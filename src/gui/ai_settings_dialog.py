"""Dialog for black/white AI strength and KataGo search settings."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QSpinBox, QTabWidget,
    QTextBrowser, QVBoxLayout, QWidget,
)

from src.ai.ai_profile import (
    AIProfile, KATA_MAX_VISITS, KATA_MIN_VISITS, KATA_STEP_VISITS,
    KataSearchConfig, MCTS_MAX_SECONDS, MCTS_MIN_SECONDS, MCTS_STEP_SECONDS,
    SEARCH_CONFIG_CUSTOM, SEARCH_CONFIG_DEFAULT, SEARCH_CONFIG_STRONGEST,
    STRONGEST_KATA_SEARCH_CONFIG,
)


class AISettingsDialog(QDialog):
    """Edits two independent profiles without changing a running worker."""

    PRESET_CUSTOM = SEARCH_CONFIG_CUSTOM
    PRESET_DEFAULT = SEARCH_CONFIG_DEFAULT
    PRESET_STRONGEST = SEARCH_CONFIG_STRONGEST

    def __init__(self, black: AIProfile, white: AIProfile, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 参数设置")
        self.setModal(True)
        self.resize(900, 690)
        root = QVBoxLayout(self)

        tabs = QTabWidget(self)
        settings_page = QWidget(tabs)
        settings_layout = QVBoxLayout(settings_page)
        note = QLabel(
            "最强棋力保持 MCTS 1 秒和 KataGo 600 visits，只切换竞赛式搜索参数，"
            "并关闭分差头。选择“自定义高级参数”后，可直接设置温度、cpuct、"
            "图搜索、根噪声和搜索线程等参数。具体含义和参考值见第二个标签页。",
            settings_page)
        note.setWordWrap(True)
        settings_layout.addWidget(note)

        sides = QHBoxLayout()
        self.black_controls = self._add_side(sides, "黑方", black)
        self.white_controls = self._add_side(sides, "白方", white)
        settings_layout.addLayout(sides)
        tabs.addTab(settings_page, "参数设置")

        self.parameter_help = QTextBrowser(tabs)
        self.parameter_help.setOpenExternalLinks(False)
        self.parameter_help.setHtml(self._parameter_help_html())
        tabs.addTab(self.parameter_help, "参数说明与参考值")
        root.addWidget(tabs)

        restore = QPushButton("恢复默认值")
        restore.clicked.connect(self.restore_defaults)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        footer = QHBoxLayout()
        footer.addWidget(restore)
        footer.addStretch(1)
        footer.addWidget(buttons)
        root.addLayout(footer)

    @staticmethod
    def _parameter_help_html() -> str:
        return """
        <style>
          body { font-family: sans-serif; line-height: 1.35; }
          table { border-collapse: collapse; width: 100%; }
          th, td { border: 1px solid #999; padding: 6px; vertical-align: top; }
          th { background: #e8e8e8; }
          code { font-family: monospace; }
        </style>
        <h3>如何理解这些参数</h3>
        <p>“引擎默认配置”不覆盖 X/L 自带配置；“最强棋力”使用表中的固定值；
        “自定义高级参数”才会把界面数值写入运行时配置。参考范围是实用起点，
        不是所有局面都严格单调变强。</p>
        <table>
          <tr><th>参数</th><th>作用</th><th>默认 / 最强</th><th>常用参考</th></tr>
          <tr><td>MCTS 思考时间</td><td>只控制两个公式 MCTS 的单步时间。</td>
              <td>默认 1 秒；最强方案仍为 1 秒</td><td>0.5–3 秒；越长通常越强</td></tr>
          <tr><td>KataGo 搜索次数</td><td>控制 X/L 每个阶段的访问数。</td>
              <td>X 默认 600；L 历史默认 400；最强方案 600</td>
              <td>300 快速，600 均衡，1000–2000 高预算</td></tr>
          <tr><td>amazon_X 分差头</td><td>以 0.02 动态分差效用辅助胜率接近的选步；只对 X 有效。</td>
              <td>默认关闭；最强关闭</td><td>追求纯胜率关闭；偏好大分差可开启</td></tr>
          <tr><td>前期 / 后期落子温度</td><td>搜索结束后按访问数抽取实际着法；
              0 表示稳定选择搜索最优着，越高越随机。</td>
              <td>引擎默认约 0.5 / 0.1；最强 0 / 0</td>
              <td>比赛 0–0.01；多样性对局 0.1–0.5</td></tr>
          <tr><td>网络策略温度</td><td>调整策略头先验分布；低于 1 更尖锐，
              高于 1 更平滑。它不是最终落子的抽样温度。</td>
              <td>X 默认 1.1；L 默认 1.0；最强 1.0</td><td>0.9–1.2</td></tr>
          <tr><td>cpuct 探索系数</td><td>平衡探索新着法与利用高价值着法；
              越高越愿意探索低访问候选。</td>
              <td>X 默认 0.9；标准/最强 1.0</td><td>0.8–1.2</td></tr>
          <tr><td>cpuct 对数增量</td><td>搜索访问数增长时逐渐增加探索强度。</td>
              <td>X 默认 0.6；标准/最强 0.45</td><td>0.3–0.7</td></tr>
          <tr><td>cpuct 基数</td><td>控制对数探索增量从多大访问量开始明显生效。</td>
              <td>默认/最强 500</td><td>300–1000</td></tr>
          <tr><td>子树价值偏置</td><td>让父节点参考子树内部价值走势；
              过高可能使搜索偏离根节点的直接判断。</td>
              <td>X 默认/最强 0</td><td>纯网络拟合建议 0；实验范围 0–0.45</td></tr>
          <tr><td>搜索线程数</td><td>单盘并行搜索线程；更多线程通常更快，
              但固定 visits 下会增加虚拟损失和调度噪声。</td>
              <td>界面默认 8；正式评测/最强 1</td>
              <td>棋力可比测试用 1；日常提速用 4–8</td></tr>
          <tr><td>图搜索</td><td>让重复局面共享节点；可能提高复用率，
              但与正式树搜索评测口径不同。</td>
              <td>X 默认开启；L 默认/最强关闭</td><td>复现正式评测关闭；可自行对局比较</td></tr>
          <tr><td>根节点噪声</td><td>给根节点加入探索噪声，主要用于产生多样化训练数据。</td>
              <td>默认/最强关闭</td><td>正式下棋关闭；仅自博弈探索时开启</td></tr>
        </table>
        <p><b>推荐：</b>想稳定下最强着法直接选“最强棋力”；想研究参数时选
        “自定义高级参数”，一次只改一个量并用交换黑白的多盘对局比较。</p>
        """

    @staticmethod
    def _double_spin(parent, minimum, maximum, step, decimals, value):
        control = QDoubleSpinBox(parent)
        control.setRange(minimum, maximum)
        control.setSingleStep(step)
        control.setDecimals(decimals)
        control.setValue(value)
        return control

    @staticmethod
    def _profile_search_config(profile: AIProfile) -> KataSearchConfig:
        return KataSearchConfig(
            profile.move_temperature_early,
            profile.move_temperature,
            profile.policy_temperature,
            profile.cpuct_exploration,
            profile.cpuct_exploration_log,
            profile.cpuct_exploration_base,
            profile.use_graph_search,
            profile.root_noise_enabled,
            profile.subtree_value_bias_factor,
            profile.num_search_threads,
        )

    @staticmethod
    def _set_search_controls(controls, config: KataSearchConfig):
        config = config.normalized()
        controls["move_temperature_early"].setValue(
            config.move_temperature_early)
        controls["move_temperature"].setValue(config.move_temperature)
        controls["policy_temperature"].setValue(config.policy_temperature)
        controls["cpuct_exploration"].setValue(config.cpuct_exploration)
        controls["cpuct_exploration_log"].setValue(config.cpuct_exploration_log)
        controls["cpuct_exploration_base"].setValue(config.cpuct_exploration_base)
        controls["use_graph_search"].setChecked(config.use_graph_search)
        controls["root_noise_enabled"].setChecked(config.root_noise_enabled)
        controls["subtree_value_bias_factor"].setValue(
            config.subtree_value_bias_factor)
        controls["num_search_threads"].setValue(config.num_search_threads)

    @classmethod
    def _add_side(cls, root, title: str, profile: AIProfile):
        profile = profile.normalized()
        box = QGroupBox(title)
        box_layout = QVBoxLayout(box)
        form = QFormLayout()

        mode = QComboBox(box)
        mode.addItem("引擎默认配置", cls.PRESET_DEFAULT)
        mode.addItem("最强棋力（1秒 / 600v）", cls.PRESET_STRONGEST)
        mode.addItem("自定义高级参数", cls.PRESET_CUSTOM)
        mode.setToolTip(
            "默认方案保留每个引擎自带参数；最强方案使用固定竞赛参数；"
            "自定义方案应用下方全部高级参数。")

        seconds = cls._double_spin(
            box, MCTS_MIN_SECONDS, MCTS_MAX_SECONDS,
            MCTS_STEP_SECONDS, 1, profile.mcts_seconds)
        seconds.setSuffix(" 秒")
        seconds.setToolTip(
            "只影响公式 MCTS。默认/最强 1 秒；日常参考 0.5–3 秒。")
        visits = QSpinBox(box)
        visits.setRange(KATA_MIN_VISITS, KATA_MAX_VISITS)
        visits.setSingleStep(KATA_STEP_VISITS)
        visits.setSuffix(" visits")
        visits.setValue(profile.kata_visits)
        visits.setToolTip(
            "只影响 amazon_X/L。X 默认 600、L 历史默认 400；"
            "300 快速，600 均衡，1000–2000 为高预算。")
        score_utility = QCheckBox("开启", box)
        score_utility.setChecked(profile.score_utility_enabled)
        score_utility.setToolTip(
            "仅作用于 amazon_X；开启后搜索会加入少量动态分差价值。"
            "最强棋力方案固定关闭。")
        form.addRow("配置方案", mode)
        form.addRow("MCTS 思考时间", seconds)
        form.addRow("KataGo 搜索次数", visits)
        form.addRow("amazon_X 分差头", score_utility)
        box_layout.addLayout(form)

        advanced = QGroupBox("KataGo 高级搜索参数", box)
        advanced_form = QFormLayout(advanced)
        search_config = cls._profile_search_config(profile)
        move_temperature_early = cls._double_spin(
            advanced, 0.0, 5.0, 0.05, 2,
            search_config.move_temperature_early)
        move_temperature_early.setToolTip(
            "开局阶段从访问分布选择实际着法的温度；0 表示不随机抽样。"
            "比赛参考 0–0.01，多样性对局参考 0.1–0.5。")
        move_temperature = cls._double_spin(
            advanced, 0.0, 5.0, 0.05, 2, search_config.move_temperature)
        move_temperature.setToolTip(
            "中后期落子温度；越低越倾向访问数最高的着法。"
            "比赛参考 0–0.01，多样性对局参考 0.1–0.2。")
        policy_temperature = cls._double_spin(
            advanced, 0.01, 5.0, 0.05, 2,
            search_config.policy_temperature)
        policy_temperature.setToolTip(
            "调整网络策略先验的平滑程度；1.0 使用模型原始策略分布。"
            "常用参考 0.9–1.2。")
        cpuct_exploration = cls._double_spin(
            advanced, 0.1, 3.0, 0.05, 2,
            search_config.cpuct_exploration)
        cpuct_exploration.setToolTip(
            "探索与利用的平衡系数。参考 0.8–1.2；最强预设 1.0。")
        cpuct_exploration_log = cls._double_spin(
            advanced, 0.0, 3.0, 0.05, 2,
            search_config.cpuct_exploration_log)
        cpuct_exploration_log.setToolTip(
            "随搜索规模增长的探索增量。参考 0.3–0.7；最强预设 0.45。")
        cpuct_exploration_base = QSpinBox(advanced)
        cpuct_exploration_base.setRange(1, 10000)
        cpuct_exploration_base.setSingleStep(100)
        cpuct_exploration_base.setValue(search_config.cpuct_exploration_base)
        cpuct_exploration_base.setToolTip(
            "对数探索增量的生效基数。参考 300–1000；默认/最强 500。")
        subtree_value_bias_factor = cls._double_spin(
            advanced, 0.0, 1.0, 0.05, 2,
            search_config.subtree_value_bias_factor)
        subtree_value_bias_factor.setToolTip(
            "子树内部价值走势的偏置强度。纯网络拟合建议 0；实验范围 0–0.45。")
        num_search_threads = QSpinBox(advanced)
        num_search_threads.setRange(1, 32)
        num_search_threads.setValue(search_config.num_search_threads)
        num_search_threads.setToolTip(
            "单盘搜索线程数；1 更接近正式评测，更多线程通常更快但会增加并行噪声。")
        use_graph_search = QCheckBox("开启", advanced)
        use_graph_search.setChecked(search_config.use_graph_search)
        use_graph_search.setToolTip(
            "重复局面共享节点。X 默认开启；正式评测口径和最强预设关闭。")
        root_noise_enabled = QCheckBox("开启", advanced)
        root_noise_enabled.setChecked(search_config.root_noise_enabled)
        root_noise_enabled.setToolTip(
            "根节点狄利克雷噪声主要用于自博弈探索，正式对弈通常关闭。")

        advanced_form.addRow("前期落子温度", move_temperature_early)
        advanced_form.addRow("后期落子温度", move_temperature)
        advanced_form.addRow("网络策略温度", policy_temperature)
        advanced_form.addRow("cpuct 探索系数", cpuct_exploration)
        advanced_form.addRow("cpuct 对数增量", cpuct_exploration_log)
        advanced_form.addRow("cpuct 基数", cpuct_exploration_base)
        advanced_form.addRow("子树价值偏置", subtree_value_bias_factor)
        advanced_form.addRow("搜索线程数", num_search_threads)
        advanced_form.addRow("图搜索", use_graph_search)
        advanced_form.addRow("根节点噪声", root_noise_enabled)
        box_layout.addWidget(advanced)
        root.addWidget(box)

        controls = {
            "mode": mode,
            "seconds": seconds,
            "visits": visits,
            "score_utility": score_utility,
            "advanced": advanced,
            "move_temperature_early": move_temperature_early,
            "move_temperature": move_temperature,
            "policy_temperature": policy_temperature,
            "cpuct_exploration": cpuct_exploration,
            "cpuct_exploration_log": cpuct_exploration_log,
            "cpuct_exploration_base": cpuct_exploration_base,
            "subtree_value_bias_factor": subtree_value_bias_factor,
            "num_search_threads": num_search_threads,
            "use_graph_search": use_graph_search,
            "root_noise_enabled": root_noise_enabled,
        }
        applying_mode = False

        def set_mode(mode_key):
            index = mode.findData(mode_key)
            if index >= 0:
                mode.setCurrentIndex(index)

        def apply_mode(_index=None):
            nonlocal applying_mode
            mode_key = mode.currentData()
            applying_mode = True
            try:
                if mode_key == cls.PRESET_STRONGEST:
                    seconds.setValue(1.0)
                    visits.setValue(600)
                    score_utility.setChecked(False)
                    cls._set_search_controls(
                        controls, STRONGEST_KATA_SEARCH_CONFIG)
                advanced.setEnabled(mode_key == cls.PRESET_CUSTOM)
            finally:
                applying_mode = False

        def leave_strongest_if_edited(*_args):
            if (not applying_mode
                    and mode.currentData() == cls.PRESET_STRONGEST):
                set_mode(cls.PRESET_CUSTOM)

        mode.currentIndexChanged.connect(apply_mode)
        seconds.valueChanged.connect(leave_strongest_if_edited)
        visits.valueChanged.connect(leave_strongest_if_edited)
        score_utility.toggled.connect(leave_strongest_if_edited)
        blocked = mode.blockSignals(True)
        mode.setCurrentIndex(mode.findData(profile.search_config_mode))
        mode.blockSignals(blocked)
        advanced.setEnabled(profile.search_config_mode == cls.PRESET_CUSTOM)
        return controls

    def restore_defaults(self):
        for controls in (self.black_controls, self.white_controls):
            mode = controls["mode"]
            mode.setCurrentIndex(mode.findData(self.PRESET_DEFAULT))
            controls["seconds"].setValue(1.0)
            controls["visits"].setValue(600)
            controls["score_utility"].setChecked(False)
            self._set_search_controls(controls, KataSearchConfig())
            controls["advanced"].setEnabled(False)

    @staticmethod
    def _profile(controls) -> AIProfile:
        return AIProfile(
            controls["seconds"].value(),
            controls["visits"].value(),
            controls["score_utility"].isChecked(),
            controls["mode"].currentData(),
            controls["move_temperature_early"].value(),
            controls["move_temperature"].value(),
            controls["policy_temperature"].value(),
            controls["cpuct_exploration"].value(),
            controls["cpuct_exploration_log"].value(),
            controls["cpuct_exploration_base"].value(),
            controls["use_graph_search"].isChecked(),
            controls["root_noise_enabled"].isChecked(),
            controls["subtree_value_bias_factor"].value(),
            controls["num_search_threads"].value(),
        ).normalized()

    def profiles(self) -> tuple[AIProfile, AIProfile]:
        return self._profile(self.black_controls), self._profile(self.white_controls)
