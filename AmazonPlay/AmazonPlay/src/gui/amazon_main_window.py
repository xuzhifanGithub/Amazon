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

    def __init__(self, simulator: AmazonsSimulator):
        super().__init__()
        self.simulator = simulator
        self.settings = {}
        self.animation_group = None
        self.is_paused = False
        self.last_turn_details = None

        self.move_history = []  # 正确：初始化为空列表
        self.board_widget = None  # 将在init_ui中初始化

        # --- 玩家模式设置 ---
        self.player_modes = {
            'black': self.PLAYER_TYPE_HUMAN,
            'white': self.PLAYER_TYPE_HUMAN
        }

        # --- AI 代理 ---
        self.ai_agent = AmazonAIAgent(self)
        self.ai_agent.move_calculated.connect(self.handle_ai_move)

        # --- 主题设置 ---
        self.current_color_scheme = 'BW'  # 默认经典黑白主题

        self.load_app_settings()
        self.setup_sound()
        self.setWindowTitle("亚马逊棋")
        self.init_ui()
        self.update_ui_from_settings()
        self.start_new_game('hvh')

    def start_new_game(self, mode='hvh', human_color=None):
        if not self.confirm_action("开始新游戏"):
            return

        self.is_paused = False
        self.simulator.reset()
        self.board_widget.reset_selection()
        self.board_widget.set_last_turn(None)
        self.board_widget.set_color_scheme(self.current_color_scheme)
        self.move_history.clear()
        self.board_widget.update()
        self.board_widget.setEnabled(True)

        # 将玩家模式重置为人类
        self.player_modes['black'] = self.PLAYER_TYPE_HUMAN
        self.player_modes['white'] = self.PLAYER_TYPE_HUMAN
        # 更新菜单选项的选中状态
        self.black_human_action.setChecked(True)
        self.white_human_action.setChecked(True)

        self.update_status()

        # 检查是否轮到 AI 先手，如果是则触发AI下棋
        if self.is_ai_turn():
            self.start_ai_turn()

    def on_turn_made(self, start_pos, move_pos, arrow_pos, source='human'):
        """
        接收一个 source 参数来区分走法来源。
        """
        if self.simulator.game_over or not self.board_widget.isEnabled():
            return

        # 如果当前回合是 AI，忽略人类点击
        if self.is_ai_turn():
            return

        player_who_moved = self.simulator.current_player
        # 将 source 参数传递给动画完成后的回调
        callback = lambda: self.post_animation_update(start_pos, move_pos, arrow_pos, source)
        self.run_full_turn_animation_sequence(start_pos, move_pos, arrow_pos, player_who_moved, callback)

    def undo_move(self):
        """
        处理悔棋操作，人机模式下连续悔两步。
        """
        # 1. 检查游戏是否已结束
        if self.simulator.game_over:
            self.statusBar().showMessage("游戏已结束，无法悔棋。")
            return

        # 悔棋前判断是否是人机对战
        is_human_vs_human = (self.player_modes['black'] == self.PLAYER_TYPE_HUMAN and
                             self.player_modes['white'] == self.PLAYER_TYPE_HUMAN)

        # 2. 执行第一次悔棋
        if self.simulator.undo():
            if self.move_history:
                self.move_history.pop()

            # 3. 如果不是人类 vs 人类，则再悔一步，以跳过 AI 的回合
            if not is_human_vs_human:
                if self.simulator.undo():
                    if self.move_history:
                        self.move_history.pop()
                    self.statusBar().showMessage("已连续悔棋，跳过AI回合。")
                else:
                    self.statusBar().showMessage("无法连续悔棋，已是开局。")

            self.statusBar().showMessage("已执行悔棋。")
        else:
            self.statusBar().showMessage("无法悔棋，已是开局。")
            return

        # 4. 更新UI状态
        self.board_widget.reset_selection()
        # 根据 move_history 恢复上一步状态
        if self.move_history:
            # 最后一个完整的走法 (start, move, arrow)
            last_turn = self.move_history[-1]
            self.board_widget.set_last_turn(last_turn)
        else:
            self.board_widget.set_last_turn(None)

        self.board_widget.update()
        self.update_status()

        # 5. 如果悔棋后轮到 AI，则触发 AI 下棋
        if self.is_ai_turn():
            self.start_ai_turn()

    def load_app_settings(self):
        """从本地加载应用设置（仅保留play_sound）。"""
        settings = QSettings("MyCompany", "AmazonsGame")
        default_settings = {
            'play_sound': True,
        }
        self.settings = {
            'play_sound': settings.value("play_sound", default_settings['play_sound'], type=bool),
        }
        # 移除加载 color_scheme 的代码

    def save_app_settings(self):
        """保存当前应用设置到本地（仅保留play_sound）。"""
        settings = QSettings("MyCompany", "AmazonsGame")
        settings.setValue('play_sound', self.settings['play_sound'])
        # 移除保存 color_scheme 的代码

    def setup_sound(self):
        """初始化音效。"""
        self.stone_sound = QSoundEffect(self)
        sound_path = os.path.join("src", "assets", "sounds", "Stone.wav")
        if os.path.exists(sound_path):
            self.stone_sound.setSource(QUrl.fromLocalFile(sound_path))
        else:
            print(f"警告: 音效文件 '{sound_path}' 不存在。")

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
        self.board_widget.turn_made.connect(self.on_turn_made)
        self.board_widget.game_over_signal.connect(self.show_game_over_message)
        right_v_layout.addWidget(self.board_widget)

        main_h_layout.addWidget(right_board_panel)
        main_h_layout.addWidget(self.left_controls_panel)

        self.create_menus()
        self.statusBar().showMessage("欢迎来到亚马逊棋！")
        self.adjustSize()

    def create_menus(self):
        """创建顶部菜单栏 - 模仿海克斯棋的菜单结构，并移除多余的 AI 选项。"""
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
        black_ai_mcts_action = QAction("MCTS(c++)", self, checkable=True)
        black_ai_mcts_action.triggered.connect(lambda: self.set_player_mode(BLACK_AMAZON, self.PLAYER_TYPE_AI_MCTS))
        black_player_group.addAction(black_ai_mcts_action)
        black_ai_menu.addAction(black_ai_mcts_action)

        #  MCTS_test(c++)
        black_ai_mcts_test_action = QAction("MCTS_test(c++)", self, checkable=True)
        black_ai_mcts_test_action.triggered.connect(lambda: self.set_player_mode(BLACK_AMAZON, self.PLAYER_TYPE_AI_MCTS2))
        black_player_group.addAction(black_ai_mcts_test_action)
        black_ai_menu.addAction(black_ai_mcts_test_action)

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
        white_ai_mcts_action = QAction("MCTS(c++)", self, checkable=True)
        white_ai_mcts_action.triggered.connect(lambda: self.set_player_mode(WHITE_AMAZON, self.PLAYER_TYPE_AI_MCTS))
        white_player_group.addAction(white_ai_mcts_action)
        white_ai_menu.addAction(white_ai_mcts_action)

        #
        white_ai_mcts_test_action = QAction("MCTS_test(c++)", self, checkable=True)
        white_ai_mcts_test_action.triggered.connect(lambda: self.set_player_mode(WHITE_AMAZON, self.PLAYER_TYPE_AI_MCTS2))
        white_player_group.addAction(white_ai_mcts_test_action)
        white_ai_menu.addAction(white_ai_mcts_test_action)

        white_player_menu.addMenu(white_ai_menu)
        game_menu.addMenu(white_player_menu)

        game_menu.addSeparator()

        # --- 主题设置子菜单 (保留主题切换，但去掉保存功能) ---
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

        game_menu.addMenu(theme_menu)
        game_menu.addSeparator()

        # --- 悔棋、认输 (保持不变) ---
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

    def set_player_mode(self, side, player_type):
        """
        设置某一边的玩家类型
        """
        if side == BLACK_AMAZON:
            self.player_modes['black'] = player_type
            side_text = "黑方"
        else:
            self.player_modes['white'] = player_type
            side_text = "白方"

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
        current_player = self.simulator.current_player
        # 获取当前玩家对应的模式
        if current_player == BLACK_AMAZON:
            current_mode = self.player_modes['black']
        else:
            current_mode = self.player_modes['white']

        # 如果模式不是“人类”，则认为是 AI (即 PLAYER_TYPE_AI_MCTS)
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
        """打开设置对话框（简化版本）"""
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

    def closeEvent(self, event):
        """关闭窗口时，保存设置（仅保存play_sound）。"""
        self.save_app_settings()
        event.accept()

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

    def update_ui_from_settings(self):
        """根据当前的设置更新UI组件。"""
        # 设置保存的主题
        if self.board_widget:
            self.set_color_scheme(self.current_color_scheme)
        self.adjustSize()

    def post_animation_update(self, start_pos, move_pos, arrow_pos, source='human'):
        """
        动画完成后的核心处理逻辑。
        """
        if self.simulator.execute_turn(start_pos, move_pos, arrow_pos):
            self.move_history.append((start_pos, move_pos, arrow_pos))
            if self.settings.get('play_sound', True):
                self.stone_sound.play()
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

        if True:
            piece_move_duration = 200  # 棋子移动动画持续时间
            piece_settle_duration = 100  # 棋子缩放归位动画持续时间
            arrow_move_duration = 100  # 箭移动动画持续时间
            arrow_land_duration = 100  # 箭落地动画持续时间
            arrow_shrink_duration = 0  # 箭瞬间缩小动画持续时间

        # ... (动画开始前的代码保持不变) ...
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
        QTimer.singleShot(100, self.execute_ai_move)

    def execute_ai_move(self):
        """
        执行AI的下棋操作。
        """
        if not self.ai_agent:
            self.statusBar().showMessage("警告：AI 模块未加载。请选择人类玩家。", 5000)
            self.board_widget.setEnabled(True)
            self.update_status()
            return

        current_player_mode = self.player_modes['black'] if self.simulator.current_player == BLACK_AMAZON else \
            self.player_modes['white']

        if current_player_mode == self.PLAYER_TYPE_AI_MCTS:
            self.ai_agent.start_ai_move('mcts')
        elif current_player_mode == self.PLAYER_TYPE_AI_MCTS2:
            self.ai_agent.start_ai_move('mcts_test')



    def handle_ai_move(self, result: tuple):
        """
        处理AI计算出的最佳移动，执行下棋并更新UI。

        预期 result 格式: ((start_row, start_col, move_row, move_col, arrow_row, arrow_col), win_pro, maxApt, select_pro)
        """
        best_move, win_pro, maxApt, select_pro = result

        if best_move == None:
            self.statusBar().showMessage("AI 计算失败。")
            return

        # 1. 皇后起始位置 (From)
        # 格式: (start_row, start_col)
        start_pos = (best_move.From // self.simulator.size, best_move.From % self.simulator.size)

        # 2. 皇后移动目标位置 (To)
        # 格式: (move_row, move_col)
        move_pos = (best_move.To // self.simulator.size, best_move.To % self.simulator.size)

        # 3. 箭射出位置 (Stone)
        # 格式: (arrow_row, arrow_col)
        arrow_pos = (best_move.Stone // self.simulator.size, best_move.Stone % self.simulator.size)

        win_pro_str = f"{win_pro :.2f}%"
        select_pro_str = f"{select_pro:.4f}"
        player_name = "黑方" if self.simulator.current_player == BLACK_AMAZON else "白方"
        # 构建状态栏信息
        info_message = (
            f"{player_name}"
            f"AI 走法: 胜率={win_pro_str} | "
            f"搜索次数={int(maxApt)} | "
            f"局面估值={select_pro_str}"
        )
        self.statusBar().showMessage(info_message)

        # 使用动画执行 AI 的走法
        player_who_moved = self.simulator.current_player
        callback = lambda: self.post_animation_update(start_pos, move_pos, arrow_pos, source='ai')
        self.run_full_turn_animation_sequence(start_pos, move_pos, arrow_pos, player_who_moved, callback)

        # 动画完成后的逻辑会由 on_group_finished -> post_animation_update 处理


if __name__ == '__main__':
    # ... (保持不变) ...
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