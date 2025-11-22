# src/ai/amazons_engine.py
# cmd可以打开，命令如下
# engine\amazons.exe gtp -config engine.cfg -model weights\amazons10x10.bin.gz
import subprocess
import os,sys
from PyQt6.QtCore import QObject, pyqtSignal

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
# 将项目的根目录添加到 sys.path
sys.path.append(project_root)
from src.core.simulator import WHITE_AMAZON, BLACK_AMAZON, OBSTACLE, EMPTY

class AmazonsKataGoEngine(QObject):
    """
    管理亚马逊棋 AI 引擎（基于GTP协议）的类。
    负责启动、关闭引擎，以及发送和接收GTP命令。
    """
    # 定义两个信号，用于广播通信内容
    # command_sent: 当一个命令发送给引擎时发射
    # response_received: 当从引擎接收到任何一行输出时发射
    command_sent = pyqtSignal(str)
    response_received = pyqtSignal(str)
    def __init__(self,
                 engine_dir: str = './src/ai/kataAmazonEngine',
                 engine_exe: str = 'kataAmazon.exe'):

        super().__init__()

        engine_path = os.path.join(engine_dir, engine_exe)

        if not os.path.exists(engine_path):
            raise FileNotFoundError(f"引擎文件未找到: {engine_path}")

        command = [engine_path, "gtp", "-config", "engine.cfg", "-model", "weights/amazons10x10.bin.gz"]

        startupinfo = None
        # if os.name == 'nt':
        #     startupinfo = subprocess.STARTUPINFO()
        #     startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        #     startupinfo.wShowWindow = subprocess.SW_HIDE

        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding='utf-8',
                text=True,
                bufsize=1,
                startupinfo=startupinfo,
                cwd=engine_dir
            )
        except Exception as e:
            print(f"启动AI引擎失败: {e}")
            raise

        self._wait_for_engine_ready()
        self._initialize_engine()
        print("亚马逊棋AI引擎初始化完成，准备就绪。")

    def _wait_for_engine_ready(self):
        if self.process.stdout:
            while True:
                line = self.process.stdout.readline().strip()
                # --- 打印引擎启动信息 ---
                print(f"FROM ENGINE (startup): {line}")
                self.response_received.emit(line)
                # ------------------------------
                if not line and self.process.poll() is not None:
                    raise RuntimeError("引擎在初始化时意外退出。")
                if "GTP ready, beginning main protocol loop" in line:
                    break

    def _send_command(self, command: str):
        if self.process.stdin:
            # --- 打印发送给引擎的命令 ---
            print(f"TO ENGINE: {command}")
            self.command_sent.emit(command)
            # ----------------------------------
            self.process.stdin.write(command + '\n')
            self.process.stdin.flush()

    def _read_response(self) -> str:
        """
        读取一个完整的GTP响应块。
        GTP响应块总是以一个空行结束。
        """
        response_lines = []
        if self.process.stdout:
            while True:
                line = self.process.stdout.readline().strip()
                # 实时发射信号，供GTP控制台显示
                self.response_received.emit(line)
                # 空行是GTP响应的结束标志
                if line == "":
                    break
                response_lines.append(line)
        # 将所有行合并成一个字符串返回
        return "\n".join(response_lines)

    def _execute_sync_command(self, command: str) -> str:
        """
        发送命令并处理可能的多行响应。
        """
        self._send_command(command)
        full_response = self._read_response()

        if full_response.startswith('?'):
            raise RuntimeError(f"引擎命令失败: {command}\n响应: {full_response}")

        # GTP的成功响应以 '=' 开头
        if full_response.startswith('='):
            # 移除第一行的 '='，并返回之后的所有内容
            # 这对于 showboard (返回多行) 和普通命令 (只返回=) 都有效
            return full_response.lstrip('=').strip()

        # 理论上不应发生，但作为保障
        return full_response

    def _initialize_engine(self):
        self._execute_sync_command("boardsize 10")
        self._execute_sync_command("clear_board")

    def get_best_turn(self, player: int) -> tuple[str, str, str]:
        player_char = 'b' if player == BLACK_AMAZON else 'w'
        opponent_char = 'w' if player_char == 'b' else 'b'

        start_pos_str = self._execute_sync_command(f"genmove {player_char}")
        move_pos_str = self._execute_sync_command(f"genmove {opponent_char}")
        arrow_pos_str = self._execute_sync_command(f"genmove {player_char}")

        return (start_pos_str, move_pos_str, arrow_pos_str)

    def clear_board(self):
        """向引擎发送 clear_board 命令。"""
        self._execute_sync_command("clear_board")

    def play_turn(self, player: int, start_str: str, move_str: str, arrow_str: str):
        player_char = 'b' if player == BLACK_AMAZON else 'w'
        opponent_char = 'w' if player_char == 'b' else 'b'

        self._execute_sync_command(f"play {player_char} {start_str}")
        self._execute_sync_command(f"play {opponent_char} {move_str}")
        self._execute_sync_command(f"play {player_char} {arrow_str}")

    def undo(self):
        self._execute_sync_command("undo")
        self._execute_sync_command("undo")
        self._execute_sync_command("undo")

    def set_time_controls(self, main_time: int, byo_yomi_time: int, byo_yomi_stones: int):
        """
        设置引擎的时间控制。
        :param main_time: 主要思考时间 (秒)
        :param byo_yomi_time: 读秒时间 (秒)
        :param byo_yomi_stones: 读秒期间的棋子数
        """
        byo_yomi_time = int(byo_yomi_time)
        command = f"time_settings {main_time} {byo_yomi_time} {byo_yomi_stones}"
        self._execute_sync_command(command)
        print(f"已向引擎设置时间: {command}")

    def close(self):
        if hasattr(self, 'process') and self.process.poll() is None:
            print("正在关闭亚马逊棋AI引擎...")
            self._send_command("quit")
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("引擎未能正常退出，强制终止。")
                self.process.kill()
            print("亚马逊棋AI引擎已关闭。")

    def _convert_coord(self, coord_str: str) -> tuple[int, int]:
        """将 'A1' 或 'J10' 这样的棋谱坐标转换为内部数组坐标 (9, 0) 或 (0, 8)"""
        # --- 支持大写和无'I'的列 ---
        GTP_COLS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"

        col_char = coord_str[0].upper()
        row_str = coord_str[1:]

        if col_char not in GTP_COLS:
            raise ValueError(f"无法解析的列坐标: {col_char}")

        col_idx = GTP_COLS.index(col_char)
        #row_idx = 10 - int(row_str)
        row_idx = int(row_str)-1

        return (row_idx, col_idx)

    def _convert_to_gtp_coord(self, row_idx: int, col_idx: int) -> str:
        """将内部数组坐标 (9, 0) 或 (0, 8) 转换为 'A1' 或 'J10' 这样的棋谱坐标"""
        # --- 支持大写和无'I'的列 ---
        GTP_COLS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"

        if col_idx < 0 or col_idx >= len(GTP_COLS):
            raise ValueError(f"列索引超出范围: {col_idx}")

        if row_idx < 0 or row_idx >= 10:  # 假设10x10棋盘
            raise ValueError(f"行索引超出范围: {row_idx}")

        col_char = GTP_COLS[col_idx]
        #row_number = 10 - row_idx  # 反转换：内部行索引0对应棋谱行10
        row_number = row_idx+1
        return f"{col_char}{row_number}"