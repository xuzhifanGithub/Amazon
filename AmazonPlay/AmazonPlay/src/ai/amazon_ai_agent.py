import sys
import os
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication
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
from src.ai.amazons_engine import AmazonsKataGoEngine
# 获取当前脚本的绝对路径
project_root = os.path.join(current_dir, '..', '..')
# 将项目的根目录添加到 sys.path
sys.path.append(project_root)
from src.core.simulator import  WHITE_AMAZON, BLACK_AMAZON

class AIWorker(QObject):
    """
    负责执行 AI 计算的 QObject 工作者。
    """
    finished = pyqtSignal(tuple)  # 计算结果（-1 表示错误）


    def __init__(self, board_size, board, queen_pos, current_player,ai_type,ai_type_engine):
        super().__init__()
        self.board_size = board_size
        self.board = board
        self.queenPos = queen_pos
        self.current_player = current_player
        self.ai_type = ai_type
        self.ai_type_engine = ai_type_engine



    def run(self):
        """
        在子线程中执行耗时的 AI 计算。
        """
        best_pos = None
        win_pro = -404
        max_apt = -404
        select_pro = -404

        try:
            if self.ai_type == 'mcts' or self.ai_type == 'mcts_test':
                best_move = self.ai_type_engine.uct_search(
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
            elif self.ai_type == 'kataAmazon':
                self.ai_type_engine.set_time_controls(0, 1, 1)
                best_pos = amazon_ai.UctRes()
                turn_tuple = self.ai_type_engine.get_best_turn(self.current_player)
                start_pos, move_pos, arrow_pos = turn_tuple
                start_pos = self.ai_type_engine._convert_coord(start_pos)
                move_pos = self.ai_type_engine._convert_coord(move_pos)
                arrow_pos = self.ai_type_engine._convert_coord(arrow_pos)
                print(f"坐标 - 起始: '{start_pos}', 移动: '{move_pos}', 射箭: '{arrow_pos}'")
                best_pos.From = start_pos[0]*self.board_size + start_pos[1]
                best_pos.To = move_pos[0] * self.board_size + move_pos[1]
                best_pos.Stone = arrow_pos[0] * self.board_size + arrow_pos[1]

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
        self.ai = amazon_ai.AmazonasAI()
        self.ai_test = amazon_ai_test.AmazonasAITest()
        self.ai_engine = None


    def start_thread_ai_calculation(self, ai_type):
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
        ai_type_engine = None


        if ai_type == 'mcts':
            ai_type_engine = self.ai
        elif ai_type == 'mcts_test':
            ai_type_engine = self.ai_test
        elif ai_type == 'kataAmazon':
            if self.ai_engine is None:
                self.init_ai_engine()
            ai_type_engine = self.ai_engine


        else:
            raise ValueError("Invalid AI type provided.")

        self.worker = AIWorker(
            simulator.size,
            ai_board,
            ai_queen_pos,
            simulator.current_player,
            ai_type,
            ai_type_engine
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

    def init_ai_engine(self):
        """加载AI引擎，并在成功后弹出提示窗口。"""
        # 先尝试关闭可能已存在的旧引擎实例
        if self.ai_engine:
            # self.ai_engine.close()
            # self.ai_engine = None
            return


        try:
            # 在状态栏提示用户正在加载
            self.main_window.statusBar().showMessage("正在加载AI引擎，请稍候...")
            # 初始化引擎
            self.ai_engine = AmazonsKataGoEngine()
            # 提示用户加载成功
            self.main_window.statusBar().showMessage("亚马逊棋AI引擎加载成功")
            temp_history = self.main_window.simulator.history_do_chess
            temp_side = BLACK_AMAZON
            for i in range(len(temp_history)):
                self.update_engine_board(BLACK_AMAZON if i % 2 == 0 else WHITE_AMAZON, temp_history[i][0], temp_history[i][1], temp_history[i][2])

        except Exception as e:
            # 错误处理已经使用了弹窗，保持不变
            self.main_window.show_ai_error(f"加载AI引擎失败: {e}")


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

    def update_engine_board(self, player, start_pos, move_pos, arrow_pos):
        if self.ai_engine is not None:
            gpt_start_pos = self.ai_engine._convert_to_gtp_coord(start_pos[0],start_pos[1])
            gpt_move_pos = self.ai_engine._convert_to_gtp_coord(move_pos[0], move_pos[1])
            gpt_arrow_pos = self.ai_engine._convert_to_gtp_coord(arrow_pos[0], arrow_pos[1])
            self.ai_engine.play_turn(player, gpt_start_pos, gpt_move_pos, gpt_arrow_pos)

    def undo_board(self):
        if self.ai_engine is not None:
            self.ai_engine.undo()

    def clear_board(self):
        if self.ai_engine is not None:
            self.ai_engine.clear_board()



