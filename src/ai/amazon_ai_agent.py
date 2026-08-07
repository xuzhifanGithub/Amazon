import sys
import os
import logging
import threading
from PyQt6.QtCore import QObject, QThread, pyqtSignal
logger = logging.getLogger(__name__)
# 确保项目根目录在 sys.path 中
current_dir = os.path.dirname(os.path.abspath(__file__))
# 优先从发布用 native 目录加载；开发构建目录仅作为本地回退。
for module_path in (
        os.path.join(current_dir, 'native'),
        os.path.join(current_dir, 'src', 'build'),
        os.path.join(current_dir, 'src2', 'build')):
    if os.path.isdir(module_path) and module_path not in sys.path:
        sys.path.append(module_path)
try:
    import amazon_ai
    logger.info("成功导入 amazon_ai 模块")
except ImportError:
    amazon_ai = None
    logger.warning("未找到 amazon_ai 模块，请选择受支持的 Python 版本或自行编译")
try:
    import amazon_ai_test
    logger.info("成功导入 amazon_ai_test 模块")
except ImportError:
    amazon_ai_test = None
    logger.warning("未找到 amazon_ai_test 模块，请选择受支持的 Python 版本或自行编译")

from src.ai.amazons_engine import (AmazonsKataGoEngine, backend_available,
                                    engine_spec_for_backend)
from src.ai.engine_manager import EngineManager
# 获取当前脚本的绝对路径
project_root = os.path.join(current_dir, '..', '..')
# 将项目的根目录添加到 sys.path
sys.path.append(project_root)
from src.core.simulator import  WHITE_AMAZON, BLACK_AMAZON
from src.ai.ai_profile import AIProfile
from src.ai.results import AIOutcome, BestResult, HintCandidate, HintOutcome


def mcts_available(ai_type: str) -> bool:
    if ai_type == 'mcts':
        return amazon_ai is not None
    if ai_type == 'mcts_test':
        return amazon_ai_test is not None
    return False

class AIWorker(QObject):
    """
    负责执行 AI 计算的 QObject 工作者。
    """
    finished = pyqtSignal(object)  # 计算结果（-1 表示错误）


    def __init__(self, board_size, board, queen_pos, current_player, ai_type,
                 ai_type_engine=None, engine_provider=None, engine_backend=None,
                 mcts_seconds: float = 1.0, kata_visits: int | None = None):
        super().__init__()
        self.board_size = board_size
        self.board = board
        self.queenPos = queen_pos
        self.current_player = current_player
        self.ai_type = ai_type
        self.ai_type_engine = ai_type_engine
        self.engine_provider = engine_provider
        self.engine_backend = engine_backend
        self.mcts_seconds = mcts_seconds
        self.kata_visits = kata_visits



    def run(self):
        """
        在子线程中执行耗时的 AI 计算。
        """
        best_res = BestResult()
        try:
            if self.ai_type == 'mcts' or self.ai_type == 'mcts_test':
                best_move = self.ai_type_engine.uct_search(
                    self.board,
                    self.queenPos,
                    self.current_player,
                    self.mcts_seconds,
                    True
                )
                # best_res.best_pos_from = (best_move.From // self.board_size, best_move.From % self.board_size)
                # best_res.best_pos_to = (best_move.To // self.board_size, best_move.To % self.board_size)
                # best_res.best_pos_stone = (best_move.Stone // self.board_size, best_move.Stone % self.board_size)
                best_res.best_pos_from = best_move.From
                best_res.best_pos_to = best_move.To
                best_res.best_pos_stone = best_move.Stone

                best_res.win_pro = best_move.pro
                best_res.max_apt = best_move.attempt
                best_res.select_pro = best_move.value
            elif self.ai_type == 'kataAmazon':
                if self.engine_provider is not None:
                    self.ai_type_engine = self.engine_provider(self.engine_backend, self.kata_visits)
                if self.ai_type_engine is None:
                    raise RuntimeError("kataAmazon 引擎不可用。")
                # 不发送 time_settings：任何时间控制都会让 CPU 引擎按时间搜索，
                # 时间为 0 时只有 1 次访问、胜率无意义。改由 engine.cfg 的 maxVisits 控制。
                turn_tuple = self.ai_type_engine.get_best_turn(self.current_player)
                start_pos, move_pos, arrow_pos = turn_tuple

                # 引擎放弃/认输：一个亚马逊棋回合由 3 次 GTP genmove 组成，
                # 其中任意一段返回 pass 或 resign 都表示引擎不再给出合法着法，
                # 一律按「当前行动方认输」处理（-2 由主窗口显示认输结算）。
                non_moves = ('pass', 'resign')
                if any(str(p).strip().lower() in non_moves
                       for p in (start_pos, move_pos, arrow_pos)):
                    self.finished.emit(AIOutcome.resignation())
                    return  # 直接返回，不执行后续逻辑

                #print(f"引擎输出坐标 - 起始1: '{start_pos}', 移动: '{move_pos}', 射箭: '{arrow_pos}'")
                start_pos = self.ai_type_engine._convert_coord(start_pos)
                move_pos = self.ai_type_engine._convert_coord(move_pos)
                arrow_pos = self.ai_type_engine._convert_coord(arrow_pos)
                #print(f"引擎输出坐标 - 起始2: '{start_pos}', 移动: '{move_pos}', 射箭: '{arrow_pos}'")
                best_res.best_pos_from = start_pos[0]*self.board_size + start_pos[1]
                best_res.best_pos_to = move_pos[0] * self.board_size + move_pos[1]
                best_res.best_pos_stone = arrow_pos[0] * self.board_size + arrow_pos[1]

                # 从引擎带回的胜率(%)与搜索次数，供 GUI 显示。
                win = getattr(self.ai_type_engine, 'last_winrate', None)
                visits = getattr(self.ai_type_engine, 'last_visits', None)
                best_res.win_pro = win
                best_res.max_apt = visits
                # kataAmazon 没有单独的“选择概率”，用胜率占位以复用状态栏格式。
                best_res.select_pro = (win / 100.0) if win is not None else None
            else:
                raise ValueError("Invalid AI type provided.")

            self.finished.emit(AIOutcome.success(best_res))
        except Exception as e:
            logger.exception("AIWorker 线程错误")
            self.finished.emit(AIOutcome.failure(str(e)))


class HintWorker(QObject):
    """Long-lived worker that owns the hint engine in one dedicated thread."""

    finished = pyqtSignal(object)
    stopped = pyqtSignal()

    def __init__(self, board_size: int):
        super().__init__()
        self.board_size = board_size
        self.engine = None
        self.backend = None
        self.busy = False

    def _close_engine(self):
        if self.engine is not None:
            try:
                self.engine.close()
            except Exception:
                logger.exception("关闭提示引擎失败")
        self.engine = None
        self.backend = None

    def _ensure_engine(self, backend: str):
        if self.engine is not None and self.backend == backend:
            return self.engine
        self._close_engine()
        spec = engine_spec_for_backend(backend)
        self.engine = AmazonsKataGoEngine(
            backend=backend,
            config_file=spec.get('hint_cfg', spec['cfg']),
        )
        self.backend = backend
        return self.engine

    def analyze(self, request):
        request_id = request['request_id']
        self.busy = True
        try:
            engine = self._ensure_engine(request['backend'])
            engine.clear_board()
            for index, turn in enumerate(request['history']):
                player = BLACK_AMAZON if index % 2 == 0 else WHITE_AMAZON
                start, move, arrow = turn
                engine.play_turn(
                    player,
                    engine._convert_to_gtp_coord(*start),
                    engine._convert_to_gtp_coord(*move),
                    engine._convert_to_gtp_coord(*arrow),
                )

            candidates = []
            for start, start_win, start_visits in engine.ranked_start_candidates(
                    request['player'], request.get('top_n', 1)):
                turn, rates, visits = engine.analyze_turn_for_start(
                    request['player'], start, start_win, start_visits)
                if turn is None or rates is None:
                    continue
                coords = tuple(engine._convert_coord(coord) for coord in turn)
                positions = tuple(r * self.board_size + c for r, c in coords)
                candidates.append(HintCandidate(
                    positions[0], positions[1], positions[2], rates, visits))
            if not candidates:
                self.finished.emit(HintOutcome(request_id, error="引擎没有返回合法候选。"))
                return
            best = candidates[0]
            self.finished.emit(HintOutcome(
                request_id=request_id,
                candidates=tuple(candidates),
                best_turn=(best.start, best.move, best.arrow),
                stage_win_rates=best.stage_win_rates,
            ))
        except Exception as exc:
            logger.exception("提示分析失败")
            self._close_engine()
            self.finished.emit(HintOutcome(request_id, error=str(exc)))
        finally:
            self.busy = False

    def shutdown(self):
        self._close_engine()
        self.stopped.emit()

    def abort(self):
        if self.engine is not None:
            self.engine.abort()




class AmazonAIAgent(QObject):
    """
    负责管理 AI 落子逻辑的类，使用独立线程。
    """
    move_calculated = pyqtSignal(object)
    hint_requested = pyqtSignal(object)
    hint_shutdown_requested = pyqtSignal()
    hint_calculated = pyqtSignal(object)
    calculation_finished = pyqtSignal()

    def __init__(self, main_window_instance, engine_manager: EngineManager | None = None):
        super().__init__()
        self.main_window = main_window_instance
        self.thread = None
        self.worker = None
        self._clear_board_pending = False
        self._engine_lock = threading.RLock()
        self.size = self.main_window.simulator.size
        self.ai = amazon_ai.AmazonasAI() if amazon_ai is not None else None
        self.ai_test = amazon_ai_test.AmazonasAITest() if amazon_ai_test is not None else None
        # kataAmazon 引擎：可选 'gpu'(CUDA,新权重) / 'legacy'(OpenCL,旧模型)。
        # Gameplay engines are reused per (backend, visits) profile.
        self.ai_engine = None
        self._engine_manager = engine_manager or EngineManager()
        self._engine_pool = self._engine_manager.engines
        self.kata_backend = None    # 当前已加载引擎的后端标识（'gpu' / 'legacy' / None）

        # 提示引擎由长生命周期 HintWorker 独占，避免在 GUI 线程中初始化或搜索。
        self.hint_thread = None
        self.hint_worker = None


    def start_thread_ai_calculation(self, ai_type, profile: AIProfile | None = None):
        """
        在子线程中启动 AI 计算。
        """
        # 确保没有正在运行的线程
        if self.thread is not None and self.thread.isRunning():
            return False

        self.main_window.statusBar().showMessage("AI 正在思考中...")

        # 创建工作者和线程
        self.thread = QThread()
        simulator = self.main_window.simulator
        ai_board, ai_queen_pos = simulator.get_ai_data()
        ai_type_engine = None


        worker_ai_type = ai_type
        if ai_type == 'mcts':
            if self.ai is None:
                raise RuntimeError("MCTS 模块不可用。")
            ai_type_engine = self.ai
        elif ai_type == 'mcts_test':
            if self.ai_test is None:
                raise RuntimeError("MCTS_test 模块不可用。")
            ai_type_engine = self.ai_test
        elif ai_type in ('kataAmazon', 'kataAmazon_gpu', 'kataAmazon_legacy'):
            #   _gpu    -> 新权重 + CUDA(GPU)
            #   _legacy -> 原始引擎(OpenCL/GPU) + 旧模型 amazons10x10
            if ai_type.endswith('_legacy'):
                backend = 'legacy'
            else:
                backend = 'gpu'
            worker_ai_type = 'kataAmazon'   # worker 内部逻辑对三种后端完全一致
        else:
            raise ValueError("Invalid AI type provided.")

        profile = (profile or AIProfile()).normalized()
        self.worker = AIWorker(
            simulator.size,
            ai_board,
            ai_queen_pos,
            simulator.current_player,
            worker_ai_type,
            ai_type_engine,
            engine_provider=self.ensure_kata_engine if worker_ai_type == 'kataAmazon' else None,
            engine_backend=backend if worker_ai_type == 'kataAmazon' else None,
            mcts_seconds=profile.mcts_seconds,
            kata_visits=profile.kata_visits,
        )
        # 将工作者移动到线程中
        self.worker.moveToThread(self.thread)

        # 连接信号与槽
        self.thread.started.connect(self.worker.run)  # 启动时运行
        self.worker.finished.connect(self.handle_ai_result)  # 处理结果
        self.worker.finished.connect(self.thread.quit)  # 结束线程
        self.worker.finished.connect(self.worker.deleteLater)  # 删除 worker
        self.thread.finished.connect(self.thread.deleteLater)  # 删除 thread
        self.thread.finished.connect(self.cleanup_thread)  # 清理引用

        # 启动线程
        self.thread.start()
        return True

    def is_busy(self):
        """Return whether an AI calculation thread is still running."""
        return self.thread is not None and self.thread.isRunning()

    def ensure_kata_engine(self, backend='gpu', visits=None):
        """确保 kataAmazon 引擎已按指定后端加载。

        两个后端各是一套 (引擎目录, 可执行文件, 模型, 配置)：
            'gpu'    新权重 + CUDA(GPU)
            'legacy' 原始引擎（OpenCL/GPU）+ 旧模型
        - 若当前引擎已是该后端，直接复用；
        - 若是另一后端，先关闭旧的再按新后端重建；
        - 重建后把当前对局历史重放进引擎，保证内部棋盘与界面一致。
        """
        visits = int(visits or (400 if backend == 'legacy' else 600))
        with self._engine_lock:
            try:
                engine = self._engine_manager.get_game_engine(
                    backend, visits, self.main_window.simulator.history_do_chess,
                    self._play_turn_on_engine, mode="gameplay")
                self.ai_engine = engine
                self.kata_backend = backend
                return engine
            except Exception:
                raise

    # 兼容旧调用名
    def init_ai_engine(self, backend='gpu', visits=None):
        self.ensure_kata_engine(backend, visits)

    def _ensure_hint_worker(self):
        if self.hint_thread is not None and self.hint_thread.isRunning():
            return
        self.hint_thread = QThread()
        self.hint_worker = HintWorker(self.size)
        self.hint_worker.moveToThread(self.hint_thread)
        self.hint_requested.connect(self.hint_worker.analyze)
        self.hint_shutdown_requested.connect(self.hint_worker.shutdown)
        self.hint_worker.finished.connect(self.hint_calculated)
        self.hint_worker.stopped.connect(self.hint_worker.deleteLater)
        self.hint_worker.stopped.connect(self.hint_thread.quit)
        self.hint_thread.finished.connect(self.hint_thread.deleteLater)
        self.hint_thread.finished.connect(self._cleanup_hint_thread)
        self.hint_thread.start()

    def start_hint_analysis(self, request_id: int, player: int, backend: str, top_n: int = 1):
        self._ensure_hint_worker()
        self.hint_requested.emit({
            'request_id': request_id,
            'player': player,
            'backend': backend,
            'top_n': top_n,
            'history': tuple(self.main_window.simulator.history_do_chess),
        })

    def cancel_hint_analysis(self):
        """Abort a stale search so a newer queued request can start promptly."""
        if self.hint_worker is not None and self.hint_worker.busy:
            self.hint_worker.abort()

    def _cleanup_hint_thread(self):
        self.hint_worker = None
        self.hint_thread = None


    def handle_ai_result(self, result):
        """
        处理从子线程返回的 AI 计算结果。
        此方法在主线程中运行。
        """
        self.move_calculated.emit(result)

    def cleanup_thread(self):
        """线程结束后清理引用"""
        self.thread = None
        self.worker = None
        if self._clear_board_pending:
            self._clear_board_pending = False
            self._clear_engines_board()
        self.calculation_finished.emit()


    def update_engine_board(self, player, start_pos, move_pos, arrow_pos):
        """Compatibility alias for committing a validated turn."""
        self.sync_committed_turn(player, start_pos, move_pos, arrow_pos)

    @staticmethod
    def _play_turn_on_engine(engine, player, start_pos, move_pos, arrow_pos):
        engine.play_turn(
            player,
            engine._convert_to_gtp_coord(*start_pos),
            engine._convert_to_gtp_coord(*move_pos),
            engine._convert_to_gtp_coord(*arrow_pos),
        )

    def sync_committed_turn(self, player, start_pos, move_pos, arrow_pos):
        """Apply one simulator-validated turn to the loaded gameplay engine."""
        with self._engine_lock:
            if not self._engine_pool:
                return
            try:
                self._engine_manager.sync_turn(
                    player, start_pos, move_pos, arrow_pos, self._play_turn_on_engine,
                    len(self.main_window.simulator.history_do_chess))
            except Exception:
                logger.exception("同步对局引擎失败；下次使用时将从历史重建")
                self._drop_ai_engine_locked()


    def undo_board(self):
        with self._engine_lock:
            if not self._engine_pool:
                return
            try:
                self._engine_manager.undo_turn(
                    len(self.main_window.simulator.history_do_chess))
            except Exception:
                logger.exception("回退对局引擎失败；下次使用时将从历史重建")
                self._drop_ai_engine_locked()

    def clear_board(self):
        # Avoid interleaving clear_board with GTP commands from a worker thread.
        if self.is_busy():
            self._clear_board_pending = True
            return False

        self._clear_engines_board()
        return True

    def _clear_engines_board(self):
        with self._engine_lock:
            if self._engine_pool:
                try:
                    self._engine_manager.clear_board()
                except Exception:
                    logger.exception("清空对局引擎失败")
                    self._drop_ai_engine_locked()

    def _drop_ai_engine_locked(self):
        self._engine_manager.close_all()
        self.ai_engine = None
        self.kata_backend = None

    def move_win_rates(self, player, top_n=3, backend=None):
        """
        返回最佳完整回合，以及选子、移动、射箭三个阶段的胜率。

        Returns:
            (candidates, best_turn, stage_win_rates)
            candidates: [(选子位置_1d, 选子阶段胜率)]。
            best_turn:  (start_1d, move_1d, arrow_1d) 或 None（无可用的最佳着法时）。
            stage_win_rates: (选子胜率, 移动胜率, 射箭胜率)，均为原行动方视角。

        兼容旧同步调用：创建临时低延迟提示引擎并按当前完整历史重放，
        不影响后台提示工作线程或正式对局引擎。
        """
        selected_backend = backend or ('gpu' if backend_available('gpu') else 'legacy')
        spec = engine_spec_for_backend(selected_backend)
        engine = None
        try:
            engine = AmazonsKataGoEngine(
                backend=selected_backend,
                config_file=spec.get('hint_cfg', spec['cfg']),
            )
            for index, turn_data in enumerate(tuple(self.main_window.simulator.history_do_chess)):
                self._play_turn_on_engine(
                    engine,
                    BLACK_AMAZON if index % 2 == 0 else WHITE_AMAZON,
                    *turn_data,
                )
            turn, stage_win_rates, _stage_visits = engine.analyze_turn_stages(player)
        except Exception as e:
            logger.exception("获取 kataAmazon 提示失败")
            return [], None, None
        finally:
            if engine is not None:
                engine.close()

        if turn is None or stage_win_rates is None:
            return [], None, None

        try:
            coords = [engine._convert_coord(coord) for coord in turn]
        except Exception as e:
            logger.warning("解析最佳完整回合失败: %s", e)
            return [], None, None

        size = self.size
        positions = tuple(r * size + c for r, c in coords)
        start_win = stage_win_rates[0]
        candidates = [] if start_win is None else [(positions[0], start_win)]
        return candidates, positions, stage_win_rates

    def shutdown(self, wait_ms: int = 5000):
        """Stop worker threads and release all engine subprocesses."""
        if self.thread is not None and self.thread.isRunning():
            self.thread.quit()
            if not self.thread.wait(wait_ms):
                with self._engine_lock:
                    if self.ai_engine is not None:
                        self.ai_engine.abort()
                self.thread.wait(3000)

        if self.hint_thread is not None and self.hint_thread.isRunning():
            self.hint_shutdown_requested.emit()
            if not self.hint_thread.wait(wait_ms):
                if self.hint_worker is not None:
                    self.hint_worker.abort()
                self.hint_thread.wait(3000)

        with self._engine_lock:
            self._drop_ai_engine_locked()



