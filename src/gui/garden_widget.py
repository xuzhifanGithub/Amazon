from __future__ import annotations

import math
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


GROWTH_THRESHOLDS = (0, 1, 3, 6)
STAGE_NAMES = ("种子", "嫩芽", "绿叶", "开花")


GARDEN_THEMES = {
    "BW": {"sky": "#EEF2F3", "soil": "#8B735B", "pot": "#68717C", "leaf": "#4D8B67", "flower": "#E6B85C"},
    "RB": {"sky": "#EDF2FF", "soil": "#90715E", "pot": "#6678C5", "leaf": "#4C957D", "flower": "#E8838E"},
    "GS": {"sky": "#EAF6EE", "soil": "#846C50", "pot": "#D08A50", "leaf": "#3C8A61", "flower": "#F1C65B"},
    "PS": {"sky": "#FAEDF4", "soil": "#8A6E62", "pot": "#A96883", "leaf": "#598E70", "flower": "#E99CB8"},
}


@dataclass(slots=True)
class GardenState:
    water_drops: int = 0
    growth: int = 0
    completed_games: int = 0

    @property
    def stage(self) -> int:
        return max(index for index, threshold in enumerate(GROWTH_THRESHOLDS)
                   if self.growth >= threshold)

    @property
    def fully_grown(self) -> bool:
        return self.stage == len(GROWTH_THRESHOLDS) - 1

    def reward_game(self) -> None:
        self.completed_games += 1
        self.water_drops += 1

    def water(self) -> bool:
        if self.water_drops <= 0 or self.fully_grown:
            return False
        self.water_drops -= 1
        self.growth += 1
        return True


class PlantCanvas(QWidget):
    """Small vector plant scene; no image assets are required."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(116)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.stage = 0
        self.sway = 0.0
        self._phase = 0.0
        self._thinking = False
        self._theme = GARDEN_THEMES["BW"]
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._animate)

    def set_theme(self, scheme: str) -> None:
        self._theme = GARDEN_THEMES.get(scheme.upper(), GARDEN_THEMES["BW"])
        self.update()

    def set_stage(self, stage: int) -> None:
        self.stage = max(0, min(3, int(stage)))
        self.update()

    def set_thinking(self, thinking: bool) -> None:
        self._thinking = bool(thinking)
        if self._thinking:
            self._timer.start()
        else:
            self._timer.stop()
            self.sway = 0.0
            self.update()

    def _animate(self) -> None:
        self._phase += 0.22
        self.sway = math.sin(self._phase) * 2.2
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        scene = QRectF(1, 1, width - 2, height - 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._theme["sky"]))
        painter.drawRoundedRect(scene, 11, 11)

        ground_y = height * 0.82
        painter.setBrush(QColor(self._theme["soil"]))
        painter.drawEllipse(QRectF(width * 0.24, ground_y - 5, width * 0.52, 13))

        pot_top = ground_y - 31
        pot = QPainterPath()
        pot.moveTo(width * 0.36, pot_top)
        pot.lineTo(width * 0.64, pot_top)
        pot.lineTo(width * 0.59, ground_y)
        pot.quadTo(width * 0.50, ground_y + 5, width * 0.41, ground_y)
        pot.closeSubpath()
        painter.setBrush(QColor(self._theme["pot"]))
        painter.drawPath(pot)
        painter.setBrush(QColor(self._theme["soil"]).lighter(112))
        painter.drawEllipse(QRectF(width * 0.355, pot_top - 4, width * 0.29, 10))

        center_x = width * 0.5 + self.sway
        if self.stage == 0:
            painter.setBrush(QColor("#B98554"))
            painter.drawEllipse(QRectF(center_x - 5, pot_top - 8, 10, 7))
            return

        stem_top = pot_top - (27 + self.stage * 10)
        painter.setPen(QPen(QColor(self._theme["leaf"]), 4, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(width * 0.5, pot_top), QPointF(center_x, stem_top))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._theme["leaf"]))
        leaf_count = 2 if self.stage == 1 else 4
        for index in range(leaf_count):
            side = -1 if index % 2 == 0 else 1
            y = pot_top - 14 - (index // 2) * 15
            x = center_x + side * 10
            painter.save()
            painter.translate(x, y)
            painter.rotate(side * -24)
            painter.drawEllipse(QRectF(-11, -5, 22, 10))
            painter.restore()

        if self.stage == 3:
            painter.setBrush(QColor(self._theme["flower"]))
            for angle in range(0, 360, 72):
                radians = math.radians(angle)
                painter.drawEllipse(QRectF(center_x + math.cos(radians) * 8 - 5,
                                           stem_top + math.sin(radians) * 8 - 5, 10, 10))
            painter.setBrush(QColor("#F5D66F"))
            painter.drawEllipse(QRectF(center_x - 5, stem_top - 5, 10, 10))


class GardenWidget(QFrame):
    """Persistent, low-distraction garden card for the panel's spare area."""

    watered = pyqtSignal()

    def __init__(self, settings, parent=None, color_scheme: str = "BW"):
        super().__init__(parent)
        self.setObjectName("gardenCard")
        self.settings = settings
        self.state = GardenState(
            max(0, settings.value("garden/water_drops", 0, type=int)),
            max(0, settings.value("garden/growth", 0, type=int)),
            max(0, settings.value("garden/completed_games", 0, type=int)),
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        title_row = QHBoxLayout()
        title = QLabel("亚马逊小花园")
        title.setObjectName("gardenTitle")
        self.stage_label = QLabel()
        self.stage_label.setObjectName("gardenStage")
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.stage_label)
        layout.addLayout(title_row)

        self.canvas = PlantCanvas(self)
        layout.addWidget(self.canvas)

        self.activity_label = QLabel("安静地陪你下棋")
        self.activity_label.setObjectName("gardenActivity")
        self.activity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.activity_label)

        footer = QHBoxLayout()
        self.stats_label = QLabel()
        self.stats_label.setObjectName("gardenStats")
        self.water_button = QPushButton("浇水")
        self.water_button.setObjectName("waterButton")
        self.water_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.water_button.clicked.connect(self.water_plant)
        footer.addWidget(self.stats_label, 1)
        footer.addWidget(self.water_button)
        layout.addLayout(footer)

        self.set_theme(color_scheme)
        self._refresh()

    def _save(self) -> None:
        self.settings.setValue("garden/water_drops", self.state.water_drops)
        self.settings.setValue("garden/growth", self.state.growth)
        self.settings.setValue("garden/completed_games", self.state.completed_games)
        self.settings.sync()

    def _refresh(self) -> None:
        self.canvas.set_stage(self.state.stage)
        self.stage_label.setText(STAGE_NAMES[self.state.stage])
        self.stats_label.setText(
            f"水滴 {self.state.water_drops}  ·  对局 {self.state.completed_games}")
        self.water_button.setEnabled(
            self.state.water_drops > 0 and not self.state.fully_grown)
        self.water_button.setText("已开花" if self.state.fully_grown else "浇水")
        self.setToolTip(
            f"成长阶段：{STAGE_NAMES[self.state.stage]}\n"
            f"累计浇水：{self.state.growth} 次\n"
            "完成一盘棋可获得一滴水。")

    def reward_completed_game(self) -> None:
        self.state.reward_game()
        self._save()
        self._refresh()
        self.activity_label.setText("对局完成，获得 1 滴水！")

    def water_plant(self) -> None:
        if not self.state.water():
            return
        self._save()
        self._refresh()
        self.activity_label.setText(
            "植物开花啦！" if self.state.fully_grown else "喝到水了，又长大了一点")
        self.watered.emit()

    def set_ai_activity(self, active: bool, text: str = "", progress=None) -> None:
        self.canvas.set_thinking(active)
        if not active:
            if text:
                self.activity_label.setText(text)
            elif not self.activity_label.text().startswith(("对局完成", "喝到水", "植物开花")):
                self.activity_label.setText("安静地陪你下棋")
            return
        if progress is None:
            self.activity_label.setText(text or "叶片正陪 AI 一起思考…")
        else:
            self.activity_label.setText(f"{text or 'AI 正在思考'}  {round(progress)}%")

    def set_theme(self, color_scheme: str) -> None:
        self.canvas.set_theme(color_scheme)

