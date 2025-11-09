# src/core/simulator.py
import numpy as np

# 定义棋盘上的实体
EMPTY = 0
WHITE_AMAZON = -1
BLACK_AMAZON = 1
OBSTACLE = 2  # 障碍 (箭)


class AmazonsSimulator:
    """
    亚马逊棋游戏的核心规则。
    这个版本修正了历史记录保存的逻辑，以确保悔棋功能完美运行。
    """
    def __init__(self, size=10):
        self.size = size
        self.board = np.zeros((size, size), dtype=np.int8)
        self.current_player = BLACK_AMAZON
        self.history = []
        self.game_over = False
        self.winner = 0
        self.reset()

    def reset(self):
        """重置游戏到初始状态。"""
        self.board.fill(EMPTY)
        self.board[0, self.size//2 - 2] = WHITE_AMAZON
        self.board[0, self.size//2 + 1] = WHITE_AMAZON
        self.board[self.size//2 - 2, 0] = WHITE_AMAZON
        self.board[self.size//2 - 2, self.size - 1] = WHITE_AMAZON

        # 黑方 (玩家-1) - 对应红方
        self.board[self.size//2 + 1, 0] = BLACK_AMAZON
        self.board[self.size//2 + 1, self.size - 1] = BLACK_AMAZON
        self.board[self.size - 1, self.size//2 - 2] = BLACK_AMAZON
        self.board[self.size - 1, self.size//2 + 1] = BLACK_AMAZON


        # 白方 (玩家1)
        # self.board[0, 3] = WHITE_AMAZON
        # self.board[0, 6] = WHITE_AMAZON
        # self.board[3, 0] = WHITE_AMAZON
        # self.board[3, 9] = WHITE_AMAZON
        # # 黑方 (玩家-1)
        # self.board[6, 0] = BLACK_AMAZON
        # self.board[6, 9] = BLACK_AMAZON
        # self.board[9, 3] = BLACK_AMAZON
        # self.board[9, 6] = BLACK_AMAZON

        self.current_player = BLACK_AMAZON
        # 历史记录只保存棋盘状态，开局时保存一次
        self.history = [self.board.copy()]
        self.game_over = False
        self.winner = 0

    def save_state(self):
        """保存当前棋盘状态到历史记录中。"""
        self.history.append(self.board.copy())

    def undo(self):
        """悔棋，撤销最近的一步棋。"""
        if len(self.history) > 1:
            self.history.pop()  # 弹出当前棋盘状态
            self.board = self.history[-1].copy() # 恢复到上一步的棋盘状态
            self.current_player *= -1 # 将玩家顺序反转回来
            self.game_over = False
            self.winner = 0
            return True
        return False

    def get_valid_moves(self, r, c, board_state=None):
        """获取一个棋子在(r, c)位置所有合法的移动或射击位置。"""
        current_board = self.board if board_state is None else board_state
        if current_board[r, c] == 0:
            return []
        moves = []
        directions = [(-1, -1), (-1, 0), (-1, 1), (0, -1),
                      (0, 1), (1, -1), (1, 0), (1, 1)]
        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            while 0 <= nr < self.size and 0 <= nc < self.size:
                if current_board[nr, nc] == 0:
                    moves.append((nr, nc))
                    nr += dr
                    nc += dc
                else:
                    break
        return moves

    def check_game_over(self):
        """检查当前玩家是否已输掉比赛。"""
        player_amazons = np.argwhere(self.board == self.current_player)
        for r, c in player_amazons:
            if self.get_valid_moves(r, c):
                return False
        self.game_over = True
        self.winner = -self.current_player
        return True

    def execute_turn(self, start_pos, move_pos, arrow_pos):
        """执行一个完整的行棋回合：移动棋子 -> 释放障碍。"""
        if self.game_over: return False

        # --- 验证阶段 (此处代码保持不变) ---
        player_piece = self.board[start_pos]
        if player_piece != self.current_player: return False
        if move_pos not in self.get_valid_moves(start_pos[0], start_pos[1]): return False
        temp_board = self.board.copy()
        temp_board[move_pos] = player_piece
        temp_board[start_pos] = EMPTY
        if arrow_pos not in self.get_valid_moves(move_pos[0], move_pos[1], board_state=temp_board): return False
        # --- 验证结束 ---

        # 执行移动
        self.board[move_pos] = player_piece
        self.board[start_pos] = EMPTY
        self.board[arrow_pos] = OBSTACLE

        # 先切换玩家，再保存状态
        self.current_player *= -1
        self.save_state()

        # 检查游戏是否结束
        self.check_game_over()

        return True

    def get_ai_data(self):
        """
        获取 C++ AI 模块所需的所有数据：
        1. 棋盘 (转换为 C++ 格式: 0, 1, 2, 3)
        2. 皇后位置列表 (1D 坐标: [[黑方1D], [白方1D]])

        返回: (ai_board, ai_queen_pos)
        """
        size = self.size

        # --- 1. 皇后位置列表获取 ---

        # 查找黑方皇后位置 (BLACK_AMAZON = 1)
        black_amazons_2d = np.argwhere(self.board == BLACK_AMAZON)
        black_amazons_1d = [r * size + c for r, c in black_amazons_2d]

        # 查找白方皇后位置 (WHITE_AMAZON = -1)
        white_amazons_2d = np.argwhere(self.board == WHITE_AMAZON)
        white_amazons_1d = [r * size + c for r, c in white_amazons_2d]

        # 返回格式: [[黑方1D], [白方1D]]
        ai_queen_pos = [black_amazons_1d, white_amazons_1d]

        # --- 2. 棋盘转换 ---
        # 映射规则：
        # Python (1:黑, -1:白, 2:障碍) -> C++ (1:红方/黑, 2:蓝方/白, 3:障碍)

        # C++ 目标值
        c_black_queen = 1  # 对应 C++ 的 RED_QUEEN
        c_white_queen = 2  # 对应 C++ 的 BLUE_QUEEN
        c_obstacle = 3  # 对应 C++ 的 STONE

        conditions = [
            self.board == BLACK_AMAZON,  # 1 -> 1
            self.board == WHITE_AMAZON,  # -1 -> 2
            self.board == OBSTACLE  # 2 -> 3
        ]
        choices = [c_black_queen, c_white_queen, c_obstacle]

        # 使用 np.select 进行多条件选择和赋值，default=EMPTY (0)
        ai_board = np.select(conditions, choices, default=EMPTY).astype(np.int32)

        return ai_board, ai_queen_pos