import sys
import os
from PyQt6.QtCore import QObject, QThread, pyqtSignal
import copy
# 确保项目根目录在 sys.path 中
current_dir = os.path.dirname(os.path.abspath(__file__))
# 导入 C++ AI 模块
module_path = os.path.join(current_dir,'src', 'build')
sys.path.append(module_path)
module_path2 = os.path.join(current_dir,'src2', 'build')
sys.path.append(module_path2)
import amazon_ai
import amazon_ai_test
class AIWorker(QObject):
    """
    负责执行 AI 计算的 QObject 工作者。
    """
    finished = pyqtSignal(tuple)  # 计算结果（-1 表示错误）


    def __init__(self, board_size, board, queen_pos, current_player,ai_type):
        super().__init__()
        self.board_size = board_size
        self.board = board
        self.queenPos = queen_pos
        self.current_player = current_player
        self.ai_type = ai_type  # 新增: AI 类型属性
        self.ai = amazon_ai.AmazonasAI()
        self.ai_test = amazon_ai_test.AmazonasAITest()


    def run(self):
        """
        在子线程中执行耗时的 AI 计算。
        """
        best_pos = None
        win_pro = None
        max_apt = None
        select_pro = None

        try:
            if self.ai_type == 'mcts':
                best_move = self.ai.uct_search(
                    self.board,
                    self.queenPos,
                    self.current_player,
                    1.0,  # 计算 1.0 秒
                    True
                )
                best_pos = best_move
                win_pro = best_move.pro
                max_apt = best_move.attempt
                select_pro = best_move.value
            elif self.ai_type == 'mcts_test':
                best_move = self.ai_test.uct_search(
                    self.board,
                    self.queenPos,
                    self.current_player,
                    1.0,  # 计算 1.0 秒
                    True
                )
                best_pos = best_move
                win_pro = best_move.pro
                max_apt = best_move.attempt
                select_pro = best_move.value
            else:
                raise ValueError("Invalid AI type provided.")

            # print(f"获胜概率: {winPro}")
            #self.main_window.statusBar().showMessage(self.winPro)
            result = (best_pos, win_pro, max_apt, select_pro)
            self.finished.emit(result)
        except Exception as e:
            print(f"AIWorker 线程错误: {e}")
            error_result = (best_pos, win_pro, max_apt, select_pro)
            self.finished.emit(error_result)  # 发生错误时发送一个特殊值


class AmazonAIAgent(QObject):
    """
    负责管理 AI 落子逻辑的类，使用独立线程。
    """
    move_calculated = pyqtSignal(tuple)

    def __init__(self, main_window_instance):
        super().__init__()
        self.main_window = main_window_instance
        self.thread = None
        self.worker = None
        self.size = self.main_window.simulator.size


    def start_ai_move(self, ai_type):
        """
        在子线程中启动 AI 计算。
        """
        # 确保没有正在运行的线程
        if self.thread is not None and self.thread.isRunning():
            return

        self.main_window.statusBar().showMessage("AI 正在思考中...")

        # 创建工作者和线程
        self.thread = QThread()
        simulator = self.main_window.simulator
        ai_board, ai_queen_pos = simulator.get_ai_data()

        self.worker = AIWorker(
            simulator.size,
            ai_board,
            ai_queen_pos,
            simulator.current_player,
            ai_type
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


    def handle_ai_result(self, result: tuple):
        """
        处理从子线程返回的 AI 计算结果。
        此方法在主线程中运行。
        """
        best_move, win_pro, maxApt, select_pro = result  # 解包元组

        if best_move == -1:
            self.main_window.statusBar().showMessage("AI 计算失败。")
            # 即使计算失败也发送信号，方便主窗口处理
            self.move_calculated.emit((-1, win_pro, maxApt, select_pro))
            return

        # simulator = self.main_window.simulator
        # row = best_move // simulator.size
        # col = best_move % simulator.size
        # ai_move_pos = (row, col)

        # 只发送计算结果，不做任何其他处理
        self.move_calculated.emit((best_move, win_pro, maxApt, select_pro))

    def cleanup_thread(self):
        """线程结束后清理引用"""
        self.thread = None
        self.worker = None
