from __future__ import annotations

import random
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


PET_ACTIONS = {
    "idle": ("047-相互依靠.gif", "靠在一起，安静陪伴", 0),
    "heart_white": ("038-小白爱心环绕.gif", "小白送来一圈爱心", 3600),
    "comfort": ("048-抱抱安慰.gif", "抱一抱，烦恼就跑掉", 4200),
    "hello": ("051-并肩打招呼.gif", "两只小狗一起打招呼", 3600),
    "fly": ("052-并排飞奔.gif", "并排飞奔，快乐加倍", 3200),
    "chase_circle": ("053-追逐跑圈.gif", "围着房间追逐跑圈", 3200),
    "heart_white_gift": ("055-小白送爱心.gif", "小白送来一颗爱心", 3600),
    "heart_gold": ("057-小金毛送爱心.gif", "小金毛也送来一颗爱心", 3600),
    "magic": ("058-小金毛挥魔法棒.gif", "小金毛施展快乐魔法", 4200),
    "peek_white": ("103-小白探头.gif", "小白从角落探出头", 3600),
    "peek_gold": ("104-小金毛探头.gif", "小金毛偷偷观察", 3600),
    "shoulder": ("112-搭肩贴贴.gif", "肩并肩贴在一起", 3600),
    "chase": ("136-开心追逐.gif", "两只小狗开心地追起来了", 3800),
    "pet": ("141-摸摸小金毛.gif", "小白正在摸摸小金毛", 3600),
    "sleep": ("160-抱在一起睡觉.gif", "玩累了，抱在一起睡觉", 5200),
    "kiss": ("174-互相亲亲.gif", "互相亲亲，今天也要开心", 3600),
}

PET_ASSETS = {key: value[0] for key, value in PET_ACTIONS.items()}
PET_ACTION_KEYS = tuple(key for key in PET_ACTIONS if key != "idle")
PETTING_ACTIONS = ("pet", "comfort", "shoulder", "kiss", "heart_white_gift", "heart_gold")
PLAY_ACTIONS = ("chase", "fly", "chase_circle", "hello", "magic")


class DogCanvas(QLabel):
    """A clickable GIF player for the two-dog desktop pet."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(170)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("点一点两只小狗")
        self._theme = PET_THEMES["BW"]
        self._theme_key = "BW"
        self._zoom_percent = 100
        self._asset_dir = Path(__file__).resolve().parents[1] / "assets" / "line_dogs"
        self._movies: dict[str, QMovie] = {}
        self._source_sizes: dict[str, QSize] = {}
        self._pose = "idle"
        self._movie: QMovie | None = None
        self.set_pose("idle")

    @property
    def movie_is_valid(self) -> bool:
        return self._movie is not None and self._movie.isValid()

    def set_theme(self, scheme: str) -> None:
        self._theme_key = scheme.upper()
        self._theme = PET_THEMES.get(self._theme_key, PET_THEMES["BW"])
        radius = max(1, round(11 * self._zoom_percent / 100.0))
        self.setStyleSheet(
            f"background: {self._theme['scene']}; border: none; border-radius: {radius}px;")

    def _apply_movie_scale(self, pose: str, movie: QMovie) -> None:
        source_size = QSize(self._source_sizes.get(pose, QSize()))
        if source_size.isEmpty():
            # QMovie may not expose frameRect until its first frame has been
            # decoded. Decode that frame once so zooming never turns a newly
            # loaded sticker into a 1 x 1 image.
            movie.jumpToFrame(0)
            source_size = movie.currentImage().size()
            if source_size.isEmpty():
                movie.setScaledSize(QSize())
                return
            self._source_sizes[pose] = QSize(source_size)
        base_size = QSize(source_size)
        if base_size.width() > 170 or base_size.height() > 170:
            base_size.scale(170, 170, Qt.AspectRatioMode.KeepAspectRatio)
        scale = self._zoom_percent / 100.0
        target = QSize(
            max(1, round(base_size.width() * scale)),
            max(1, round(base_size.height() * scale)),
        )
        if target == source_size:
            movie.setScaledSize(QSize())
        else:
            movie.setScaledSize(target)

    def set_zoom_percent(self, percent: int) -> None:
        self._zoom_percent = percent if percent in (80, 100, 120, 140) else 100
        self.setFixedHeight(max(1, round(170 * self._zoom_percent / 100.0)))
        for pose, movie in self._movies.items():
            was_running = movie.state() == QMovie.MovieState.Running
            movie.stop()
            self._apply_movie_scale(pose, movie)
            if movie is self._movie and was_running:
                movie.start()
        self.set_theme(self._theme_key)

    def _movie_for(self, pose: str) -> QMovie:
        movie = self._movies.get(pose)
        if movie is None:
            movie = QMovie(str(self._asset_dir / PET_ASSETS[pose]))
            # Decode on demand so gradually seeing many random actions does not
            # retain every frame of every GIF in memory.
            movie.setCacheMode(QMovie.CacheMode.CacheNone)
            # Keep 150/170 px stickers at their native size. Only oversized
            # source GIFs are reduced, preserving their aspect ratio.
            source_size = movie.frameRect().size()
            if not source_size.isEmpty():
                self._source_sizes[pose] = QSize(source_size)
            self._apply_movie_scale(pose, movie)
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
        self._zoom_percent = 100
        self.settings.remove("garden")
        self.settings.remove("pets/snacks")
        self.settings.remove("pets/snack_date")
        self.affection = max(0, settings.value("pets/affection", 0, type=int))
        self._last_random_action = ""
        self._reaction_timer = QTimer(self)
        self._reaction_timer.setSingleShot(True)
        self._reaction_timer.timeout.connect(self._relax)
        self._random_timer = QTimer(self)
        self._random_timer.setSingleShot(True)
        self._random_timer.timeout.connect(self._show_random_action)
        self._schedule_random_action()

        layout = QVBoxLayout(self)
        self._root_layout = layout
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        heading = QHBoxLayout()
        self._heading_layout = heading
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
        self._actions_layout = actions
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
        self.status_label.setText(PET_ACTIONS["idle"][1])
        self._schedule_random_action()

    def _schedule_random_action(self) -> None:
        self._random_timer.start(random.randint(7_000, 15_000))

    def _show_reaction(self, action: str) -> None:
        _filename, message, duration = PET_ACTIONS[action]
        self._random_timer.stop()
        self.canvas.set_pose(action)
        self.status_label.setText(message)
        self._reaction_timer.start(duration)

    def _show_random_action(self) -> None:
        choices = [key for key in PET_ACTION_KEYS if key != self._last_random_action]
        action = random.choice(choices)
        self._last_random_action = action
        self._show_reaction(action)

    def pet_dogs(self) -> None:
        self.affection += 1
        self._save()
        self._refresh_tooltip()
        self._show_reaction(random.choice(PETTING_ACTIONS))

    def play_dogs(self) -> None:
        self.affection += 2
        self._save()
        self._refresh_tooltip()
        self._show_reaction(random.choice(PLAY_ACTIONS))

    def show_sleeping(self) -> None:
        self._show_reaction("sleep")

    def set_theme(self, color_scheme: str) -> None:
        self.canvas.set_theme(color_scheme)

    def set_zoom_percent(self, percent: int) -> None:
        self._zoom_percent = percent if percent in (80, 100, 120, 140) else 100
        scale = self._zoom_percent / 100.0
        px = lambda value: max(1, round(value * scale))
        self._root_layout.setContentsMargins(px(12), px(8), px(12), px(8))
        self._root_layout.setSpacing(px(4))
        self._heading_layout.setSpacing(px(6))
        self._actions_layout.setSpacing(px(6))
        self.canvas.set_zoom_percent(self._zoom_percent)
        self.updateGeometry()
