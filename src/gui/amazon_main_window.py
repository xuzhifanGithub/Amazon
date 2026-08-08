# src/gui/main_window.py
import re
import os
import sys

import datetime
import logging
from PyQt6.QtWidgets import (QMainWindow, QWidget, QMessageBox, QVBoxLayout, QPushButton, QLabel,
                             QFileDialog, QHBoxLayout, QInputDialog, QListWidget, QApplication, QMenu, QSlider,
                             QTextEdit, QLineEdit, QDialog, QDialogButtonBox)
from PyQt6.QtGui import QFont, QAction, QActionGroup
from PyQt6.QtCore import Qt, QTimer, QUrl, QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup, \
    QParallelAnimationGroup, QObject, pyqtSignal

from PyQt6.QtMultimedia import QSoundEffect

# 获取当前脚本的绝对路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
# 将项目的根目录添加到 sys.path
sys.path.append(project_root)
from src.core.simulator import AmazonsSimulator, WHITE_AMAZON, BLACK_AMAZON, OBSTACLE, EMPTY
from src.core.game_record import export_record, load_record
from src.core.game_session import GameSessionController, SessionState
from src.gui.amazon_board_widget import BoardWidget, AWAITING_PIECE_SELECTION, AWAITING_MOVE_DESTINATION, \
    AWAITING_ARROW_DESTINATION
from src.gui.ai_info_panel import AIInfoPanel

from src.ai.amazon_ai_agent import AmazonAIAgent, mcts_available
from src.ai.engine_manager import EngineManager
from src.ai.amazons_engine import backend_available
from src.ai.ai_profile import AIProfile, load_profile, save_profile
from src.ai.results import AIOutcome, HintCandidate, HintOutcome
from src.config import create_settings
from src.gui.ai_settings_dialog import AISettingsDialog
from src.logging_setup import log_file_path


logger = logging.getLogger(__name__)


class AmazonsMainWindow(QMainWindow):
    """
    亚马逊棋游戏主窗口
    """
    # 定义玩家类型常量
    PLAYER_TYPE_HUMAN = 'human'
    PLAYER_TYPE_AI_MCTS = 'mcts'
    PLAYER_TYPE_AI_KATAAMAZON = 'kataAmazon'          # 兼容旧引用
    PLAYER_TYPE_AI_KATAAMAZON_GPU = 'kataAmazon_gpu'  # XZF-gen028 模型 + OpenCL(GPU) 引擎
    PLAYER_TYPE_AI_KATAAMAZON_LEGACY = 'kataAmazon_legacy'  # 原始引擎（OpenCL/GPU）+ 旧模型

    def __init__(self, simulator: AmazonsSimulator):
        super().__init__()
        self.simulator = simulator
        self.animation_group = None
        self.session = GameSessionController()
        self._ai_turn_pending = False
        self._active_ai_request = None
        self._hint_request_id = 0
        self._closing = False
        self._resume_ai_after_worker = False

        self.board_widget = None  # 将在init_ui中初始化

        self.black_modes = self.PLAYER_TYPE_HUMAN
        self.white_modes = self.PLAYER_TYPE_HUMAN
        # AI
        self.engine_manager = EngineManager()
        self.black_ai_agent = AmazonAIAgent(self, self.engine_manager)
        self.white_ai_agent = AmazonAIAgent(self, self.engine_manager)
        self.black_ai_agent.move_calculated.connect(
            lambda result: self.execute_ai_move(result, BLACK_AMAZON))
        self.white_ai_agent.move_calculated.connect(
            lambda result: self.execute_ai_move(result, WHITE_AMAZON))
        self.black_ai_agent.hint_calculated.connect(self._handle_hint_outcome)
        self.white_ai_agent.hint_calculated.connect(self._handle_hint_outcome)
        self.black_ai_agent.hint_progress.connect(self._handle_hint_progress)
        self.white_ai_agent.hint_progress.connect(self._handle_hint_progress)
        self.black_ai_agent.calculation_finished.connect(self._on_ai_worker_idle)
        self.white_ai_agent.calculation_finished.connect(self._on_ai_worker_idle)
        # 主题设置
        self.settings = create_settings()
        self.black_ai_profile = load_profile(self.settings, "black")
        self.white_ai_profile = load_profile(self.settings, "white")
        self.current_color_scheme = self.settings.value("display/theme", "BW", type=str)
        if self.current_color_scheme not in ('BW', 'RB', 'GS', 'PS'):
            self.current_color_scheme = 'BW'
        self.board_zoom = self.settings.value("display/board_zoom", 100, type=int)
        if self.board_zoom not in (80, 100, 120, 140):
            self.board_zoom = 100
        self.setWindowTitle("亚马逊棋")

        # --- AI 提示设置：显示最佳“选子 → 移动 → 射箭”的三阶段胜率 ---
        self.hint_count = self.settings.value("hints/count", 1, type=int)
        if self.hint_count not in (1, 3, 5):
            self.hint_count = 1
        self.hint_source = self.settings.value("hints/source", "gpu", type=str)
        if self.hint_source not in ('gpu', 'legacy'):
            self.hint_source = 'gpu'
        if not backend_available(self.hint_source):
            self.hint_source = 'gpu' if backend_available('gpu') else 'legacy'
        self.hint_side = self.settings.value("hints/side", BLACK_AMAZON, type=int)
        if self.hint_side not in (BLACK_AMAZON, WHITE_AMAZON):
            self.hint_side = BLACK_AMAZON
        # 完整回合胜率会立即启动后台模型分析。每次启动均保持关闭，
        # 避免沿用上次会话的勾选状态而在用户未主动选择时占用引擎资源。
        self._show_hints_default = False
        # 最近一次 AI 胜率(%)，用于左侧信息面板显示
        self.last_win_rate = None

        self.init_ui()
        geometry = self.settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.start_new_game()

    @property
    def game_generation(self):
        """Compatibility name for the revision attached to async requests."""
        return self.session.revision

    def _invalidate_position(self):
        """Cancel position-bound work before reset/import/undo/mode changes."""
        self.session.invalidate()
        self._hint_request_id += 1
        self._ai_turn_pending = False
        self._active_ai_request = None
        self.black_ai_agent.cancel_hint_analysis()
        self.white_ai_agent.cancel_hint_analysis()
        if hasattr(self, 'info_panel'):
            self.info_panel.set_task_progress()
        self._cancel_current_animation()

    def start_new_game(self):
        if not self.confirm_action("开始新游戏"):
            return

        # Invalidate every delayed callback and result that belongs to the old game.
        self._invalidate_position()

        self.simulator.reset()
        self.board_widget.reset_selection()
        self.board_widget.set_last_turn(None)
        self.board_widget.set_color_scheme(self.current_color_scheme)
        self.board_widget.set_hints([], self.hint_side)  # 清除 AI 提示
        self.update_win_rate_display(None)               # 清除胜率显示
        self.update_ai_info_panel(None, None)             # 清除右侧 AI 分析面板
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

    def _cancel_current_animation(self):
        """Stop an old-game animation and restore the board's idle state."""
        group = self.animation_group
        if group is not None:
            try:
                group.finished.disconnect()
            except (TypeError, RuntimeError):
                pass
            try:
                group.stop()
            except RuntimeError:
                pass

        self.animation_group = None
        if self.board_widget is not None:
            self.board_widget.animation_group = None
            self.board_widget.is_animating = False
            self.board_widget.hidden_pieces.clear()
            self.board_widget.anim_piece_type = 0
            self.board_widget.anim_arrow_scale = 1.0

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

    def set_hint_count(self, n):
        """设置 AI 提示显示的着法数量。"""
        self.hint_count = n if n in (1, 3, 5) else 1
        self.settings.setValue("hints/count", self.hint_count)
        self.update_hints()

    def set_board_zoom(self, percent: int):
        self.board_zoom = percent if percent in (80, 100, 120, 140) else 100
        self.board_widget.set_zoom_percent(self.board_zoom)
        if hasattr(self, "info_panel"):
            self.info_panel.set_zoom_percent(self.board_zoom)
        for value, action in getattr(self, "zoom_actions", {}).items():
            action.setChecked(value == self.board_zoom)
        self.settings.setValue("display/board_zoom", self.board_zoom)
        self.statusBar().showMessage(f"棋盘缩放已设置为 {self.board_zoom}%", 2500)
        # The board is inside a stretchable container.  When moving from a
        # larger zoom to a smaller one, that container can retain its previous
        # geometry for one layout pass, leaving a gap before the side panel.
        # Recalculate each parent from the fixed board size outward so the
        # first click produces the same compact layout as subsequent clicks.
        board_panel = self.board_widget.parentWidget()
        if board_panel is not None:
            board_panel.adjustSize()
        central = self.centralWidget()
        if central is not None:
            layout = central.layout()
            if layout is not None:
                layout.invalidate()
                layout.activate()
            central.adjustSize()
        self.adjustSize()

    def step_board_zoom(self, direction: int):
        """Move one step through the supported board zoom levels."""
        levels = (80, 100, 120, 140)
        try:
            index = levels.index(self.board_zoom)
        except ValueError:
            index = levels.index(100)
        delta = 1 if direction > 0 else -1
        index = max(0, min(len(levels) - 1, index + delta))
        self.set_board_zoom(levels[index])

    def show_ai_settings(self):
        """Edit per-side profiles; an already-running worker keeps its snapshot."""
        dialog = AISettingsDialog(self.black_ai_profile, self.white_ai_profile, self)
        if dialog.exec():
            black, white = dialog.profiles()
            self.black_ai_profile = save_profile(self.settings, "black", black)
            self.white_ai_profile = save_profile(self.settings, "white", white)
            self.settings.sync()
            self.statusBar().showMessage("AI 参数已保存，将在下一次 AI 回合生效。", 3500)

    def export_game_record(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出棋谱", "", "Amazons 棋谱 (*.amazons.json)")
        if not path:
            return
        if not path.lower().endswith(".amazons.json"):
            path += ".amazons.json"
        try:
            export_record(path, self.simulator)
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        self.statusBar().showMessage("棋谱已导出。", 3000)

    def import_game_record(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入棋谱", "", "Amazons 棋谱 (*.amazons.json)")
        if not path:
            return
        try:
            turns = load_record(path, self.simulator)
        except ValueError as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        # Validation above leaves the current board intact; mutate only now.
        self._invalidate_position()
        self.black_ai_agent.clear_board()
        self.white_ai_agent.clear_board()
        self.simulator.load_turns(turns)
        self.board_widget.reset_selection()
        self.board_widget.set_last_turn(turns[-1] if turns else None)
        self.board_widget.set_hints([], self.hint_side)
        self.update_win_rate_display(None)
        self.update_ai_info_panel(None, None)
        self.update_status()
        self.board_widget.update()
        if self.simulator.game_over:
            self.session.finish_turn(True)
            self.board_widget.setEnabled(False)
        elif self.is_ai_turn():
            if self.black_ai_agent.is_busy() or self.white_ai_agent.is_busy():
                self._resume_ai_after_worker = True
                self.board_widget.setEnabled(False)
            else:
                self.start_ai_turn()
        else:
            self.session.finish_turn()
            self.board_widget.setEnabled(True)
            self.update_hints()
        self.statusBar().showMessage("棋谱已导入。", 3000)

    def set_hint_source(self, source):
        """设置 AI 提示使用的引擎后端（'gpu' / 'legacy'）。"""
        self.hint_source = source
        self.settings.setValue("hints/source", source)
        self.update_hints()

    def set_hint_side(self, side):
        """设置提示对应的落子方。"""
        self.hint_side = side
        self.settings.setValue("hints/side", side)
        self.update_hints()

    def update_hints(self):
        """显示 kataAmazon 最佳完整回合的选子、移动、射箭阶段胜率。

        三个数字统一为原行动方视角；仅当轮到所选提示方（hint_side）落子时
        显示，非该方回合时清空。
        """
        if (not self.show_hints_action.isChecked() or self.simulator.game_over
                or self.simulator.current_player != self.hint_side):
            self._hint_request_id += 1
            self.black_ai_agent.cancel_hint_analysis()
            self.white_ai_agent.cancel_hint_analysis()
            self.board_widget.set_hints([], self.hint_side)
            self.info_panel.set_candidates()
            self.info_panel.set_task_progress()
            return

        # 用对应方的 AI agent 查询（使用独立的提示引擎，不影响对局引擎）
        agent = self.black_ai_agent if self.hint_side == BLACK_AMAZON else self.white_ai_agent
        self._hint_request_id += 1
        self.black_ai_agent.cancel_hint_analysis()
        self.white_ai_agent.cancel_hint_analysis()
        request_id = self._hint_request_id
        self.board_widget.set_hints([], self.hint_side)
        self.info_panel.set_candidates()
        self.statusBar().showMessage("正在后台计算 AI 提示...")
        self.info_panel.set_task_progress("正在启动胜率提示模型…")
        agent.start_hint_analysis(request_id, self.hint_side, self.hint_source, self.hint_count)

    def _handle_hint_progress(self, update):
        """Display progress only for the newest hint request and position."""
        if (self._closing or update.get('request_id') != self._hint_request_id
                or not self.show_hints_action.isChecked()
                or self.simulator.game_over
                or self.simulator.current_player != self.hint_side):
            return
        self.info_panel.set_task_progress(
            update.get('text', '正在分析胜率…'), update.get('progress'))

    def _handle_hint_outcome(self, outcome: HintOutcome):
        """Apply only the newest hint response for the current game position."""
        if (self._closing or outcome.request_id != self._hint_request_id
                or not self.show_hints_action.isChecked()
                or self.simulator.game_over
                or self.simulator.current_player != self.hint_side):
            return

        if outcome.error:
            self.board_widget.set_hints([], self.hint_side)
            self.info_panel.set_candidates()
            self.info_panel.set_task_progress("胜率提示分析失败", 0)
            self.statusBar().showMessage(f"AI 提示不可用：{outcome.error}")
            return

        normalized = []
        for candidate in outcome.candidates:
            if isinstance(candidate, HintCandidate):
                normalized.append(candidate)
            elif isinstance(candidate, tuple) and len(candidate) >= 2:
                normalized.append(HintCandidate(candidate[0], stage_win_rates=(candidate[1], None, None)))
        # The board stays readable by rendering only the strongest candidate.
        # Other Top-N candidates remain available in the analysis card.
        hints = sorted(
            normalized,
            key=lambda candidate: (candidate.stage_win_rates[0]
                                   if candidate.stage_win_rates[0] is not None
                                   else float('-inf')),
            reverse=True,
        )
        board_candidate = hints[0] if hints else None
        best_turn = (board_candidate.start, board_candidate.move, board_candidate.arrow) \
            if board_candidate is not None else outcome.best_turn
        stage_win_rates = (board_candidate.stage_win_rates
                           if board_candidate is not None else outcome.stage_win_rates)
        size = self.simulator.size
        self.board_widget.set_hints(
            ([(board_candidate.start // size, board_candidate.start % size,
               board_candidate.stage_win_rates[0])] if board_candidate is not None else []),
            self.hint_side,
            best_turn=best_turn,
            stage_win_rates=stage_win_rates)
        candidate_rows = []
        for index, candidate in enumerate(hints, 1):
            start = self._pos_to_display(candidate.start, size)
            move = self._pos_to_display(candidate.move, size) if candidate.move is not None else "—"
            arrow = self._pos_to_display(candidate.arrow, size) if candidate.arrow is not None else "—"
            rate = candidate.stage_win_rates[0]
            rate_text = "—" if rate is None else f"{rate:.1f}%"
            candidate_rows.append(f"{index}. {start} → {move} → {arrow}  {rate_text}")
        self.info_panel.set_candidates(candidate_rows)
        self.info_panel.set_task_progress("胜率提示分析完成", 100)
        # The progress block is useful during analysis, but keeping a completed
        # bar would unnecessarily take the space needed to show Top-3 directly.
        completed_request = outcome.request_id
        QTimer.singleShot(
            1200,
            lambda: self._clear_completed_hint_progress(completed_request),
        )
        if hints and stage_win_rates:
            labels = ("选子", "移动", "射箭")
            rate_text = " → ".join(
                f"{label} {rate:.1f}%" if rate is not None else f"{label} —"
                for label, rate in zip(labels, stage_win_rates))
            self.statusBar().showMessage(f"AI 提示：{rate_text}")
        else:
            self.statusBar().showMessage("AI 提示不可用（引擎未返回候选）。")

    def _clear_completed_hint_progress(self, request_id: int):
        """Clear only the completed progress block for the still-current hint."""
        if not self._closing and request_id == self._hint_request_id:
            self.info_panel.set_task_progress()

    def update_win_rate_display(self, win_rate=None, player=None):
        """更新左侧面板的 AI 胜率显示。win_rate 为百分比(0..100)，player 为行动方。"""
        self.last_win_rate = win_rate
        who = "黑方" if player == BLACK_AMAZON else ("白方" if player == WHITE_AMAZON else "")
        context = f"{who} AI 预测" if who else "当前行动方 AI 预测"
        self.info_panel.set_win_rate(win_rate, context)

    @staticmethod
    def _pos_to_display(pos_1d: int, size: int = 10) -> str:
        """将 1D 坐标转为棋盘显示坐标（如 0→'A10', 9→'J10', 90→'A1', 99→'J1'）。"""
        row = pos_1d // size
        col = pos_1d % size
        col_letter = chr(ord('A') + col)
        row_number = size - row
        return f"{col_letter}{row_number}"

    def update_ai_info_panel(self, best_res, player, ai_type_key: str = ""):
        """更新右侧 AI 分析信息面板。

        best_res: BestResult 或 None（None 时清空面板）。
        player: 当前行动方（BLACK_AMAZON / WHITE_AMAZON）。
        ai_type_key: AI 类型标识（如 'mcts' / 'kataAmazon_gpu' 等）。
        """
        if best_res is None:
            self.info_ai_model.setText("模型：—")
            self.info_move_detail.setText("棋步：—")
            self.info_win_rate.setText("胜率：—")
            self.info_visits.setText("搜索次数：—")
            self.info_eval.setText("局面估值：—")
            self.info_panel.info_summary.setText("数据：—")
            self.info_panel.set_candidates()
            return

        who = "黑方" if player == BLACK_AMAZON else "白方"

        # 模型名称
        model_names = {
            'mcts': 'MCTS C++',
            'kataAmazon': 'kataAmazon',
            'kataAmazon_gpu': 'gen028 GPU',
            'kataAmazon_legacy': '旧模型 GPU',
        }
        model_label = model_names.get(ai_type_key, ai_type_key or "AI")
        profile = self.black_ai_profile if player == BLACK_AMAZON else self.white_ai_profile
        strength = (f"{profile.mcts_seconds:.1f}s" if ai_type_key.startswith("mcts")
                    else f"{profile.kata_visits}v")
        side_short = "黑" if player == BLACK_AMAZON else "白"
        self.info_ai_model.setText(f"模型：{model_label} · {side_short}/{strength}")

        # 棋步详情
        size = self.simulator.size
        try:
            start_str = self._pos_to_display(best_res.best_pos_from, size)
            move_str = self._pos_to_display(best_res.best_pos_to, size)
            arrow_str = self._pos_to_display(best_res.best_pos_stone, size)
            self.info_move_detail.setText(
                f"棋步：{start_str} → {move_str} → {arrow_str}")
            self.info_move_detail.setToolTip(
                f"选子 {start_str} → 移动 {move_str} → 射箭 {arrow_str}")
        except Exception:
            self.info_move_detail.setText("棋步：解析失败")
            self.info_move_detail.setToolTip("")

        # 胜率
        if best_res.win_pro is not None:
            self.info_win_rate.setText(f"胜率：{best_res.win_pro:.2f}%")
        else:
            self.info_win_rate.setText("胜率：—")

        # 搜索次数
        if best_res.max_apt is not None:
            self.info_visits.setText(f"搜索次数：{int(best_res.max_apt)}")
        else:
            self.info_visits.setText("搜索次数：—")

        # 局面估值 / 选择概率
        if best_res.select_pro is not None:
            self.info_eval.setText(f"局面估值：{best_res.select_pro:.4f}")
        else:
            self.info_eval.setText("局面估值：—")

        rate_summary = ("—" if best_res.win_pro is None
                        else f"{best_res.win_pro:.1f}%")
        visits_summary = ("—" if best_res.max_apt is None
                          else str(int(best_res.max_apt)))
        eval_summary = ("—" if best_res.select_pro is None
                        else f"{best_res.select_pro:.3f}")
        self.info_panel.info_summary.setText(
            f"胜率 {rate_summary} · {visits_summary}次 · 估值 {eval_summary}")

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

        # 开局没有可撤销着法时保留正在运行的 AI 请求。若先作废请求再
        # 返回，棋盘会保持禁用且该请求的结果也不会再被接受。
        if not self.simulator.history_do_chess:
            self.statusBar().showMessage("无法悔棋，已是开局。")
            return

        self._invalidate_position()

        # 判断是否为人人
        is_human_vs_human = (
                self.black_modes == self.PLAYER_TYPE_HUMAN and
                self.white_modes == self.PLAYER_TYPE_HUMAN
        )

        # ========== 执行第一次悔棋 ==========
        if self.simulator.undo():
            self.black_ai_agent.undo_board()
            self.white_ai_agent.undo_board()

            # ====== 如果是人机对战，要再悔一步跳过 AI ======
            if not is_human_vs_human:
                if self.simulator.undo():
                    self.black_ai_agent.undo_board()
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
        self.board_widget.set_hints([], self.hint_side)
        self.update_win_rate_display(None)
        self.update_ai_info_panel(None, None)

        if self.simulator.history_do_chess:
            self.board_widget.set_last_turn(self.simulator.history_do_chess[-1])
        else:
            self.board_widget.set_last_turn(None)

        self.board_widget.update()
        self.update_status()

        # ========== 如果悔棋后轮到AI，则继续AI ==========
        if self.is_ai_turn():
            if self.black_ai_agent.is_busy() or self.white_ai_agent.is_busy():
                self._resume_ai_after_worker = True
                self.board_widget.setEnabled(False)
                self.session.begin_ai()
            else:
                self.start_ai_turn()
        else:
            self._resume_ai_after_worker = False
            self.board_widget.setEnabled(True)
            self.session.finish_turn()
            self.update_hints()

    def init_ui(self):
        """初始化主窗口的用户界面布局和控件。"""
        central_widget = QWidget()
        central_widget.setObjectName("gameCentralWidget")
        self.setCentralWidget(central_widget)
        main_h_layout = QHBoxLayout(central_widget)
        main_h_layout.setContentsMargins(10, 8, 10, 8)
        main_h_layout.setSpacing(12)

        board_panel = QWidget()
        board_layout = QVBoxLayout(board_panel)
        board_layout.setContentsMargins(0, 0, 0, 0)
        self.board_widget = BoardWidget(self.simulator, color_scheme=self.current_color_scheme)
        self.board_widget.set_zoom_percent(self.board_zoom)
        self.board_widget.mouse_genmove_completed.connect(self.on_turn_made)
        self.board_widget.game_over_signal.connect(self.show_game_over_message)
        board_layout.addWidget(self.board_widget)

        self.info_panel = AIInfoPanel(
            color_scheme=self.current_color_scheme,
            settings=self.settings,
            zoom_percent=self.board_zoom,
        )
        # 保留主窗口原有属性，避免影响状态更新和 AI 结果处理接口。
        self.status_label = self.info_panel.status_label
        self.win_rate_label = self.info_panel.win_rate_label
        self.info_ai_model = self.info_panel.info_ai_model
        self.info_move_detail = self.info_panel.info_move_detail
        self.info_win_rate = self.info_panel.info_win_rate
        self.info_visits = self.info_panel.info_visits
        self.info_eval = self.info_panel.info_eval

        main_h_layout.addWidget(board_panel, 1)
        main_h_layout.addWidget(self.info_panel, 0)

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
        self.black_ai_mcts_action = QAction("MCTS★", self, checkable=True)
        self.black_ai_mcts_action.setEnabled(mcts_available('mcts'))
        self.black_ai_mcts_action.triggered.connect(lambda: self.set_player_mode(BLACK_AMAZON, self.PLAYER_TYPE_AI_MCTS))
        black_player_group.addAction(self.black_ai_mcts_action)
        black_ai_menu.addAction(self.black_ai_mcts_action)

        #  kataAmazon（XZF-gen028 模型，OpenCL/GPU）
        self.black_ai_kata_gpu_action = QAction("XZF-gen028（GPU）★★", self, checkable=True)
        self.black_ai_kata_gpu_action.setEnabled(backend_available('gpu'))
        self.black_ai_kata_gpu_action.triggered.connect(
            lambda: self.set_player_mode(BLACK_AMAZON, self.PLAYER_TYPE_AI_KATAAMAZON_GPU))
        black_player_group.addAction(self.black_ai_kata_gpu_action)
        black_ai_menu.addAction(self.black_ai_kata_gpu_action)

        # 原始 kataAmazon（OpenCL/GPU + 旧模型 amazons10x10），项目最初就带的选项
        self.black_ai_kata_legacy_action = QAction("kataAmazon(原始)★★", self, checkable=True)
        self.black_ai_kata_legacy_action.setEnabled(backend_available('legacy'))
        self.black_ai_kata_legacy_action.triggered.connect(
            lambda: self.set_player_mode(BLACK_AMAZON, self.PLAYER_TYPE_AI_KATAAMAZON_LEGACY))
        black_player_group.addAction(self.black_ai_kata_legacy_action)
        black_ai_menu.addAction(self.black_ai_kata_legacy_action)

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
        self.white_ai_mcts_action = QAction("MCTS★", self, checkable=True)
        self.white_ai_mcts_action.setEnabled(mcts_available('mcts'))
        self.white_ai_mcts_action.triggered.connect(lambda: self.set_player_mode(WHITE_AMAZON, self.PLAYER_TYPE_AI_MCTS))
        white_player_group.addAction(self.white_ai_mcts_action)
        white_ai_menu.addAction(self.white_ai_mcts_action)

        #  kataAmazon（XZF-gen028 模型，OpenCL/GPU）
        self.white_ai_kata_gpu_action = QAction("XZF-gen028（GPU）★★", self, checkable=True)
        self.white_ai_kata_gpu_action.setEnabled(backend_available('gpu'))
        self.white_ai_kata_gpu_action.triggered.connect(
            lambda: self.set_player_mode(WHITE_AMAZON, self.PLAYER_TYPE_AI_KATAAMAZON_GPU))
        white_player_group.addAction(self.white_ai_kata_gpu_action)
        white_ai_menu.addAction(self.white_ai_kata_gpu_action)

        # 原始 kataAmazon（OpenCL/GPU + 旧模型 amazons10x10），项目最初就带的选项
        self.white_ai_kata_legacy_action = QAction("kataAmazon(原始)★★", self, checkable=True)
        self.white_ai_kata_legacy_action.setEnabled(backend_available('legacy'))
        self.white_ai_kata_legacy_action.triggered.connect(
            lambda: self.set_player_mode(WHITE_AMAZON, self.PLAYER_TYPE_AI_KATAAMAZON_LEGACY))
        white_player_group.addAction(self.white_ai_kata_legacy_action)
        white_ai_menu.addAction(self.white_ai_kata_legacy_action)

        white_player_menu.addMenu(white_ai_menu)
        game_menu.addMenu(white_player_menu)

        ai_settings_action = QAction("AI 参数设置…", self)
        ai_settings_action.triggered.connect(self.show_ai_settings)
        game_menu.addAction(ai_settings_action)

        export_action = QAction("导出棋谱…", self)
        export_action.triggered.connect(self.export_game_record)
        game_menu.addAction(export_action)

        import_action = QAction("导入棋谱…", self)
        import_action.triggered.connect(self.import_game_record)
        game_menu.addAction(import_action)

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
        self.theme_bw_action.setChecked(self.current_color_scheme == 'BW')
        self.theme_bw_action.triggered.connect(lambda: self.set_color_scheme('BW'))
        theme_group.addAction(self.theme_bw_action)
        theme_menu.addAction(self.theme_bw_action)

        # 红蓝对决主题
        self.theme_rb_action = QAction("桃蹊蒼茫", self, checkable=True)
        self.theme_rb_action.setChecked(self.current_color_scheme == 'RB')
        self.theme_rb_action.triggered.connect(lambda: self.set_color_scheme('RB'))
        theme_group.addAction(self.theme_rb_action)
        theme_menu.addAction(self.theme_rb_action)

        # 主题
        self.theme_gs_action = QAction("杳霭流玉", self, checkable=True)
        self.theme_gs_action.setChecked(self.current_color_scheme == 'GS')
        self.theme_gs_action.triggered.connect(lambda: self.set_color_scheme('GS'))
        theme_group.addAction(self.theme_gs_action)
        theme_menu.addAction(self.theme_gs_action)

        # 主题
        self.theme_ps_action = QAction("流绪微梦", self, checkable=True)
        self.theme_ps_action.setChecked(self.current_color_scheme == 'PS')
        self.theme_ps_action.triggered.connect(lambda: self.set_color_scheme('PS'))
        theme_group.addAction(self.theme_ps_action)
        theme_menu.addAction(self.theme_ps_action)

        display_menu.addMenu(theme_menu)  # 添加主题设置到显示菜单

        zoom_menu = QMenu("棋盘缩放", self)
        zoom_group = QActionGroup(self)
        zoom_group.setExclusive(True)
        self.zoom_actions = {}
        for percent in (80, 100, 120, 140):
            action = QAction(f"{percent}%", self, checkable=True)
            action.setChecked(percent == self.board_zoom)
            action.triggered.connect(lambda _, percent=percent: self.set_board_zoom(percent))
            zoom_group.addAction(action)
            zoom_menu.addAction(action)
            self.zoom_actions[percent] = action
        zoom_menu.addSeparator()
        self.zoom_in_action = QAction("放大一级", self)
        self.zoom_in_action.setShortcut("Ctrl++")
        self.zoom_in_action.triggered.connect(lambda: self.step_board_zoom(1))
        zoom_menu.addAction(self.zoom_in_action)
        self.zoom_out_action = QAction("缩小一级", self)
        self.zoom_out_action.setShortcut("Ctrl+-")
        self.zoom_out_action.triggered.connect(lambda: self.step_board_zoom(-1))
        zoom_menu.addAction(self.zoom_out_action)
        display_menu.addMenu(zoom_menu)

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

        display_menu.addSeparator()

        # --- AI 提示（kataAmazon 胜率）---
        self.show_hints_action = QAction("显示完整回合胜率", self, checkable=True)
        self.show_hints_action.setChecked(self._show_hints_default)
        self.show_hints_action.setShortcut("Ctrl+H")
        self.show_hints_action.triggered.connect(self.update_hints)
        display_menu.addAction(self.show_hints_action)

        # 提示数量子菜单
        hint_count_menu = QMenu("提示数量", self)
        hint_count_group = QActionGroup(self)
        hint_count_group.setExclusive(True)
        for n in (1, 3, 5):
            action = QAction(f"前 {n} 个候选", self, checkable=True)
            action.setChecked(n == self.hint_count)
            action.triggered.connect(lambda _, n=n: self.set_hint_count(n))
            hint_count_group.addAction(action)
            hint_count_menu.addAction(action)
        display_menu.addMenu(hint_count_menu)

        # 提示视角子菜单（提示哪一方的候选着法）
        hint_side_menu = QMenu("提示视角", self)
        hint_side_group = QActionGroup(self)
        hint_side_group.setExclusive(True)
        for side, name in ((BLACK_AMAZON, "黑方"), (WHITE_AMAZON, "白方")):
            action = QAction(name, self, checkable=True)
            action.setChecked(side == self.hint_side)
            action.triggered.connect(lambda _, side=side: self.set_hint_side(side))
            hint_side_group.addAction(action)
            hint_side_menu.addAction(action)
        display_menu.addMenu(hint_side_menu)

        # 提示模型子菜单（用哪个引擎后端评估胜率：XZF-gen028 / 原始旧模型）
        hint_source_menu = QMenu("提示模型", self)
        hint_source_group = QActionGroup(self)
        hint_source_group.setExclusive(True)
        for key, label in (('gpu', 'XZF-gen028（GPU）'),
                           ('legacy', 'kataAmazon-原始（旧模型）')):
            action = QAction(label, self, checkable=True)
            action.setEnabled(backend_available(key))
            action.setChecked(key == self.hint_source)
            action.triggered.connect(lambda _, key=key: self.set_hint_source(key))
            hint_source_group.addAction(action)
            hint_source_menu.addAction(action)
        display_menu.addMenu(hint_source_menu)

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

        diagnostics_action = QAction("查看诊断日志", self)
        diagnostics_action.triggered.connect(self.show_diagnostics_log)
        help_menu.addAction(diagnostics_action)

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
        <p><b>ESC</b> - 取消当前选择</p>
        <p><b>Ctrl++ / Ctrl+-</b> - 逐级放大/缩小棋盘</p>
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

    def show_diagnostics_log(self):
        path = log_file_path()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[-20_000:]
        except OSError:
            text = "暂无诊断日志。"
        dialog = QDialog(self)
        dialog.setWindowTitle(f"诊断日志：{path}")
        dialog.resize(760, 480)
        layout = QVBoxLayout(dialog)
        viewer = QTextEdit(dialog)
        viewer.setReadOnly(True)
        viewer.setPlainText(text or "暂无诊断日志。")
        layout.addWidget(viewer)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def set_player_mode(self, side, player_type):
        """
        设置某一边的玩家类型
        """
        availability = {
            self.PLAYER_TYPE_AI_MCTS: mcts_available('mcts'),
            self.PLAYER_TYPE_AI_KATAAMAZON_GPU: backend_available('gpu'),
            self.PLAYER_TYPE_AI_KATAAMAZON_LEGACY: backend_available('legacy'),
        }
        if player_type != self.PLAYER_TYPE_HUMAN and not availability.get(player_type, False):
            QMessageBox.warning(self, "AI 不可用", "所选 AI 的模块、引擎或模型文件不完整。")
            if side == BLACK_AMAZON:
                self.black_human_action.setChecked(True)
            else:
                self.white_human_action.setChecked(True)
            return

        if side == BLACK_AMAZON:
            self.black_modes = player_type
            side_text = "黑方"
        else:
            self.white_modes = player_type
            side_text = "白方"

        if player_type == self.PLAYER_TYPE_HUMAN:
            mode_text = "人类"
        else:
            mode_text = "AI"

        self.statusBar().showMessage(f"已将 {side_text} 设置为 {mode_text} 玩家。", 3000)

        # A result from a just-replaced AI must not leave the board disabled.
        # Wait for that worker to release its engine, then start the selected AI.
        if (side == self.simulator.current_player
                and (self._active_ai_request is not None or self._ai_turn_pending)):
            worker_busy = (self.black_ai_agent.is_busy()
                           or self.white_ai_agent.is_busy())
            self._invalidate_position()
            self._resume_ai_after_worker = worker_busy
            self.board_widget.setEnabled(True)
            if worker_busy:
                self._on_ai_worker_idle()

        if self.simulator.game_over:
            self.show_game_over_message()
        else:
            # 检查是否需要触发 AI 下棋
            if self.is_ai_turn() and not self._resume_ai_after_worker:
                self.start_ai_turn()

    def _on_ai_worker_idle(self):
        """Resume a mode-switched AI turn only after its old worker ended."""
        if not self._resume_ai_after_worker or self._closing:
            return
        if self.black_ai_agent.is_busy() or self.white_ai_agent.is_busy():
            return
        self._resume_ai_after_worker = False
        if not self.simulator.game_over and self.is_ai_turn():
            self.start_ai_turn()

    def set_color_scheme(self, scheme_key: str):
        """
        设置棋盘的主题配色方案。
        """
        if self.board_widget:
            self.board_widget.set_color_scheme(scheme_key)
            self.info_panel.set_theme(scheme_key)
            self.current_color_scheme = scheme_key
            self.settings.setValue("display/theme", scheme_key)

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
        if self.simulator.game_over:
            if self.simulator.winner in (BLACK_AMAZON, WHITE_AMAZON):
                winner_name = "黑方" if self.simulator.winner == BLACK_AMAZON else "白方"
                self.info_panel.set_status(f"游戏结束：{winner_name}获胜")
            else:
                self.info_panel.set_status("游戏结束")
            return

        player_name = "黑方" if self.simulator.current_player == BLACK_AMAZON else "白方"

        if self.is_ai_turn():
            self.info_panel.set_status(f"轮到 {player_name}（AI）落子")
        else:
            self.info_panel.set_status(f"轮到 {player_name}（人类）落子")

    def show_game_over_message(self, message=None):
        """显示游戏结束消息"""
        self.session.finish_turn(True)
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

    def resign_game(self):
        """处理认输操作。"""
        # 检查是否在游戏中
        if self.simulator.game_over or len(self.simulator.history_do_chess) == 0:
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
        player_who_moved = self.simulator.current_player
        if self.simulator.execute_turn(start_pos, move_pos, arrow_pos):
            # 先由规则层确认合法，再把同一已提交回合同步到所有对局引擎。
            self.black_ai_agent.sync_committed_turn(
                player_who_moved, start_pos, move_pos, arrow_pos)
            self.white_ai_agent.sync_committed_turn(
                player_who_moved, start_pos, move_pos, arrow_pos)
            self.board_widget.set_last_turn((start_pos, move_pos, arrow_pos))

            self.update_status()
            self.board_widget.update()  # 确保在动画结束后立即刷新

            if self.simulator.game_over:
                self.session.finish_turn(True)
                self.board_widget.set_hints([], self.hint_side)
                return 'GAME_OVER'

            # 玩家落子后，检查是否轮到 AI 下棋
            if self.is_ai_turn():
                self.board_widget.set_hints([], self.hint_side)  # 轮到 AI，清除旧提示
                self.start_ai_turn()
                return 'AI_TURN'

            # 轮到人类：若开启了提示，刷新当前局面的候选着法胜率
            self.update_hints()

            self.board_widget.setEnabled(True)  # 恢复人类输入
            self.session.finish_turn()
            return 'HUMAN_TURN'
        else:
            QMessageBox.warning(self, "无效操作", "此操作不符合规则!")
            self.board_widget.setEnabled(True)  # 恢复人类输入
            self.session.finish_turn()
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
        self.session.begin_animation()
        self.board_widget.hidden_pieces.add(start_pos)
        # 明确告知控件正在移动的是哪一方的棋子，避免它从 hidden_pieces 反推。
        self.board_widget.anim_piece_type = piece_type

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
        animation_generation = self.game_generation
        animation_group = QSequentialAnimationGroup(self)
        animation_group.addAnimation(piece_anim)
        animation_group.addAnimation(settle_group)
        animation_group.addAnimation(arrow_shrink_anim)
        animation_group.addAnimation(arrow_anim)
        animation_group.addAnimation(arrow_land_anim)

        self.animation_group = animation_group
        self.board_widget.animation_group = animation_group

        def on_group_finished():
            # A stale animation must never apply its move to a new board.
            if (animation_generation != self.game_generation
                    or self.animation_group is not animation_group):
                return

            self.animation_group = None
            self.board_widget.is_animating = False
            self.board_widget.hidden_pieces.clear()
            self.board_widget.anim_piece_type = 0
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
        animation_group.finished.connect(on_group_finished)
        animation_group.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def start_ai_turn(self):
        """
        启动AI回合，带有视觉反馈。
        """
        if self.simulator.game_over or not self.is_ai_turn() or self._ai_turn_pending:
            return

        # 1. 改变状态栏提示
        current_player_name = "黑方" if self.simulator.current_player == BLACK_AMAZON else "白方"
        self.info_panel.set_status(f"{current_player_name}（AI）正在思考…")
        self.board_widget.setEnabled(False)  # 禁用交互
        self.board_widget.repaint()

        # 2. 延迟启动 AI 计算，避免阻塞 UI
        generation = self.game_generation
        player = self.simulator.current_player
        self._ai_turn_pending = True
        self.session.begin_ai()
        QTimer.singleShot(
            100, lambda: self.start_ai_calculation(generation, player))

    def start_ai_calculation(self, generation=None, expected_player=None):
        """
        执行AI的下棋操作。
        """
        if generation is None:
            generation = self.game_generation
        if expected_player is None:
            expected_player = self.simulator.current_player
        if generation != self.game_generation:
            return

        self._ai_turn_pending = False
        if (self.simulator.game_over or expected_player != self.simulator.current_player
                or not self.is_ai_turn()):
            return

        # 选择当前玩家的模式和 agent
        if self.simulator.current_player == BLACK_AMAZON:
            current_player_mode = self.black_modes
            current_agent = self.black_ai_agent
            profile = self.black_ai_profile
            profile_key = "black"
        else:
            current_player_mode = self.white_modes
            current_agent = self.white_ai_agent
            profile = self.white_ai_profile
            profile_key = "white"

        # 根据玩家类型启动 AI 计算，同时记录当前 AI 类型供右侧面板显示
        ai_type_key = ''
        if current_player_mode == self.PLAYER_TYPE_AI_MCTS:
            ai_type_key = 'mcts'
        elif current_player_mode == self.PLAYER_TYPE_AI_KATAAMAZON_GPU:
            ai_type_key = 'kataAmazon_gpu'
        elif current_player_mode == self.PLAYER_TYPE_AI_KATAAMAZON_LEGACY:
            ai_type_key = 'kataAmazon_legacy'
        if not ai_type_key:
            return
        # Preserve the legacy backend's historical 400-visits default until
        # the player explicitly saves a per-side visits value.
        if (ai_type_key == 'kataAmazon_legacy'
                and not self.settings.contains(f"ai/{profile_key}/kata_visits")):
            profile = AIProfile(profile.mcts_seconds, 400)

        self.current_ai_type = ai_type_key
        try:
            started = current_agent.start_thread_ai_calculation(ai_type_key, profile)
        except Exception as exc:
            self._active_ai_request = None
            self._recover_from_ai_failure(str(exc), expected_player)
            return
        if not started:
            # calculation_finished 会在旧 worker 真正退出后恢复本回合，
            # 无需每 100ms 创建一个新的重试定时器。
            self._resume_ai_after_worker = True
            self.board_widget.setEnabled(False)
            return
        self._active_ai_request = (generation, expected_player, ai_type_key)

    def execute_ai_move(self, result, source_player=None):
        """
        处理AI计算出的最佳移动，执行下棋并更新UI。
        """
        outcome = result if isinstance(result, AIOutcome) else AIOutcome.failure("AI 返回了未知结果。")
        request = self._active_ai_request
        if (request is None
                or request[0] != self.game_generation
                or request[1] != self.simulator.current_player
                or (source_player is not None and request[1] != source_player)
                or self.simulator.game_over
                or not self.is_ai_turn()):
            return

        current_mode = (self.black_modes if request[1] == BLACK_AMAZON
                        else self.white_modes)
        if current_mode != request[2]:
            return
        self._active_ai_request = None

        if outcome.error:
            self._recover_from_ai_failure(outcome.error, request[1])
            return

        if outcome.resigned:
            self.simulator.game_over = True
            self.simulator.winner = -self.simulator.current_player
            winner_name = "黑方" if self.simulator.winner == BLACK_AMAZON else "白方"
            player_name = "黑方" if self.simulator.current_player == BLACK_AMAZON else "白方"
            self.handle_game_over(f"{player_name}已认输，{winner_name}获胜！")
            return

        best_res = outcome.result
        if best_res is None:
            self._recover_from_ai_failure("AI 没有返回着法。", request[1])
            return

        # 任何空值或越界值都不能进入动画。
        size = self.simulator.size
        raw_positions = (best_res.best_pos_from, best_res.best_pos_to, best_res.best_pos_stone)
        if not all(isinstance(p, int) and 0 <= p < size * size for p in raw_positions):
            logger.warning("AI 返回非法坐标: %s", raw_positions)
            self._recover_from_ai_failure(
                f"AI 返回了非法坐标：{raw_positions}", request[1])
            return

        start_pos = (best_res.best_pos_from // self.simulator.size, best_res.best_pos_from % self.simulator.size)
        move_pos = (best_res.best_pos_to // self.simulator.size, best_res.best_pos_to % self.simulator.size)
        arrow_pos = (best_res.best_pos_stone // self.simulator.size, best_res.best_pos_stone % self.simulator.size)
        if not self.simulator.is_legal_turn(start_pos, move_pos, arrow_pos):
            self._recover_from_ai_failure(
                f"AI 返回了非法着法：{start_pos} → {move_pos} / {arrow_pos}", request[1])
            return

        win_pro_str = "—" if best_res.win_pro is None else f"{best_res.win_pro:.2f}%"
        visits_str = "—" if best_res.max_apt is None else str(int(best_res.max_apt))
        select_pro_str = "—" if best_res.select_pro is None else f"{best_res.select_pro:.4f}"
        player_name = "黑方" if self.simulator.current_player == BLACK_AMAZON else "白方"
        # 构建状态栏信息
        info_message = (
            f"{player_name}"
            f"AI 走法: 胜率={win_pro_str} | "
            f"搜索次数={visits_str} | "
            f"局面估值={select_pro_str}"
        )
        self.statusBar().showMessage(info_message)

        self.update_win_rate_display(best_res.win_pro, self.simulator.current_player)

        # 更新右侧 AI 分析信息面板
        self.update_ai_info_panel(best_res, self.simulator.current_player,
                                  getattr(self, 'current_ai_type', ''))

        # 使用动画执行 AI 的走法
        player_who_moved = self.simulator.current_player
        callback = lambda: self.post_animation_update(start_pos, move_pos, arrow_pos)
        self.run_full_turn_animation_sequence(start_pos, move_pos, arrow_pos, player_who_moved, callback)

        # 动画完成后的逻辑会由 on_group_finished -> post_animation_update 处理

    def _recover_from_ai_failure(self, message: str, side: int):
        """Return control to a human instead of leaving the board disabled."""
        if side == BLACK_AMAZON:
            self.black_modes = self.PLAYER_TYPE_HUMAN
            self.black_human_action.setChecked(True)
            side_name = "黑方"
        else:
            self.white_modes = self.PLAYER_TYPE_HUMAN
            self.white_human_action.setChecked(True)
            side_name = "白方"
        self._ai_turn_pending = False
        self._active_ai_request = None
        self.board_widget.setEnabled(True)
        self.session.finish_turn()
        self.update_status()
        self.statusBar().showMessage(f"AI 失败，{side_name}已切换为人类：{message}")

    def closeEvent(self, event):
        """Invalidate callbacks and release engine subprocesses before exit."""
        self._closing = True
        self._invalidate_position()
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.sync()
        # Shutdown has a short bounded grace period; a native search that
        # cannot be interrupted is force-terminated so closing the window does
        # not leave the user waiting through multiple engine timeouts.
        self.black_ai_agent.shutdown(wait_ms=350)
        self.white_ai_agent.shutdown(wait_ms=350)
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    try:
        logger.info("正在初始化模拟器")
        simulator = AmazonsSimulator(size=10)
        logger.info("模拟器初始化成功")
        logger.info("正在创建主窗口")
        main_window = AmazonsMainWindow(simulator)
        logger.info("主窗口创建成功")
        main_window.show()
        logger.info("程序启动成功")
        sys.exit(app.exec())
    except Exception as e:
        logger.exception("应用程序错误: %s", e)
