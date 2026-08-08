from __future__ import annotations

import math
from datetime import date
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


PET_THEMES = {
    "BW": {"scene": "#F1F3F5", "line": "#32363B", "gold": "#E7B86B", "blush": "#EFA4A9", "accent": "#66717D"},
    "RB": {"scene": "#EEF2FF", "line": "#303B59", "gold": "#E9B76A", "blush": "#EE9FAE", "accent": "#6679C8"},
    "GS": {"scene": "#ECF6EF", "line": "#30473A", "gold": "#E5B269", "blush": "#ECA4A2", "accent": "#579071"},
    "PS": {"scene": "#FAEEF4", "line": "#503943", "gold": "#E8B66F", "blush": "#E79EB8", "accent": "#A96B83"},
}


class DogCanvas(QWidget):
    """Official two-dog artwork with a small, UI-native idle animation."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(124)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("点一点两只小狗")
        self._theme = PET_THEMES["BW"]
        self._phase = 0.0
        self._blink = False
        self._pose = "idle"
        asset = Path(__file__).resolve().parents[1] / "assets" / "line_dogs_official.png"
        self._artwork = QPixmap(str(asset))
        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._animate)
        self._timer.start()

    def set_theme(self, scheme: str) -> None:
        self._theme = PET_THEMES.get(scheme.upper(), PET_THEMES["BW"])
        self.update()

    def set_pose(self, pose: str) -> None:
        self._pose = pose
        self.update()

    def _animate(self) -> None:
        self._phase += 0.12
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._theme["scene"]))
        painter.drawRoundedRect(QRectF(1, 1, width - 2, height - 2), 11, 11)

        if self._artwork.isNull():
            painter.setPen(QColor(self._theme["line"]))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "小狗图片未找到")
            return

        # The official product image is a 2x2 sprite sheet. Its lower row is
        # exactly the requested Maltese + golden retriever pair.
        bounce = math.sin(self._phase * 1.1) * (2.0 if self._pose != "idle" else 0.7)
        target_width = min(width - 24, 218)
        target_height = target_width / 2
        target = QRectF((width - target_width) / 2, (height - target_height) / 2 + bounce,
                        target_width, target_height)
        source = QRectF(0, self._artwork.height() / 2,
                        self._artwork.width(), self._artwork.height() / 2)
        painter.drawPixmap(target, self._artwork, source)

        if self._pose != "idle":
            heart_y = 21 + math.sin(self._phase * 2.0) * 2
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self._theme["blush"]))
            heart = QPainterPath(QPointF(width / 2, heart_y + 10))
            heart.cubicTo(width / 2 - 16, heart_y, width / 2 - 8, heart_y - 9,
                          width / 2, heart_y - 2)
            heart.cubicTo(width / 2 + 8, heart_y - 9, width / 2 + 16, heart_y,
                          width / 2, heart_y + 10)
            painter.drawPath(heart)


class LineDogWidget(QFrame):
    """Self-contained two-dog desktop pet with no game-state dependencies."""

    def __init__(self, settings, parent=None, color_scheme: str = "BW"):
        super().__init__(parent)
        self.setObjectName("lineDogCard")
        self.settings = settings
        # The former plant mini-game has been fully replaced; discard its stale data.
        self.settings.remove("garden")
        self.affection = max(0, settings.value("pets/affection", 0, type=int))
        self.snacks, self.snack_date = self._load_daily_snacks()
        self._message_index = 0
        self._reaction_timer = QTimer(self)
        self._reaction_timer.setSingleShot(True)
        self._reaction_timer.timeout.connect(self._relax)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        heading = QHBoxLayout()
        title = QLabel("线条小狗")
        title.setObjectName("petTitle")
        self.caption = QLabel("马尔济斯 × 小金毛")
        self.caption.setObjectName("petCaption")
        heading.addWidget(title)
        heading.addStretch(1)
        heading.addWidget(self.caption)
        layout.addLayout(heading)

        self.canvas = DogCanvas(self)
        self.canvas.clicked.connect(self.pet_dogs)
        layout.addWidget(self.canvas)

        self.status_label = QLabel("两只小狗正在安静贴贴")
        self.status_label.setObjectName("petStatus")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        self.pet_button = QPushButton("摸摸")
        self.feed_button = QPushButton()
        for button in (self.pet_button, self.feed_button):
            button.setObjectName("petButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pet_button.clicked.connect(self.pet_dogs)
        self.feed_button.clicked.connect(self.feed_dogs)
        actions.addWidget(self.pet_button)
        actions.addWidget(self.feed_button)
        layout.addLayout(actions)

        self.set_theme(color_scheme)
        self._refresh()

    def _load_daily_snacks(self) -> tuple[int, str]:
        today = date.today().isoformat()
        saved_date = self.settings.value("pets/snack_date", "", type=str)
        if saved_date != today:
            return 3, today
        return max(0, min(3, self.settings.value("pets/snacks", 3, type=int))), today

    def _save(self) -> None:
        self.settings.setValue("pets/affection", self.affection)
        self.settings.setValue("pets/snacks", self.snacks)
        self.settings.setValue("pets/snack_date", self.snack_date)
        self.settings.sync()

    def _refresh(self) -> None:
        self.feed_button.setText(f"喂零食 · {self.snacks}")
        self.feed_button.setEnabled(self.snacks > 0)
        self.setToolTip(f"今日零食：{self.snacks}/3\n陪伴值：{self.affection}")

    def _relax(self) -> None:
        self.canvas.set_pose("idle")
        self.status_label.setText("两只小狗正在安静贴贴")

    def _show_reaction(self, pose: str, message: str) -> None:
        self.canvas.set_pose(pose)
        self.status_label.setText(message)
        # Restarting one owned timer prevents an older interaction from ending a
        # newer reaction prematurely.
        self._reaction_timer.start(2600)

    def pet_dogs(self) -> None:
        messages = ("摸摸成功，小尾巴摇起来了", "小白和小金贴得更近了", "收到了两份小狗喜欢")
        message = messages[self._message_index % len(messages)]
        self._message_index += 1
        self.affection += 1
        self._save()
        self._refresh()
        self._show_reaction("pet", message)

    def feed_dogs(self) -> None:
        if self.snacks <= 0:
            return
        self.snacks -= 1
        self.affection += 2
        self._save()
        self._refresh()
        self._show_reaction("snack", "零食一人一半，感情不会散")

    def set_theme(self, color_scheme: str) -> None:
        self.canvas.set_theme(color_scheme)
