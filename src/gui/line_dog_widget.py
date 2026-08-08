from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QMovie
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


PET_THEMES = {
    "BW": {"scene": "#F1F3F5"},
    "RB": {"scene": "#EEF2FF"},
    "GS": {"scene": "#ECF6EF"},
    "PS": {"scene": "#FAEEF4"},
}


PET_ASSETS = {
    "idle": "047-相互依靠.gif",
    "play": "136-开心追逐.gif",
    "pet": "141-摸摸小金毛.gif",
    "sleep": "160-抱在一起睡觉.gif",
}


class DogCanvas(QLabel):
    """A clickable GIF player for the two-dog desktop pet."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(142)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("点一点两只小狗")
        self._theme = PET_THEMES["BW"]
        self._asset_dir = Path(__file__).resolve().parents[1] / "assets" / "line_dogs"
        self._movies: dict[str, QMovie] = {}
        self._pose = "idle"
        self._movie: QMovie | None = None
        self.set_pose("idle")

    @property
    def movie_is_valid(self) -> bool:
        return self._movie is not None and self._movie.isValid()

    def set_theme(self, scheme: str) -> None:
        self._theme = PET_THEMES.get(scheme.upper(), PET_THEMES["BW"])
        self.setStyleSheet(
            f"background: {self._theme['scene']}; border: none; border-radius: 11px;")

    def _movie_for(self, pose: str) -> QMovie:
        movie = self._movies.get(pose)
        if movie is None:
            movie = QMovie(str(self._asset_dir / PET_ASSETS[pose]))
            movie.setCacheMode(QMovie.CacheMode.CacheAll)
            movie.setScaledSize(QSize(136, 136))
            self._movies[pose] = movie
        return movie

    def set_pose(self, pose: str) -> None:
        pose = pose if pose in PET_ASSETS else "idle"
        if self._movie is not None:
            self._movie.stop()
        self._pose = pose
        self._movie = self._movie_for(pose)
        self.setMovie(self._movie)
        if self._movie.isValid():
            self._movie.start()
        else:
            self.setText("小狗动图未找到")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class LineDogWidget(QFrame):
    """Self-contained animated two-dog pet with no game-state dependencies."""

    def __init__(self, settings, parent=None, color_scheme: str = "BW"):
        super().__init__(parent)
        self.setObjectName("lineDogCard")
        self.settings = settings
        self.settings.remove("garden")
        self.settings.remove("pets/snacks")
        self.settings.remove("pets/snack_date")
        self.affection = max(0, settings.value("pets/affection", 0, type=int))
        self._message_index = 0
        self._reaction_timer = QTimer(self)
        self._reaction_timer.setSingleShot(True)
        self._reaction_timer.timeout.connect(self._relax)
        self._sleep_timer = QTimer(self)
        self._sleep_timer.setSingleShot(True)
        self._sleep_timer.setInterval(30_000)
        self._sleep_timer.timeout.connect(self.show_sleeping)
        self._sleep_timer.start()

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

        self.status_label = QLabel("靠在一起，安静陪伴")
        self.status_label.setObjectName("petStatus")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        self.pet_button = QPushButton("摸摸")
        self.play_button = QPushButton("一起玩")
        # Compatibility alias for callers that used the former second button.
        self.feed_button = self.play_button
        for button in (self.pet_button, self.play_button):
            button.setObjectName("petButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pet_button.clicked.connect(self.pet_dogs)
        self.play_button.clicked.connect(self.play_dogs)
        actions.addWidget(self.pet_button)
        actions.addWidget(self.play_button)
        layout.addLayout(actions)

        self.set_theme(color_scheme)
        self._refresh_tooltip()

    def _save(self) -> None:
        self.settings.setValue("pets/affection", self.affection)
        self.settings.sync()

    def _refresh_tooltip(self) -> None:
        self.setToolTip(f"陪伴值：{self.affection}\n动图与棋局状态无关")

    def _relax(self) -> None:
        self.canvas.set_pose("idle")
        self.status_label.setText("靠在一起，安静陪伴")
        self._sleep_timer.start()

    def _show_reaction(self, pose: str, message: str, duration: int = 3200) -> None:
        self.canvas.set_pose(pose)
        self.status_label.setText(message)
        self._reaction_timer.start(duration)
        self._sleep_timer.start()

    def pet_dogs(self) -> None:
        messages = ("小白正在摸摸小金毛", "两只小狗贴得更近了", "收到了两份小狗喜欢")
        message = messages[self._message_index % len(messages)]
        self._message_index += 1
        self.affection += 1
        self._save()
        self._refresh_tooltip()
        self._show_reaction("pet", message)

    def play_dogs(self) -> None:
        self.affection += 2
        self._save()
        self._refresh_tooltip()
        self._show_reaction("play", "两只小狗开心地追起来了", 3800)

    def show_sleeping(self) -> None:
        self._show_reaction("sleep", "玩累了，抱在一起睡觉", 5000)

    def set_theme(self, color_scheme: str) -> None:
        self.canvas.set_theme(color_scheme)
