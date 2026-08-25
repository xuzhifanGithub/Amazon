from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.config import create_settings
from src.gui.line_dog_widget import LineDogWidget


PANEL_THEMES = {
    "BW": {
        "surface": "#FFFFFF",
        "panel": "#F4F6F8",
        "border": "#D9DEE5",
        "text": "#20252B",
        "muted": "#6B7280",
        "accent": "#3B4654",
        "accent_soft": "#E7EBF0",
        "success": "#2D8A62",
        "warning": "#C47A18",
    },
    "RB": {
        "surface": "#FFFFFF",
        "panel": "#F3F6FF",
        "border": "#D5DDF2",
        "text": "#202A45",
        "muted": "#66708A",
        "accent": "#4B5CC4",
        "accent_soft": "#E5E9FF",
        "success": "#2C8C78",
        "warning": "#C97935",
    },
    "GS": {
        "surface": "#FFFFFF",
        "panel": "#F2F8F5",
        "border": "#D3E4DA",
        "text": "#25352C",
        "muted": "#6A7C70",
        "accent": "#3C8062",
        "accent_soft": "#E0F0E7",
        "success": "#2F8A64",
        "warning": "#C57936",
    },
    "PS": {
        "surface": "#FFFFFF",
        "panel": "#FBF4F8",
        "border": "#E8D6E0",
        "text": "#432D3A",
        "muted": "#856B79",
        "accent": "#9A526C",
        "accent_soft": "#F4E1EA",
        "success": "#45886F",
        "warning": "#C4774E",
    },
}


class AIInfoPanel(QWidget):
    """Theme-aware card panel for game status and AI analysis."""

    def __init__(self, parent=None, color_scheme: str = "BW", settings=None,
                 zoom_percent: int = 100):
        super().__init__(parent)
        self.setObjectName("aiInfoPanel")
        self._zoom_percent = 100
        self._theme_key = color_scheme.upper()
        self._card_layouts = []
        # The board controls the main-window height. Dynamic progress text and
        # Top-N analysis rows must be contained inside this side panel instead
        # of increasing the window's minimum height.
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Ignored)

        root = QVBoxLayout(self)
        self._root_layout = root
        root.setContentsMargins(8, 10, 12, 10)
        root.setSpacing(8)

        status_card, status_layout = self._create_card("当前状态", "statusCard")
        status_row = QHBoxLayout()
        self._status_row = status_row
        status_row.setSpacing(10)
        self.status_indicator = QLabel()
        self.status_indicator.setObjectName("statusIndicator")
        self.status_indicator.setFixedSize(10, 10)
        self.status_label = QLabel("欢迎！")
        self.status_label.setObjectName("statusValue")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        # Keep the status dot on the same visual line as the status text,
        # including when the text wraps to multiple lines.
        status_row.addWidget(self.status_indicator, 0, Qt.AlignmentFlag.AlignVCenter)
        status_row.addWidget(self.status_label, 1)
        status_layout.addLayout(status_row)
        self.task_status_label = QLabel()
        self.task_status_label.setObjectName("taskStatus")
        self.task_status_label.setWordWrap(True)
        self.task_progress_bar = QProgressBar()
        self.task_progress_bar.setObjectName("taskProgressBar")
        self.task_progress_bar.setRange(0, 100)
        self.task_progress_bar.setValue(0)
        self.task_progress_bar.setTextVisible(True)
        self.task_progress_bar.setFixedHeight(16)
        self.task_status_label.hide()
        self.task_progress_bar.hide()
        status_layout.addWidget(self.task_status_label)
        status_layout.addWidget(self.task_progress_bar)
        root.addWidget(status_card)

        win_card, win_layout = self._create_card("局面胜率", "winRateCard")
        self.win_rate_context = QLabel("等待 AI 评估")
        self.win_rate_context.setObjectName("cardCaption")
        self.win_rate_context.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.win_rate_label = QLabel("—")
        self.win_rate_label.setObjectName("winRateValue")
        self.win_rate_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.win_rate_label.setMinimumHeight(36)
        self.win_rate_bar = QProgressBar()
        self.win_rate_bar.setObjectName("winRateBar")
        self.win_rate_bar.setRange(0, 100)
        self.win_rate_bar.setValue(0)
        self.win_rate_bar.setTextVisible(False)
        self.win_rate_bar.setFixedHeight(7)
        win_layout.addWidget(self.win_rate_context)
        win_layout.addWidget(self.win_rate_label)
        win_layout.addWidget(self.win_rate_bar)
        root.addWidget(win_card)

        analysis_card, analysis_layout = self._create_card("AI 分析", "analysisCard")
        self.info_ai_model = QLabel("模型：—")
        self.info_move_detail = QLabel("棋步：—")
        self.info_score = QLabel("预测分差：—")
        self.info_win_rate = QLabel("胜率：—")
        self.info_visits = QLabel("搜索次数：—")
        self.info_eval = QLabel("局面估值：—")
        self.info_summary = QLabel("数据：—")
        self.info_candidates = QLabel("候选：—")
        analysis_content = QWidget()
        analysis_content.setObjectName("analysisContent")
        analysis_values_layout = QVBoxLayout(analysis_content)
        self._analysis_values_layout = analysis_values_layout
        analysis_values_layout.setContentsMargins(0, 0, 4, 0)
        analysis_values_layout.setSpacing(4)
        # Retain the legacy labels as update-compatible data holders. Their
        # values are presented together in info_summary to save vertical space.
        for legacy_label in (self.info_win_rate, self.info_visits, self.info_eval):
            analysis_values_layout.addWidget(legacy_label)
            legacy_label.hide()
        for label in (
            self.info_ai_model,
            self.info_move_detail,
            self.info_score,
            self.info_summary,
            self.info_candidates,
        ):
            label.setObjectName("analysisValue")
            label.setWordWrap(True)
            analysis_values_layout.addWidget(label)
        self.info_score.hide()
        analysis_values_layout.addStretch(1)
        self.analysis_scroll = QScrollArea()
        self.analysis_scroll.setObjectName("analysisScroll")
        self.analysis_scroll.setWidgetResizable(True)
        self.analysis_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.analysis_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.analysis_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.analysis_scroll.setWidget(analysis_content)
        analysis_layout.addWidget(self.analysis_scroll, 1)
        root.addWidget(analysis_card, 1)

        self.line_dogs = LineDogWidget(
            settings if settings is not None else create_settings(),
            self,
            color_scheme=color_scheme,
        )
        root.addWidget(self.line_dogs)

        self.set_zoom_percent(zoom_percent)

    def _create_card(self, title: str, object_name: str):
        card = QFrame(self)
        card.setObjectName(object_name)
        layout = QVBoxLayout(card)
        self._card_layouts.append(layout)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(5)
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        layout.addWidget(title_label)
        return card, layout

    def set_theme(self, color_scheme: str):
        self._theme_key = color_scheme.upper()
        theme = PANEL_THEMES.get(self._theme_key, PANEL_THEMES["BW"])
        scale = self._zoom_percent / 100.0
        px = lambda value: max(1, round(value * scale))
        pt = lambda value: f"{value * scale:.1f}"
        self.setStyleSheet(f"""
            QWidget#aiInfoPanel {{
                background: transparent;
                color: {theme['text']};
            }}
            QFrame#statusCard, QFrame#winRateCard, QFrame#analysisCard,
            QFrame#lineDogCard {{
                background: {theme['surface']};
                border: 1px solid {theme['border']};
                border-radius: {px(14)}px;
            }}
            QLabel#cardTitle {{
                color: {theme['muted']};
                font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
                font-size: {pt(10)}pt;
                font-weight: 600;
            }}
            QLabel#petTitle {{
                color: {theme['text']};
                font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
                font-size: {pt(10)}pt;
                font-weight: 600;
            }}
            QLabel#petCaption, QLabel#petStatus {{
                color: {theme['muted']};
                font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
                font-size: {pt(8.5)}pt;
            }}
            QPushButton#petButton {{
                color: white;
                background: {theme['accent']};
                border: none;
                border-radius: {px(8)}px;
                padding: {px(6)}px {px(12)}px;
                font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
                font-weight: 600;
            }}
            QPushButton#petButton:hover {{ background: {theme['success']}; }}
            QPushButton#petButton:pressed {{
                color: {theme['muted']};
                background: {theme['accent_soft']};
            }}
            QLabel#cardCaption {{
                color: {theme['muted']};
                font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
                font-size: {pt(9)}pt;
            }}
            QLabel#statusValue {{
                color: {theme['text']};
                font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
                font-size: {pt(11)}pt;
                font-weight: 600;
            }}
            QLabel#taskStatus {{
                color: {theme['warning']};
                font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
                font-size: {pt(9)}pt;
            }}
            QLabel#winRateValue {{
                color: {theme['accent']};
                font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
                font-size: {pt(22)}pt;
                font-weight: 700;
            }}
            QLabel#analysisValue {{
                color: {theme['text']};
                background: {theme['panel']};
                border: 1px solid {theme['border']};
                border-radius: {px(6)}px;
                padding: {px(4)}px {px(6)}px;
                font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
                font-size: {pt(8.5)}pt;
            }}
            QWidget#analysisContent, QScrollArea#analysisScroll {{
                background: transparent;
                border: none;
            }}
            QScrollArea#analysisScroll QScrollBar:vertical {{
                width: {px(7)}px;
                background: transparent;
            }}
            QScrollArea#analysisScroll QScrollBar::handle:vertical {{
                min-height: {px(24)}px;
                background: {theme['border']};
                border-radius: {px(3)}px;
            }}
            QProgressBar#winRateBar, QProgressBar#taskProgressBar {{
                background: {theme['accent_soft']};
                border: none;
                border-radius: {px(3)}px;
            }}
            QProgressBar#winRateBar::chunk, QProgressBar#taskProgressBar::chunk {{
                background: {theme['accent']};
                border-radius: {px(3)}px;
            }}
            QProgressBar#taskProgressBar {{
                color: {theme['text']};
                font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
                font-size: {pt(8)}pt;
                text-align: center;
            }}
            QLabel#statusIndicator {{
                background: {theme['success']};
                border-radius: {px(5)}px;
            }}
        """)
        self._theme = theme
        self.line_dogs.set_theme(color_scheme)

    def set_zoom_percent(self, percent: int):
        """Scale the full side panel together with the board."""
        self._zoom_percent = percent if percent in (80, 100, 120, 140) else 100
        scale = self._zoom_percent / 100.0
        px = lambda value: max(1, round(value * scale))

        self.setFixedWidth(px(280))
        self._root_layout.setContentsMargins(px(8), px(10), px(12), px(10))
        self._root_layout.setSpacing(px(8))
        self._status_row.setSpacing(px(10))
        for layout in self._card_layouts:
            layout.setContentsMargins(px(12), px(8), px(12), px(8))
            layout.setSpacing(px(5))
        self.task_progress_bar.setFixedHeight(px(16))
        self.win_rate_label.setMinimumHeight(px(36))
        self.win_rate_bar.setFixedHeight(px(7))
        self._analysis_values_layout.setContentsMargins(0, 0, px(4), 0)
        self._analysis_values_layout.setSpacing(px(4))
        self.status_indicator.setFixedSize(px(10), px(10))
        self.line_dogs.set_zoom_percent(self._zoom_percent)
        self.set_theme(self._theme_key)
        self.updateGeometry()

    def set_status(self, text: str):
        self.status_label.setText(text)
        thinking = "思考" in text or "AI" in text and "轮到" not in text
        color = self._theme["warning"] if thinking else self._theme["success"]
        radius = max(1, round(5 * self._zoom_percent / 100.0))
        self.status_indicator.setStyleSheet(
            f"background: {color}; border-radius: {radius}px;")

    def set_win_rate(self, win_rate=None, context: str = ""):
        if win_rate is None or win_rate < 0 or win_rate > 100.0001:
            self.win_rate_context.setText(context or "等待 AI 评估")
            self.win_rate_label.setText("—")
            self.win_rate_bar.setValue(0)
            return
        self.win_rate_context.setText(context or "当前行动方 AI 预测")
        self.win_rate_label.setText(f"{win_rate:.1f}%")
        self.win_rate_bar.setValue(max(0, min(100, round(win_rate))))

    def set_task_progress(self, text: str = "", progress: int | None = None):
        """Show a background hint-analysis stage without replacing turn status."""
        if not text:
            self.task_status_label.clear()
            self.task_progress_bar.setRange(0, 100)
            self.task_progress_bar.setValue(0)
            self.task_status_label.hide()
            self.task_progress_bar.hide()
            return

        self.task_status_label.setText(text)
        self.task_status_label.show()
        self.task_progress_bar.show()
        if progress is None:
            # Busy indicator while engine startup duration is unknown.
            self.task_progress_bar.setRange(0, 0)
        else:
            self.task_progress_bar.setRange(0, 100)
            self.task_progress_bar.setValue(max(0, min(100, round(progress))))

    def set_candidates(self, rows: list[str] | tuple[str, ...] | None = None):
        self.info_candidates.setText("候选：—" if not rows else "候选：\n" + "\n".join(rows))
