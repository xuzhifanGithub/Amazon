# src/gui/main_window.py
import re
import os
import sys

import datetime
from PyQt6.QtWidgets import (QMainWindow, QWidget, QMessageBox, QVBoxLayout, QPushButton, QLabel,
                             QFileDialog, QHBoxLayout, QInputDialog, QListWidget, QApplication, QMenu, QSlider,
                             QTextEdit, QLineEdit)
from PyQt6.QtGui import QFont, QAction, QActionGroup
from PyQt6.QtCore import Qt, QTimer, QUrl, QSettings, QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup, \
    QParallelAnimationGroup, QObject, pyqtSignal

from PyQt6.QtMultimedia import QSoundEffect

# 获取当前脚本的绝对路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
# 将项目的根目录添加到 sys.path
sys.path.append(project_root)
from src.core.simulator import AmazonsSimulator, WHITE_AMAZON, BLACK_AMAZON, OBSTACLE, EMPTY
from src.gui.amazon_board_widget import BoardWidget, AWAITING_PIECE_SELECTION, AWAITING_MOVE_DESTINATION, \
    AWAITING_ARROW_DESTINATION


from src.ai.amazon_ai_agent import AmazonAIAgent

class AmazonsMainWindow(QMainWindow):
    """
    亚马逊棋游戏主窗口
    """
    # 定义玩家类型常量
    PLAYER_TYPE_HUMAN = 'human'
    PLAYER_TYPE_AI_MCTS = 'mcts'  # 保留 MCTS
    PLAYER_TYPE_AI_MCTS2 = 'mcts_test'  # 保留 MCTS
    PLAYER_TYPE_AI_KATAAMAZON = 'kataAmazon'  #

    def __init__(self, simulator: AmazonsSimulator):
        super().__init__()
        self.simulator = simulator
        self.animation_group = None

        self.move_history = []  # 正确：初始化为空列表
        self.board_widget = None  # 将在init_ui中初始化

        self.black_modes = self.PLAYER_TYPE_HUMAN
        self.white_modes = self.PLAYER_TYPE_HUMAN
        # AI
        self.black_ai_agent = AmazonAIAgent(self)
        self.white_ai_agent = AmazonAIAgent(self)
        self.black_ai_agent.move_calculated.connect(self.execute_ai_move)
        self.white_ai_agent.move_calculated.connect(self.execute_ai_move)
        # 主题设置
        self.current_color_scheme = 'BW'  # 默认经典黑白主题
        self.setWindowTitle("亚马逊棋")

        self.init_ui()
        self.start_new_game()

    def start_new_game(self):
        if not self.confirm_action("开始新游戏"):
            return

        self.simulator.reset()
        self.board_widget.reset_selection()
        self.board_widget.set_last_turn(None)
        self.board_widget.set_color_scheme(self.current_color_scheme)
        self.move_history.clear()
        self.board_widget.update()
        self.board_widget.setEnabled(True)

        # 将玩家模式重置为人类
        self.black_modes = self.PLAYER_TYPE_HUMAN
        self.white_modes = self.PLAYER_TYPE_HUMAN
        # 更新菜单选项的选中状态
        self.black_human_action.setChecked(True)
        self.white_human_action.setChecked(True)
        self.update_status()

        self.black_ai_agent.clear_board()
        self.white_ai_agent.clear_board()

        # 检查是否轮到 AI 先手，如果是则触发AI下棋
        if self.is_ai_turn():
            self.start_ai_turn()

    def set_coord_display_mode(self, mode_key: str):
        """
        设置坐标显示模式并更新 UI。
        :param mode_key: 'NONE', 'EDGE', 'GRID'
        """
        # 假设 BoardWidget 的常量已被引入或定义

        mode_map = {
            'NONE': self.board_widget.COORD_MODE_NONE,
            'EDGE': self.board_widget.COORD_MODE_EDGE,
            'GRID': self.board_widget.COORD_MODE_GRID,
        }

        mode_name_map = {
            'NONE': '关闭',
            'EDGE': '棋盘边缘',
            'GRID': '棋盘格子',
        }

        mode_int = mode_map.get(mode_key, self.board_widget.COORD_MODE_NONE)

        if self.board_widget:
            self.board_widget.set_coord_mode(mode_int)
            self.statusBar().showMessage(f"坐标显示模式已切换为：{mode_name_map.get(mode_key)}", 3000)

    def on_turn_made(self, start_pos, move_pos, arrow_pos):
        """
        """
        if self.simulator.game_over or not self.board_widget.isEnabled():
            return

        # 如果当前回合是 AI，忽略人类点击
        if self.is_ai_turn():
            return

        # 将 source 参数传递给动画完成后的回调
        callback = lambda: self.post_animation_update(start_pos, move_pos, arrow_pos)
        self.run_full_turn_animation_sequence(start_pos, move_pos, arrow_pos, self.simulator.current_player, callback)

    def undo_move(self):
        """
        处理悔棋操作，人机模式下连续悔两步。
        """
        if self.simulator.game_over:
            self.statusBar().showMessage("游戏已结束，无法悔棋。")
            return

        # 判断是否为人人
        is_human_vs_human = (
                self.black_modes == self.PLAYER_TYPE_HUMAN and
                self.white_modes == self.PLAYER_TYPE_HUMAN
        )

        # ========== 执行第一次悔棋 ==========
        if self.simulator.undo():
            if self.move_history:
                last_turn = self.move_history.pop()

                # 根据悔掉的是谁的回合，回退对应 AI 的内部棋盘
                last_player = -self.simulator.current_player  # undo 后 current_player 已反转
                if last_player == BLACK_AMAZON:
                    self.black_ai_agent.undo_board()
                else:
                    self.white_ai_agent.undo_board()

            # ====== 如果是人机对战，要再悔一步跳过 AI ======
            if not is_human_vs_human:
                if self.simulator.undo():
                    if self.move_history:
                        last_turn = self.move_history.pop()
                        last_player = -self.simulator.current_player
                        if last_player == BLACK_AMAZON:
                            self.black_ai_agent.undo_board()
                        else:
                            self.white_ai_agent.undo_board()

                    self.statusBar().showMessage("已连续悔棋，跳过 AI 回合。")
                else:
                    self.statusBar().showMessage("无法连续悔棋，已是开局。")

            self.statusBar().showMessage("已执行悔棋。")
        else:
            self.statusBar().showMessage("无法悔棋，已是开局。")
            return

        # ========= UI 更新 ==========
        self.board_widget.reset_selection()

        if self.move_history:
            self.board_widget.set_last_turn(self.move_history[-1])
        else:
            self.board_widget.set_last_turn(None)

        self.board_widget.update()
        self.update_status()

        # ========== 如果悔棋后轮到AI，则继续AI ==========
        if self.is_ai_turn():
            self.start_ai_turn()

    def init_ui(self):
        """初始化主窗口的用户界面布局和控件。"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_h_layout = QHBoxLayout(central_widget)

        self.left_controls_panel = QWidget()
        left_v_layout = QVBoxLayout(self.left_controls_panel)
        self.left_controls_panel.setFixedWidth(220)

        #添加状态标签的样式
        left_v_layout.addStretch(1)
        self.status_label = QLabel("欢迎！")
        font = QFont("Helvetica", 14)
        font.setBold(True)
        self.status_label.setFont(font)
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)  # 文本居中
        left_v_layout.addWidget(self.status_label, stretch=5)
        left_v_layout.addStretch(1)
        # ----------------------------------

        right_board_panel = QWidget()
        right_v_layout = QVBoxLayout(right_board_panel)
        self.board_widget = BoardWidget(self.simulator, color_scheme=self.current_color_scheme)
        self.board_widget.mouse_genmove_completed.connect(self.on_turn_made)
        self.board_widget.game_over_signal.connect(self.show_game_over_message)
        right_v_layout.addWidget(self.board_widget)

        main_h_layout.addWidget(right_board_panel)
        main_h_layout.addWidget(self.left_controls_panel)

        self.create_menus()
        self.statusBar().showMessage("欢迎来到亚马逊棋！")
        self.adjustSize()

    def create_menus(self):
        """创建顶部菜单栏"""
        menu_bar = self.menuBar()

        # --- 游戏菜单 ---
        game_menu = menu_bar.addMenu("游戏(&G)")

        # 新游戏
        new_game_action = QAction("新游戏", self)
        new_game_action.triggered.connect(lambda: self.start_new_game())
        new_game_action.setShortcut("Ctrl+N")
        game_menu.addAction(new_game_action)

        game_menu.addSeparator()

        # --- 黑方玩家类型子菜单 (黑棋 = BLACK_AMAZON) ---
        black_player_menu = QMenu("黑方", self)
        black_player_group = QActionGroup(self)
        black_player_group.setExclusive(True)

        self.black_human_action = QAction("人类", self, checkable=True)
        self.black_human_action.setChecked(True)
        self.black_human_action.triggered.connect(lambda: self.set_player_mode(BLACK_AMAZON, self.PLAYER_TYPE_HUMAN))
        black_player_group.addAction(self.black_human_action)
        black_player_menu.addAction(self.black_human_action)

        # AI 子菜单
        black_ai_menu = QMenu("AI", self)
        # 1. MCTS(c++)
        black_ai_mcts_action = QAction("MCTS★", self, checkable=True)
        black_ai_mcts_action.triggered.connect(lambda: self.set_player_mode(BLACK_AMAZON, self.PLAYER_TYPE_AI_MCTS))
        black_player_group.addAction(black_ai_mcts_action)
        black_ai_menu.addAction(black_ai_mcts_action)

        #  MCTS_test(c++)
        black_ai_mcts_test_action = QAction("MCTS_test★", self, checkable=True)
        black_ai_mcts_test_action.triggered.connect(
            lambda: self.set_player_mode(BLACK_AMAZON, self.PLAYER_TYPE_AI_MCTS2))
        black_player_group.addAction(black_ai_mcts_test_action)
        black_ai_menu.addAction(black_ai_mcts_test_action)

        #  kataAmazon
        black_ai_kataAmazon_action = QAction("kataAmazon★★", self, checkable=True)
        black_ai_kataAmazon_action.triggered.connect(
            lambda: self.set_player_mode(BLACK_AMAZON, self.PLAYER_TYPE_AI_KATAAMAZON))
        black_player_group.addAction(black_ai_kataAmazon_action)
        black_ai_menu.addAction(black_ai_kataAmazon_action)

        black_player_menu.addMenu(black_ai_menu)
        game_menu.addMenu(black_player_menu)

        # --- 白方玩家类型子菜单 (白棋 = WHITE_AMAZON) ---
        white_player_menu = QMenu("白方", self)
        white_player_group = QActionGroup(self)
        white_player_group.setExclusive(True)

        self.white_human_action = QAction("人类", self, checkable=True)
        self.white_human_action.setChecked(True)
        self.white_human_action.triggered.connect(lambda: self.set_player_mode(WHITE_AMAZON, self.PLAYER_TYPE_HUMAN))
        white_player_group.addAction(self.white_human_action)
        white_player_menu.addAction(self.white_human_action)

        # AI 子菜单
        white_ai_menu = QMenu("AI", self)
        # 1. MCTS(c++)
        white_ai_mcts_action = QAction("MCTS★", self, checkable=True)
        white_ai_mcts_action.triggered.connect(lambda: self.set_player_mode(WHITE_AMAZON, self.PLAYER_TYPE_AI_MCTS))
        white_player_group.addAction(white_ai_mcts_action)
        white_ai_menu.addAction(white_ai_mcts_action)

        #
        white_ai_mcts_test_action = QAction("MCTS_test★", self, checkable=True)
        white_ai_mcts_test_action.triggered.connect(
            lambda: self.set_player_mode(WHITE_AMAZON, self.PLAYER_TYPE_AI_MCTS2))
        white_player_group.addAction(white_ai_mcts_test_action)
        white_ai_menu.addAction(white_ai_mcts_test_action)

        white_ai_kataAmazon_action = QAction("kataAmazon★★", self, checkable=True)
        white_ai_kataAmazon_action.triggered.connect(
            lambda: self.set_player_mode(WHITE_AMAZON, self.PLAYER_TYPE_AI_KATAAMAZON))
        white_player_group.addAction(white_ai_kataAmazon_action)
        white_ai_menu.addAction(white_ai_kataAmazon_action)

        white_player_menu.addMenu(white_ai_menu)
        game_menu.addMenu(white_player_menu)

        game_menu.addSeparator()


        # --- 悔棋、认输 ---
        self.undo_action = QAction("悔棋", self)
        self.undo_action.triggered.connect(self.undo_move)
        self.undo_action.setShortcut("Ctrl+Z")
        game_menu.addAction(self.undo_action)

        self.resign_action = QAction("认输", self)
        self.resign_action.triggered.connect(self.resign_game)
        self.resign_action.setShortcut("Ctrl+R")
        game_menu.addAction(self.resign_action)

        game_menu.addSeparator()

        self.settings_action = QAction("设置...", self)
        self.settings_action.triggered.connect(self.open_settings)
        game_menu.addAction(self.settings_action)

        game_menu.addSeparator()

        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        exit_action.setShortcut("Ctrl+Q")
        game_menu.addAction(exit_action)

        # --------------------显示菜单 ---------------
        display_menu = menu_bar.addMenu("显示(&V)")

        # --- 主题设置子菜单 ---
        theme_menu = QMenu("主题设置(&T)", self)
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)

        # 经典黑白主题
        self.theme_bw_action = QAction("纸落云烟", self, checkable=True)
        self.theme_bw_action.setChecked(True)
        self.theme_bw_action.triggered.connect(lambda: self.set_color_scheme('BW'))
        theme_group.addAction(self.theme_bw_action)
        theme_menu.addAction(self.theme_bw_action)

        # 红蓝对决主题
        self.theme_rb_action = QAction("桃蹊蒼茫", self, checkable=True)
        self.theme_rb_action.triggered.connect(lambda: self.set_color_scheme('RB'))
        theme_group.addAction(self.theme_rb_action)
        theme_menu.addAction(self.theme_rb_action)

        # 主题
        self.theme_gs_action = QAction("杳霭流玉", self, checkable=True)
        self.theme_gs_action.triggered.connect(lambda: self.set_color_scheme('GS'))
        theme_group.addAction(self.theme_gs_action)
        theme_menu.addAction(self.theme_gs_action)

        # 主题
        self.theme_ps_action = QAction("流绪微梦", self, checkable=True)
        self.theme_ps_action.triggered.connect(lambda: self.set_color_scheme('PS'))
        theme_group.addAction(self.theme_ps_action)
        theme_menu.addAction(self.theme_ps_action)

        display_menu.addMenu(theme_menu)  # 添加主题设置到显示菜单

        display_menu.addSeparator()

        # --- 坐标显示子菜单 ---
        coord_menu = QMenu("坐标显示", self)
        coord_group = QActionGroup(self)
        coord_group.setExclusive(True)

        # 1. 关闭坐标
        coord_none_action = QAction("关闭", self, checkable=True)
        coord_none_action.triggered.connect(lambda: self.set_coord_display_mode('NONE'))
        coord_none_action.setChecked(True)  # 默认选中
        coord_group.addAction(coord_none_action)
        coord_menu.addAction(coord_none_action)

        # 2. 边缘坐标 (默认选中)
        coord_edge_action = QAction("棋盘边缘", self, checkable=True)
        coord_edge_action.triggered.connect(lambda: self.set_coord_display_mode('EDGE'))
        coord_group.addAction(coord_edge_action)
        coord_menu.addAction(coord_edge_action)

        # 3. 格子坐标
        coord_grid_action = QAction("棋盘格子", self, checkable=True)
        coord_grid_action.triggered.connect(lambda: self.set_coord_display_mode('GRID'))
        coord_group.addAction(coord_grid_action)
        coord_menu.addAction(coord_grid_action)

        display_menu.addMenu(coord_menu)

        # -------------------- 介绍菜单 --------------------
        help_menu = menu_bar.addMenu("介绍(&I)")  # I for Introduction

        # 1. 游戏介绍
        intro_game_action = QAction("游戏介绍", self)
        intro_game_action.triggered.connect(self.show_game_introduction)
        help_menu.addAction(intro_game_action)

        # 2. 规则说明
        rules_action = QAction("游戏规则", self)
        rules_action.triggered.connect(self.show_game_rules)
        help_menu.addAction(rules_action)

        help_menu.addSeparator()

        # 3. AI算法说明
        ai_intro_action = QAction("AI算法介绍", self)
        ai_intro_action.triggered.connect(self.show_ai_introduction)
        help_menu.addAction(ai_intro_action)

        # 4. 快捷键说明
        shortcut_action = QAction("快捷键", self)
        shortcut_action.triggered.connect(self.show_shortcuts)
        help_menu.addAction(shortcut_action)

        help_menu.addSeparator()

        # 5. 关于
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    # 在类中添加显示介绍信息的方法
    def show_game_introduction(self):
        """显示游戏介绍"""
        introduction_text = """
        <h2>亚马逊棋 (Game of the Amazons)</h2>

        <h3>游戏简介</h3>
        <p>亚马逊棋是一种双人完全信息博弈游戏，由Walter Zamkauskas于1988年发明。</p>
        <p>游戏在10x10的棋盘上进行，每位玩家有4个亚马逊棋子。</p>
        <p>目标是封锁对手的所有棋子，使其无法移动。</p>

        <h3>游戏特点</h3>
        <ul>
            <li>完全信息博弈：双方都能看到完整的棋盘状态</li>
            <li>零和博弈：一方胜利则另一方失败</li>
            <li>高分支因子：每步棋的可能走法很多</li>
            <li>公认的困难游戏：直到2000年才被证明是先手必胜</li>
        </ul>
        """

        QMessageBox.information(self, "游戏介绍", introduction_text)

    def show_game_rules(self):
        """显示游戏规则"""
        rules_text = """
        <h2>游戏规则</h2>

        <h3>棋盘和棋子</h3>
        <p>• 10x10方格棋盘</p>
        <p>• 黑方和白方各有4个亚马逊棋子</p>
        <p>• 初始布局如图中所示</p>

        <h3>走子规则</h3>
        <p>每回合必须完成两个动作：</p>
        <p><b>1. 移动棋子：</b></p>
        <p>   • 可以像国际象棋的后（皇后）一样移动（横、竖、斜线任意距离）</p>
        <p>   • 不能穿过其他棋子或障碍</p>

        <p><b>2. 放置障碍：</b></p>
        <p>   • 从移动后的位置，像皇后一样射出"箭"（放置障碍）</p>
        <p>   • 障碍永久占据该格子，不能再被移动通过</p>

        <h3>胜负条件</h3>
        <p>• 当一方无法移动任何棋子时，该方输掉比赛</p>
        <p>• 最后成功移动的一方获胜</p>
        """

        QMessageBox.information(self, "游戏规则", rules_text)

    def show_ai_introduction(self):
        """显示AI算法介绍"""
        ai_text = """
        <h2>AI算法介绍</h2>

        <h3>MCTS (蒙特卡洛树搜索)★</h3>
        <p>python版本要求:3.11.5/3.13.3/自行编译</p>
        <p>• 通过随机模拟探索游戏树</p>
        <p>• 平衡探索与利用</p>
        <p>• 适合高分支因子的游戏</p>

        <h3>KataAmazon (基于katago的AI)★★</h3>
        <p>• 使用katago框架的专业AI</p>
        <p>• 性能更强但计算更复杂</p>

        <h3>AI难度等级</h3>
        <p>★ 基础AI - 适合新手练习</p>
        <p>★★ 中级AI - 有一定挑战性</p>
        <p>★★★ 高级AI - 极具挑战性</p>
        """

        QMessageBox.information(self, "AI算法介绍", ai_text)

    def show_shortcuts(self):
        """显示快捷键"""
        shortcuts_text = """
        <h2>快捷键</h2>

        <h3>游戏操作</h3>
        <p><b>Ctrl+N</b> - 新游戏</p>
        <p><b>Ctrl+Z</b> - 悔棋</p>
        <p><b>Ctrl+R</b> - 认输</p>
        <p><b>Ctrl+Q</b> - 退出游戏</p>

        <h3>棋盘操作</h3>
        <p><b>鼠标左键</b> - 选择棋子/放置障碍</p>
        <p><b>鼠标右键</b> - 取消选择</p>
        <p><b>ESC</b> - 返回主菜单</p>
        """

        QMessageBox.information(self, "快捷键", shortcuts_text)

    def show_about_dialog(self):
        """显示关于对话框"""
        about_text = f"""
        <h2>亚马逊棋AI对战平台</h2>

        <p><b>版本：</b>1.0.0</p>
        <p><b>开发:</b> Zhifan Xu, Lvxi Liu (徐志凡，刘律希)</p>
        <p><b>团队:</b> Shenyang University of Technology (沈阳工业大学)</p>

        <h3>功能特点</h3>
        <p>• 支持人机对战和机机对战</p>
        <p>• 多种AI算法可选</p>
        <p>• 多种棋盘主题</p>

        <p>© 2026. 保留所有权利。</p>
        """

        QMessageBox.about(self, "关于", about_text)

    # 如果需要更美观的对话框，可以使用自定义对话框
    def show_introduction_dialog(self):
        """显示包含多个标签页的介绍对话框"""
        from PyQt5.QtWidgets import QDialog, QTabWidget, QTextBrowser, QVBoxLayout

        dialog = QDialog(self)
        dialog.setWindowTitle("游戏介绍")
        dialog.resize(600, 500)

        # 创建标签页
        tab_widget = QTabWidget()

        # 游戏介绍标签
        intro_browser = QTextBrowser()
        intro_browser.setHtml(self.get_introduction_html())
        tab_widget.addTab(intro_browser, "游戏介绍")

        # 规则标签
        rules_browser = QTextBrowser()
        rules_browser.setHtml(self.get_rules_html())
        tab_widget.addTab(rules_browser, "游戏规则")

        # AI介绍标签
        ai_browser = QTextBrowser()
        ai_browser.setHtml(self.get_ai_intro_html())
        tab_widget.addTab(ai_browser, "AI算法")

        # 布局
        layout = QVBoxLayout()
        layout.addWidget(tab_widget)
        dialog.setLayout(layout)

        dialog.exec_()




    def set_player_mode(self, side, player_type):
        """
        设置某一边的玩家类型
        """
        if side == BLACK_AMAZON:
            self.black_modes = player_type
            side_text = "黑方"
            if player_type == self.PLAYER_TYPE_AI_KATAAMAZON:
                self.black_ai_agent.init_ai_engine()
        else:
            self.white_modes = player_type
            side_text = "白方"
            if player_type == self.PLAYER_TYPE_AI_KATAAMAZON:
                self.white_ai_agent.init_ai_engine()

        if player_type == self.PLAYER_TYPE_HUMAN:
            mode_text = "人类"
        else:
            mode_text = "AI"


        self.statusBar().showMessage(f"已将 {side_text} 设置为 {mode_text} 玩家。", 3000)


        if self.simulator.game_over:
            self.show_game_over_message()
        else:
            # 检查是否需要触发 AI 下棋
            if self.is_ai_turn():
                self.start_ai_turn()

    def set_color_scheme(self, scheme_key: str):
        """
        设置棋盘的主题配色方案。
        """
        if self.board_widget:
            self.board_widget.set_color_scheme(scheme_key)
            self.current_color_scheme = scheme_key

            # 更新菜单状态
            scheme_names = {
                'BW': '纸落云烟',
                'RB': '桃蹊蒼茫',
                'GS': '杳霭流玉',
                'PS': '流绪微梦'
            }
            scheme_name = scheme_names.get(scheme_key, '未知主题')
            self.statusBar().showMessage(f"已切换到主题：{scheme_name}", 3000)

            # 确保 QActionGroup 机制下，这里仅选中当前主题
            actions = {
                'BW': self.theme_bw_action,
                'RB': self.theme_rb_action,
                'GS': self.theme_gs_action,
                'PS': self.theme_ps_action
            }

            for action_key, action in actions.items():
                action.setChecked(action_key == scheme_key)

    def is_ai_turn(self):
        """
        判断当前回合是否轮到 AI 下棋。
        """
        # 获取当前玩家对应的模式
        if self.simulator.current_player == BLACK_AMAZON:
            current_mode = self.black_modes
        else:
            current_mode = self.white_modes

        # 如果模式不是“人类”，则认为是 AI
        return current_mode != self.PLAYER_TYPE_HUMAN

    def update_status(self):
        """更新状态显示"""
        player_name = "黑方" if self.simulator.current_player == BLACK_AMAZON else "白方"

        if self.is_ai_turn():
            self.status_label.setText(f"轮到 {player_name} (AI) 落子。")
        else:
            self.status_label.setText(f"轮到 {player_name} (人类) 落子。")

    def show_game_over_message(self, message=None):
        """显示游戏结束消息"""
        self.board_widget.setEnabled(False)  # 游戏结束，禁用棋盘
        self.update_status()
        if message:
            QMessageBox.information(self, "游戏结束", message)
        else:
            winner_name = "黑方" if self.simulator.winner == BLACK_AMAZON else "白方"
            QMessageBox.information(self, "游戏结束", f"游戏结束！{winner_name}获胜！")

    def confirm_action(self, action_name="此操作"):
        """在执行可能中断游戏的操作前，向用户请求确认。"""
        if not self.simulator.game_over and len(self.simulator.history) > 1:
            reply = QMessageBox.question(self, '确认操作', f'当前对局尚未结束，您确定要{action_name}吗？',
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            return reply == QMessageBox.StandardButton.Yes
        return True

    def open_settings(self):
        """打开设置对话框"""
        # 更新菜单状态
        scheme_names = {
            'BW': '纸落云烟',
            'RB': '桃蹊蒼茫',
            'GS': '杳霭流玉',
            'PS': '流绪微梦'
        }
        current_theme = scheme_names.get(self.current_color_scheme, '未知主题')
        QMessageBox.information(self, "设置",
                                f"当前主题：{current_theme}\n\n"
                                f"您可以在「游戏」菜单的「主题设置」中切换不同的配色方案。\n\n"
                                )


    def resign_game(self):
        """处理认输操作。"""
        # 检查是否在游戏中
        if self.simulator.game_over or len(self.move_history) == 0:
            QMessageBox.information(self, "提示", "游戏尚未开始或已结束，无法认输。")
            return

        player_name = "黑方" if self.simulator.current_player == BLACK_AMAZON else "白方"
        reply = QMessageBox.question(self, '确认认输', f'轮到 {player_name}，您确定要认输吗？',
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            # 设置游戏结束状态，获胜者是对方
            self.simulator.game_over = True
            self.simulator.winner = -self.simulator.current_player
            winner_name = "黑方" if self.simulator.winner == BLACK_AMAZON else "白方"
            self.handle_game_over(f"{player_name}已认输，{winner_name}获胜！")

    def handle_game_over(self, message=None):
        """
        处理游戏结束的逻辑。
        """
        if message:
            self.show_game_over_message(message)
        else:
            winner_name = "黑方" if self.simulator.winner == BLACK_AMAZON else "白方"
            self.show_game_over_message(f"游戏结束！{winner_name}获胜！")


    def post_animation_update(self, start_pos, move_pos, arrow_pos):
        """
        动画完成后的核心处理逻辑。
        """
        if self.simulator.current_player == BLACK_AMAZON:
            self.white_ai_agent.update_engine_board(self.simulator.current_player, start_pos, move_pos, arrow_pos)
        else:
            self.black_ai_agent.update_engine_board(self.simulator.current_player, start_pos, move_pos, arrow_pos)

        if self.simulator.execute_turn(start_pos, move_pos, arrow_pos):
            self.move_history.append((start_pos, move_pos, arrow_pos))
            self.board_widget.set_last_turn((start_pos, move_pos, arrow_pos))

            self.update_status()
            self.board_widget.update()  # 确保在动画结束后立即刷新

            if self.simulator.game_over:
                return 'GAME_OVER'

            # 玩家落子后，检查是否轮到 AI 下棋
            if self.is_ai_turn():
                self.start_ai_turn()
                return 'AI_TURN'

            self.board_widget.setEnabled(True)  # 恢复人类输入
            return 'HUMAN_TURN'
        else:
            QMessageBox.warning(self, "无效操作", "此操作不符合规则!")
            self.board_widget.setEnabled(True)  # 恢复人类输入
            return 'MOVE_FAILED'

    def run_full_turn_animation_sequence(self, start_pos, move_pos, arrow_pos, piece_type, on_finished_callback):
        # 动画速度控制参数
        piece_move_duration = 700  # 棋子移动动画持续时间
        piece_settle_duration = 350  # 棋子缩放归位动画持续时间
        arrow_move_duration = 550  # 箭移动动画持续时间
        arrow_land_duration = 300  # 箭落地动画持续时间
        arrow_shrink_duration = 0  # 箭瞬间缩小动画持续时间

        if self.black_modes != self.PLAYER_TYPE_HUMAN and self.white_modes != self.PLAYER_TYPE_HUMAN:
            piece_move_duration = 200  # 棋子移动动画持续时间
            piece_settle_duration = 100  # 棋子缩放归位动画持续时间
            arrow_move_duration = 100  # 箭移动动画持续时间
            arrow_land_duration = 100  # 箭落地动画持续时间
            arrow_shrink_duration = 0  # 箭瞬间缩小动画持续时间

        # 在动画开始前，清除上一步留下的路径箭头。
        self.board_widget.set_last_turn(None)

        # 在动画开始前，立即重置棋盘的选择状态。
        self.board_widget.reset_selection()

        self.board_widget.setEnabled(False)
        self.board_widget.is_animating = True
        self.board_widget.hidden_pieces.add(start_pos)

        self.board_widget.anim_piece_scale = 1.15
        self.board_widget.anim_offset_factor = 1.0
        self.board_widget.anim_glow_radius_factor = 1.6
        self.board_widget.anim_arrow_scale = 0.0

        # 1. 创建棋子移动动画
        piece_anim = QPropertyAnimation(self.board_widget, b'anim_piece_pos')
        piece_anim.setDuration(piece_move_duration)
        piece_anim.setStartValue(self.board_widget.get_coord_from_row_col(start_pos[0], start_pos[1]))
        piece_anim.setEndValue(self.board_widget.get_coord_from_row_col(move_pos[0], move_pos[1]))
        piece_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # 2a. 缩小动画
        settle_group = QParallelAnimationGroup(self)
        scale_anim = QPropertyAnimation(self.board_widget, b'anim_piece_scale')
        scale_anim.setDuration(piece_settle_duration)
        scale_anim.setStartValue(1.15)
        scale_anim.setEndValue(1.0)
        scale_anim.setEasingCurve(QEasingCurve.Type.OutQuad)

        # 2b. 归位（偏移消失）动画
        offset_anim = QPropertyAnimation(self.board_widget, b'anim_offset_factor')
        offset_anim.setDuration(piece_settle_duration)
        offset_anim.setStartValue(1.0)
        offset_anim.setEndValue(0.0)
        offset_anim.setEasingCurve(QEasingCurve.Type.OutQuad)

        glow_shrink_anim = QPropertyAnimation(self.board_widget, b'anim_glow_radius_factor')
        glow_shrink_anim.setDuration(piece_settle_duration)
        glow_shrink_anim.setStartValue(1.6)
        glow_shrink_anim.setEndValue(0.0)
        glow_shrink_anim.setEasingCurve(QEasingCurve.Type.InQuad)

        settle_group.addAnimation(scale_anim)
        settle_group.addAnimation(offset_anim)
        settle_group.addAnimation(glow_shrink_anim)

        # 3. 创建障碍发射动画
        arrow_anim = QPropertyAnimation(self.board_widget, b'anim_arrow_pos')
        arrow_anim.setDuration(arrow_move_duration)
        arrow_anim.setStartValue(self.board_widget.get_coord_from_row_col(move_pos[0], move_pos[1]))
        arrow_anim.setEndValue(self.board_widget.get_coord_from_row_col(arrow_pos[0], arrow_pos[1]))
        arrow_anim.setEasingCurve(QEasingCurve.Type.OutQuad)

        # 4. 定义飞行的"小尺寸"和落地动画
        flying_scale = 0.5

        # 4a. 新增一个"瞬间缩小"的动画，在飞行前执行
        arrow_shrink_anim = QPropertyAnimation(self.board_widget, b'anim_arrow_scale')
        arrow_shrink_anim.setDuration(arrow_shrink_duration)
        arrow_shrink_anim.setEndValue(flying_scale)

        # 4b. 修改落地动画，使其从"小尺寸"开始
        arrow_land_anim = QPropertyAnimation(self.board_widget, b'anim_arrow_scale')
        arrow_land_anim.setDuration(arrow_land_duration)
        arrow_land_anim.setStartValue(flying_scale)
        arrow_land_anim.setEndValue(1)  # 恢复到正常尺寸
        arrow_land_anim.setEasingCurve(QEasingCurve.Type.OutQuad)

        # 5. 创建动画组并按顺序添加动画
        self.animation_group = QSequentialAnimationGroup(self)
        self.animation_group.addAnimation(piece_anim)
        self.animation_group.addAnimation(settle_group)
        self.animation_group.addAnimation(arrow_shrink_anim)
        self.animation_group.addAnimation(arrow_anim)
        self.animation_group.addAnimation(arrow_land_anim)

        self.board_widget.animation_group = self.animation_group

        def on_group_finished():
            self.board_widget.is_animating = False
            self.board_widget.hidden_pieces.clear()
            self.board_widget.anim_arrow_scale = 1.0
            self.board_widget.animation_group = None

            # on_finished_callback() 会调用 post_animation_update
            next_step = on_finished_callback()

            if next_step == 'GAME_OVER':
                self.handle_game_over()
                self.board_widget.setEnabled(False)
            elif next_step == 'HUMAN_TURN':
                self.board_widget.setEnabled(True)
            elif next_step == 'AI_TURN':
                # AI 回合已在 post_animation_update 中启动
                pass  # 保持禁用，直到 AI 走完
            elif next_step in ['MOVE_FAILED']:
                self.board_widget.setEnabled(True)

        # 连接信号并启动动画组
        self.animation_group.finished.connect(on_group_finished)
        self.animation_group.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def start_ai_turn(self):
        """
        启动AI回合，带有视觉反馈。
        """
        # 1. 改变状态栏提示
        current_player_name = "黑方" if self.simulator.current_player == BLACK_AMAZON else "白方"
        self.status_label.setText(f"{current_player_name} (AI) 正在思考...")
        self.board_widget.setEnabled(False)  # 禁用交互
        self.board_widget.repaint()

        # 2. 延迟启动 AI 计算，避免阻塞 UI
        QTimer.singleShot(100, self.start_ai_calculation)

    def start_ai_calculation(self):
        """
        执行AI的下棋操作。
        """
        # 选择当前玩家的模式和 agent
        if self.simulator.current_player == BLACK_AMAZON:
            current_player_mode = self.black_modes
            current_agent = self.black_ai_agent
        else:
            current_player_mode = self.white_modes
            current_agent = self.white_ai_agent

        # 根据玩家类型启动 AI 计算
        if current_player_mode == self.PLAYER_TYPE_AI_MCTS:
            current_agent.start_thread_ai_calculation('mcts')
        elif current_player_mode == self.PLAYER_TYPE_AI_MCTS2:
            current_agent.start_thread_ai_calculation('mcts_test')
        elif current_player_mode == self.PLAYER_TYPE_AI_KATAAMAZON:
            current_agent.start_thread_ai_calculation('kataAmazon')

    def execute_ai_move(self, result):
        """
        处理AI计算出的最佳移动，执行下棋并更新UI。
        """
        best_res = result

        if best_res is None or best_res == -1:
            self.statusBar().showMessage("AI 计算失败。")
            return

        if best_res == -2:
            self.simulator.game_over = True
            self.simulator.winner = -self.simulator.current_player
            winner_name = "黑方" if self.simulator.winner == BLACK_AMAZON else "白方"
            player_name = "黑方" if self.simulator.current_player == BLACK_AMAZON else "白方"
            self.handle_game_over(f"{player_name}已认输，{winner_name}获胜！")
            return


        start_pos = (best_res.best_pos_from // self.simulator.size, best_res.best_pos_from % self.simulator.size)
        move_pos = (best_res.best_pos_to // self.simulator.size, best_res.best_pos_to % self.simulator.size)
        arrow_pos = (best_res.best_pos_stone // self.simulator.size, best_res.best_pos_stone % self.simulator.size)

        win_pro_str = f"{best_res.win_pro :.2f}%"
        select_pro_str = f"{best_res.select_pro:.4f}"
        player_name = "黑方" if self.simulator.current_player == BLACK_AMAZON else "白方"
        # 构建状态栏信息
        info_message = (
            f"{player_name}"
            f"AI 走法: 胜率={win_pro_str} | "
            f"搜索次数={int(best_res.max_apt)} | "
            f"局面估值={select_pro_str}"
        )
        self.statusBar().showMessage(info_message)

        # 使用动画执行 AI 的走法
        player_who_moved = self.simulator.current_player
        callback = lambda: self.post_animation_update(start_pos, move_pos, arrow_pos)
        self.run_full_turn_animation_sequence(start_pos, move_pos, arrow_pos, player_who_moved, callback)

        # 动画完成后的逻辑会由 on_group_finished -> post_animation_update 处理


if __name__ == '__main__':
    app = QApplication(sys.argv)
    try:
        print("正在初始化模拟器...")
        simulator = AmazonsSimulator(size=10)
        print("模拟器初始化成功")
        print("正在创建主窗口...")
        main_window = AmazonsMainWindow(simulator)
        print("主窗口创建成功")
        main_window.show()
        print("程序启动成功")
        sys.exit(app.exec())
    except Exception as e:
        print(f"应用程序错误: {e}")
        import traceback

        traceback.print_exc()