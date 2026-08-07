"""Dialog for black/white AI strength settings."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QPushButton, QSpinBox, QVBoxLayout,
)

from src.ai.ai_profile import (
    AIProfile, KATA_MAX_VISITS, KATA_MIN_VISITS, KATA_STEP_VISITS,
    MCTS_MAX_SECONDS, MCTS_MIN_SECONDS, MCTS_STEP_SECONDS,
)


class AISettingsDialog(QDialog):
    """Edits two independent profiles without changing a running worker."""

    def __init__(self, black: AIProfile, white: AIProfile, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 参数设置")
        self.setModal(True)
        root = QVBoxLayout(self)
        self.black_controls = self._add_side(root, "黑方", black)
        self.white_controls = self._add_side(root, "白方", white)

        restore = QPushButton("恢复默认值")
        restore.clicked.connect(self.restore_defaults)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        footer = QHBoxLayout()
        footer.addWidget(restore)
        footer.addStretch(1)
        footer.addWidget(buttons)
        root.addLayout(footer)

    @staticmethod
    def _add_side(root, title: str, profile: AIProfile):
        box = QGroupBox(title)
        form = QFormLayout(box)
        seconds = QDoubleSpinBox(box)
        seconds.setRange(MCTS_MIN_SECONDS, MCTS_MAX_SECONDS)
        seconds.setSingleStep(MCTS_STEP_SECONDS)
        seconds.setDecimals(1)
        seconds.setSuffix(" 秒")
        seconds.setValue(profile.normalized().mcts_seconds)
        visits = QSpinBox(box)
        visits.setRange(KATA_MIN_VISITS, KATA_MAX_VISITS)
        visits.setSingleStep(KATA_STEP_VISITS)
        visits.setSuffix(" visits")
        visits.setValue(profile.normalized().kata_visits)
        form.addRow("MCTS 思考时间", seconds)
        form.addRow("KataGo 搜索次数", visits)
        root.addWidget(box)
        return seconds, visits

    def restore_defaults(self):
        for seconds, visits in (self.black_controls, self.white_controls):
            seconds.setValue(1.0)
            visits.setValue(600)

    @staticmethod
    def _profile(controls) -> AIProfile:
        seconds, visits = controls
        return AIProfile(seconds.value(), visits.value()).normalized()

    def profiles(self) -> tuple[AIProfile, AIProfile]:
        return self._profile(self.black_controls), self._profile(self.white_controls)
