from __future__ import annotations
import math

from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import (QPainter, QPixmap, QColor, QFont, QPen, QPolygon,
                         QPainterPath, QRadialGradient, QBrush)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect, QPointF, pyqtProperty, QRectF

from src.core.simulator import BLACK_AMAZON, WHITE_AMAZON, OBSTACLE

# 定义游戏操作的各个阶段（状态）
AWAITING_PIECE_SELECTION = 0
AWAITING_MOVE_DESTINATION = 1
AWAITING_ARROW_DESTINATION = 2

# 定义配色方案
COLOR_SCHEMES = {
    # 默认黑白配色
    'BW': {
        'WHITE_PIECE': QColor("#FFFFFF"),  # 白棋（白色）
        'BLACK_PIECE': QColor("#333333"),  # 黑棋（深灰）
        'WHITE_PIECE_BORDER': QColor("black"),  # 白棋边框（黑色）
        'BLACK_PIECE_BORDER': QColor("black"),  # 黑棋边框（黑色）
        'OBSTACLE': QColor("#808080"),  # 障碍物（灰色）
        'VALID_MOVE': QColor(120, 226, 241, 143),  # 移动目标（青色/浅蓝）
        'VALID_ARROW': QColor(251, 210, 106, 143),  # 射箭目标（橙黄色）
        'SELECTED_GLOW': QColor(80, 200, 120, 180),  # 选中棋子（绿色辉光）
        'HOVER_GLOW': QColor(150, 255, 150, 180),  # 悬停棋子（浅绿辉光）
        'SCHEME_NAME': "经典黑白"
    },
    # 红蓝配色
    'RB': {
        'WHITE_PIECE': QColor("#4A7C9D"),  # 原白棋改为蓝色
        'BLACK_PIECE': QColor("#D9534F"),  # 原黑棋改为红色
        'WHITE_PIECE_BORDER': QColor("#1C3A4A"),  # 蓝棋边框（深蓝）
        'BLACK_PIECE_BORDER': QColor("#993A37"),  # 红棋边框（深红）
        'OBSTACLE': QColor("#333333"),  # 障碍物（棕色，与红蓝配色更协调）
        'VALID_MOVE': QColor(120, 226, 241, 143),  # 移动目标（青色/浅蓝）
        'VALID_ARROW': QColor(251, 210, 106, 143),  # 射箭目标（橙黄色）
        'SELECTED_GLOW': QColor(255, 255, 100, 180),  # 选中棋子（黄色辉光）
        'HOVER_GLOW': QColor(100, 200, 255, 180),  # 悬停棋子（浅蓝辉光）
        'SCHEME_NAME': "红蓝对决"
    },
    'GS': {
        'WHITE_PIECE': QColor("#C2E2FA"),  # 白棋改为森林绿
        'BLACK_PIECE': QColor("#F9B487"),  # 黑棋改为亮绿
        'WHITE_PIECE_BORDER': QColor("#000000"),  # 深绿边框
        'BLACK_PIECE_BORDER': QColor("#000000"),  # 森林绿边框
        'OBSTACLE': QColor("#435663"),  # 障碍物（淡绿色）
        'VALID_MOVE': QColor(135, 206, 235, 143),  # 移动目标（天蓝色）
        'VALID_ARROW': QColor(255, 215, 0, 143),  # 射箭目标（金黄色）
        'SELECTED_GLOW': QColor(255, 215, 0, 180),  # 选中棋子（金色辉光）
        'HOVER_GLOW': QColor(144, 238, 144, 180),  # 悬停棋子（浅绿辉光）
    },
    # 新增：紫色系配色 (梦幻紫韵)
    'PS': {
        'WHITE_PIECE': QColor("#A3485A"),  # 白棋改为紫色
        'BLACK_PIECE': QColor("#B7A3E3"),  # 黑棋改为深紫色
        'WHITE_PIECE_BORDER': QColor("#8D5F8C"),  # 深紫边框
        'BLACK_PIECE_BORDER': QColor("#8D5F8C"),  # 紫色边框
        'OBSTACLE': QColor("#B4DEBD"),  # 障碍物（淡紫色）
        'VALID_MOVE': QColor(255, 182, 193, 143),  # 移动目标（浅粉色）
        'VALID_ARROW': QColor(255, 160, 122, 143),  # 射箭目标（浅橙色）
        'SELECTED_GLOW': QColor(255, 105, 180, 180),  # 选中棋子（粉红辉光）
        'HOVER_GLOW': QColor(221, 160, 221, 180),  # 悬停棋子（梅色辉光）
    }
}
DEFAULT_COLOR_SCHEME = 'BW'  # 默认使用黑白配色


class BoardWidget(QWidget):
    """
    亚马逊棋棋盘控件。
    负责绘制棋盘、棋子、高亮提示，并处理用户的三步式落子操作。
    为动画效果提供属性接口，并增加鼠标悬停效果。
    """
    mouse_genmove_completed = pyqtSignal(tuple, tuple, tuple)
    game_over_signal = pyqtSignal(str)

    def __init__(self, simulator, parent=None, color_scheme: str = DEFAULT_COLOR_SCHEME):  # <-- 增加 color_scheme 参数
        """
        初始化棋盘控件。
        :param simulator: AmazonsSimulator 的实例。
        :param parent: 父控件。
        :param color_scheme: 'BW' (黑白) 或 'RB' (红蓝)。
        """
        super().__init__(parent)
        self.simulator = simulator

        self.grid_size = 60
        self.margin = 40
        self.board_dim = simulator.size

        board_pixel_size = self.board_dim * self.grid_size + 2 * self.margin
        self.setFixedSize(board_pixel_size, board_pixel_size)

        # --- 引入配色方案变量 ---
        self.color_scheme_key = color_scheme.upper()
        if self.color_scheme_key not in COLOR_SCHEMES:
            self.color_scheme_key = DEFAULT_COLOR_SCHEME
        self.colors = COLOR_SCHEMES[self.color_scheme_key]
        # ------------------------

        # --- 启用鼠标跟踪以实现悬停效果 ---
        self.setMouseTracking(True)

        # 游戏交互状态
        self.game_phase = AWAITING_PIECE_SELECTION
        self.selected_piece_pos = None
        self.moved_piece_pos = None
        self.valid_moves = []
        self.last_turn = None

        # --- 用于悬停效果的状态变量 ---
        self.hovered_piece_pos = None  # 悬停在哪个棋子上
        self.hovered_path_pos = None  # 悬停在哪条路径格子上

        # 简化的动画属性
        self.is_animating = False
        self.hidden_pieces = set()
        self._anim_piece_pos = QPointF(0, 0)
        self._anim_arrow_pos = QPointF(0, 0)
        self._anim_piece_scale = 1.0  # 棋子缩放
        self._anim_offset_factor = 0.0  # 棋子偏移系数 (0=无偏移, 1=最大偏移)
        self._anim_glow_radius_factor = 1.0
        self._anim_glow_opacity = 0.0
        self._anim_arrow_scale = 1.0

        # --- 为动画框架定义的属性接口 ---

    @pyqtProperty(QPointF)
    def anim_piece_pos(self):
        return self._anim_piece_pos

    @anim_piece_pos.setter
    def anim_piece_pos(self, pos):
        self._anim_piece_pos = pos
        self.update()

    @pyqtProperty(QPointF)
    def anim_arrow_pos(self):
        return self._anim_arrow_pos

    @anim_arrow_pos.setter
    def anim_arrow_pos(self, pos):
        self._anim_arrow_pos = pos
        self.update()

    @pyqtProperty(float)
    def anim_piece_scale(self):
        return self._anim_piece_scale

    @anim_piece_scale.setter
    def anim_piece_scale(self, scale):
        self._anim_piece_scale = scale
        self.update()

    @pyqtProperty(float)
    def anim_offset_factor(self):
        return self._anim_offset_factor

    @anim_offset_factor.setter
    def anim_offset_factor(self, factor):
        self._anim_offset_factor = factor
        self.update()

    @pyqtProperty(float)
    def anim_arrow_scale(self):
        return self._anim_arrow_scale

    @anim_arrow_scale.setter
    def anim_arrow_scale(self, scale):
        self._anim_arrow_scale = scale
        self.update()

    @pyqtProperty(float)
    def anim_glow_radius_factor(self):
        return self._anim_glow_radius_factor

    @anim_glow_radius_factor.setter
    def anim_glow_radius_factor(self, factor):
        self._anim_glow_radius_factor = factor
        self.update()

    def paintEvent(self, event: "QPaintEvent"):
        """ 完整绘图事件 (含柔和阴影) """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. 绘制棋盘、高亮和上一步指示 (不变)
        self.draw_board_grid(painter)
        self.draw_highlights(painter)
        self.draw_last_move_indicator(painter)

        # 2. 绘制所有不在动画中、且不被隐藏的棋子 (不变)
        for r in range(self.board_dim):
            for c in range(self.board_dim):
                if (r, c) in self.hidden_pieces:
                    continue
                piece = self.simulator.board[r, c]
                if piece != 0:
                    self.draw_piece_with_shape(painter, r, c, piece)

        # 3. 如果正在播放动画，则绘制运动中的元素
        if self.is_animating:
            # ==================== [绘制移动的棋子] ====================
            piece_type = self.simulator.board[self.hidden_pieces.copy().pop()] if self.hidden_pieces else 0
            if piece_type in [WHITE_AMAZON, BLACK_AMAZON]:
                center = self._anim_piece_pos
                radius = int(self.grid_size * 0.4)

                # 使用动画属性计算当前帧的各种参数 (不变)
                scaled_radius = radius * self._anim_piece_scale
                base_offset = QPointF(-5, -5)
                current_offset = base_offset * self._anim_offset_factor
                offset_center = center + current_offset

                # --- 绘制柔和阴影 ---
                shadow_radius = scaled_radius * 1.1  # 让阴影范围比棋子稍大
                shadow_center = offset_center + QPointF(3, 3)  # 阴影的偏移位置
                shadow_gradient = QRadialGradient(shadow_center, shadow_radius)
                shadow_gradient.setColorAt(0.5, QColor(0, 0, 0, 80))  # 阴影中心颜色
                shadow_gradient.setColorAt(1.0, QColor(0, 0, 0, 0))  # 阴影边缘完全透明
                painter.setBrush(QBrush(shadow_gradient))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(shadow_center, shadow_radius, shadow_radius)

                # --- 绘制辉光 ---
                glow_opacity = int(180 * self._anim_glow_opacity)
                if glow_opacity > 0:
                    glow_radius = scaled_radius * 1.6
                    # 使用配色方案的选中辉光色
                    glow_color = self.colors['SELECTED_GLOW']
                    glow_color.setAlpha(glow_opacity)
                    gradient = QRadialGradient(QPointF(offset_center), glow_radius)
                    gradient.setColorAt(0.4, glow_color)
                    gradient.setColorAt(1.0, QColor(255, 255, 0, 0))
                    painter.setBrush(QBrush(gradient))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(offset_center, glow_radius, glow_radius)

                # --- 绘制棋子本身 ---
                # 使用配色方案的棋子颜色
                color = self.colors['WHITE_PIECE'] if piece_type == WHITE_AMAZON else self.colors['BLACK_PIECE']
                pen_color = self.colors['WHITE_PIECE_BORDER'] if piece_type == WHITE_AMAZON else self.colors['BLACK_PIECE_BORDER']
                painter.setBrush(color)
                painter.setPen(QPen(pen_color, 2))
                painter.drawEllipse(offset_center, scaled_radius, scaled_radius)

            center = self._anim_arrow_pos
            # 基础半径，用于计算最终大小
            radius = int(self.grid_size * 0.4)
            # 应用动画缩放属性，计算当前帧的正方形边长
            current_side_length = radius * 2 * self._anim_arrow_scale

            # 创建一个以 'center' 为中心的正方形
            arrow_rect = QRectF(
                center.x() - current_side_length / 2,
                center.y() - current_side_length / 2,
                current_side_length,
                current_side_length
            )

            # --- 为正方形绘制阴影 ---
            shadow_offset = 3
            shadow_rect = arrow_rect.translated(shadow_offset, shadow_offset)
            shadow_color = QColor(0, 0, 0, 70)
            painter.setBrush(shadow_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(shadow_rect)

            # --- 绘制障碍物本身为正方形 ---
            # 使用配色方案的障碍物颜色
            painter.setBrush(self.colors['OBSTACLE'])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(arrow_rect)

    # --- 交互与状态更新 ---
    def mousePressEvent(self, event: "QMouseEvent"):
        """处理用户的鼠标点击事件，驱动游戏状态机。"""
        if self.is_animating or self.simulator.game_over:
            return

        if event.button() == Qt.MouseButton.RightButton:
            self.reset_selection()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        row, col = self.get_row_col_from_coord(event.pos().x(), event.pos().y())
        if row is None:
            self.reset_selection()
            return

        if self.game_phase == AWAITING_PIECE_SELECTION:
            if self.simulator.board[row, col] == self.simulator.current_player:
                self.selected_piece_pos = (row, col)
                self.valid_moves = self.simulator.get_valid_moves(row, col)
                self.game_phase = AWAITING_MOVE_DESTINATION
                self.update()

        elif self.game_phase == AWAITING_MOVE_DESTINATION:
            if (row, col) in self.valid_moves:
                self.moved_piece_pos = (row, col)
                temp_board = self.simulator.board.copy()
                temp_board[self.moved_piece_pos] = temp_board[self.selected_piece_pos]
                temp_board[self.selected_piece_pos] = 0
                self.valid_moves = self.simulator.get_valid_moves(row, col, board_state=temp_board)
                self.game_phase = AWAITING_ARROW_DESTINATION
                self.update()
            elif self.simulator.board[row, col] == self.simulator.current_player:
                self.selected_piece_pos = (row, col)
                self.valid_moves = self.simulator.get_valid_moves(row, col)
                self.update()
            else:
                self.reset_selection()

        elif self.game_phase == AWAITING_ARROW_DESTINATION:
            if (row, col) in self.valid_moves:
                self.mouse_genmove_completed.emit(self.selected_piece_pos, self.moved_piece_pos, (row, col))
            else:
                self.reset_selection()

    # --- 处理鼠标移动事件，用于悬停效果 ---
    def mouseMoveEvent(self, event: "QMouseEvent"):
        """当鼠标在控件上移动时调用，用于更新悬停状态。"""
        if self.is_animating:
            return

        old_hover_piece = self.hovered_piece_pos
        old_hover_path = self.hovered_path_pos

        self.hovered_piece_pos = None
        self.hovered_path_pos = None

        row, col = self.get_row_col_from_coord(event.pos().x(), event.pos().y())

        if row is not None:
            if self.game_phase == AWAITING_PIECE_SELECTION:
                # 如果是等待选择棋子阶段，检查鼠标下是否是当前玩家的棋子
                if self.simulator.board[row, col] == self.simulator.current_player:
                    self.hovered_piece_pos = (row, col)
            else:
                # 如果是移动或射箭阶段，检查鼠标下是否是有效路径点
                if (row, col) in self.valid_moves:
                    self.hovered_path_pos = (row, col)

        # 只有在悬停状态改变时才重绘，避免不必要的性能开销
        if old_hover_piece != self.hovered_piece_pos or old_hover_path != self.hovered_path_pos:
            self.update()

    # --- 处理鼠标离开事件 ---
    def leaveEvent(self, event):
        """当鼠标离开控件时，清除所有悬停效果。"""
        if self.hovered_piece_pos or self.hovered_path_pos:
            self.hovered_piece_pos = None
            self.hovered_path_pos = None
            self.update()
        super().leaveEvent(event)

    def set_color_scheme(self, scheme_key: str):
        """
        更改棋盘的配色方案。
        """
        scheme_key = scheme_key.upper()
        if scheme_key in COLOR_SCHEMES:
            self.color_scheme_key = scheme_key
            self.colors = COLOR_SCHEMES[scheme_key]
            self.update()

    def set_last_turn(self, turn_details: tuple | None):
        """
        设置上一步棋的细节，用于绘制指示器。
        :param turn_details: 一个包含(start_pos, move_pos, arrow_pos)的元组，或None。
        """
        self.last_turn = turn_details
        self.update()

    def reset_selection(self):
        """重置所有选择状态，返回到初始选择阶段。"""
        self.game_phase = AWAITING_PIECE_SELECTION
        self.selected_piece_pos = None
        self.moved_piece_pos = None
        self.valid_moves = []
        self.update()

    # --- 绘图辅助方法 ---
    def draw_board_grid(self, painter: QPainter):
        """
        绘制棋盘网格背景。如果某个格子是悬停的路径点，则将其放大绘制。
        """
        painter.fillRect(self.rect(), QColor("#D0D0D0"))
        shadow_offset = 3
        shadow_color = QColor(0, 0, 0, 50)
        gap_width = 6
        base_tile_size = self.grid_size - gap_width
        base_offset = gap_width // 2

        for r in range(self.board_dim):
            for c in range(self.board_dim):
                tile_size = base_tile_size
                offset = base_offset

                # 检查当前格子是否是鼠标悬停的路径格子
                is_hovered_path = (self.hovered_path_pos == (r, c))
                if is_hovered_path:
                    # 如果是，计算放大后的尺寸和偏移，使其保持居中
                    scale = 1.08  # 放大8%
                    tile_size = int(base_tile_size * scale)
                    offset_adjust = (tile_size - base_tile_size) // 2
                    offset = base_offset - offset_adjust
                # -----------------

                rect = QRect(self.margin + c * self.grid_size + offset,
                             self.margin + r * self.grid_size + offset,
                             tile_size, tile_size)

                # 为了美观，放大的格子阴影也一起放大
                shadow_rect = rect.translated(shadow_offset, shadow_offset)
                painter.setBrush(shadow_color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(shadow_rect)

                painter.setBrush(QColor("white"))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(rect)

    def draw_highlights(self, painter: QPainter):

        if self.game_phase not in [AWAITING_MOVE_DESTINATION, AWAITING_ARROW_DESTINATION]:
            return

        glow_radius = self.grid_size * 0.7

        if self.game_phase == AWAITING_MOVE_DESTINATION:
            # 使用配色方案的移动目标高亮色
            center_color = self.colors['VALID_MOVE']
            edge_color = QColor(center_color.red(), center_color.green(), center_color.blue(), 0)
        else:  # AWAITING_ARROW_DESTINATION
            # 使用配色方案的射箭目标高亮色
            center_color = self.colors['VALID_ARROW']
            edge_color = QColor(center_color.red(), center_color.green(), center_color.blue(), 0)

        painter.setPen(Qt.PenStyle.NoPen)

        for r, c in self.valid_moves:
            center = self.get_coord_from_row_col(r, c)
            gradient = QRadialGradient(QPointF(center), glow_radius)
            gradient.setColorAt(0.2, center_color)
            gradient.setColorAt(1.0, edge_color)

            painter.setBrush(QBrush(gradient))
            cell_rect = QRect(self.margin + c * self.grid_size,
                              self.margin + r * self.grid_size,
                              self.grid_size,
                              self.grid_size)
            painter.drawRect(cell_rect)

    def draw_piece_with_shape(self, painter: QPainter, r: int, c: int, piece: int):
        """
        根据棋子是否被选中或悬停，应用不同的绘制效果。
        """
        # 计算棋子在画布上的中心坐标
        center = self.get_coord_from_row_col(r, c)
        # 计算棋子的基础半径（网格大小的40%）
        radius = int(self.grid_size * 0.4)
        # 判断当前棋子是否被选中
        is_selected = (r, c) == self.selected_piece_pos

        # --- 增加悬停状态判断 ---
        # 判断当前棋子是否处于悬停状态，且游戏处于等待选择棋子阶段
        is_hovered = (r, c) == self.hovered_piece_pos and self.game_phase == AWAITING_PIECE_SELECTION

        # 绘制选中状态的棋子（最高优先级）
        if is_selected:
            # --- 效果1: 绘制选中的棋子（放大、偏移、带选中辉光）---
            # 选中状态：放大1.15倍，向左上偏移5像素
            scale_factor = 1.15
            offset = QPoint(-5, -5)
            scaled_radius = int(radius * scale_factor)
            offset_center = center + offset

            # 绘制选中辉光效果（径向渐变）
            glow_radius = int(scaled_radius * 1.6)
            # 使用配色方案的选中辉光色
            gradient = QRadialGradient(QPointF(offset_center), glow_radius)
            gradient.setColorAt(0.4, self.colors['SELECTED_GLOW'])
            gradient.setColorAt(1.0, QColor(255, 255, 0, 0))
            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(offset_center, glow_radius, glow_radius)

            # 绘制阴影和棋子 (与原逻辑类似)
            # 添加棋子阴影，增强立体感
            shadow_offset = 3
            shadow_center = offset_center + QPoint(shadow_offset, shadow_offset)
            painter.setBrush(QColor(0, 0, 0, 70))
            painter.drawEllipse(shadow_center, scaled_radius, scaled_radius)

            # 根据棋子类型绘制不同的颜色和样式
            if piece == WHITE_AMAZON:
                # 白棋：使用 WHITE_PIECE 颜色
                # painter.setPen(QPen(QColor("black"), 2))
                painter.setPen(self.colors['WHITE_PIECE_BORDER'])
                painter.setBrush(self.colors['WHITE_PIECE'])
                painter.drawEllipse(offset_center, scaled_radius, scaled_radius)
            elif piece == BLACK_AMAZON:
                # 黑棋：使用 BLACK_PIECE 颜色
                # painter.setPen(QPen(QColor("black"), 2))
                painter.setPen(self.colors['BLACK_PIECE_BORDER'])
                painter.setBrush(self.colors['BLACK_PIECE'])
                painter.drawEllipse(offset_center, scaled_radius, scaled_radius)

        # --- 悬停效果的绘制逻辑 ---
        # 绘制悬停状态的棋子（中等优先级）
        elif is_hovered:
            # --- 效果2: 绘制悬停的棋子（放大、左移、带悬停辉光）---
            # 悬停状态：放大1.1倍，向左偏移4像素
            scale_factor = 1.1
            offset = QPoint(-4, 0)  # 向左轻微偏移
            scaled_radius = int(radius * scale_factor)
            offset_center = center + offset

            # 绘制悬停辉光效果（径向渐变）
            glow_radius = int(scaled_radius * 1.5)
            # 使用配色方案的悬停辉光色
            gradient = QRadialGradient(QPointF(offset_center), glow_radius)
            gradient.setColorAt(0.4, self.colors['HOVER_GLOW'])
            gradient.setColorAt(1.0, QColor(50, 255, 50, 0))
            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(offset_center, glow_radius, glow_radius)

            # 绘制阴影和棋子
            # 添加棋子阴影，增强立体感
            shadow_offset = 3
            shadow_center = offset_center + QPoint(shadow_offset, shadow_offset)
            painter.setBrush(QColor(0, 0, 0, 70))
            painter.drawEllipse(shadow_center, scaled_radius, scaled_radius)

            # 根据棋子类型绘制不同的颜色和样式
            if piece == WHITE_AMAZON:
                # 白棋：使用 WHITE_PIECE 颜色
                # painter.setPen(QPen(QColor("black"), 2))
                painter.setPen(self.colors['WHITE_PIECE_BORDER'])
                painter.setBrush(self.colors['WHITE_PIECE'])
                painter.drawEllipse(offset_center, scaled_radius, scaled_radius)
            elif piece == BLACK_AMAZON:
                # 黑棋：使用 BLACK_PIECE 颜色
                # painter.setPen(QPen(QColor("black"), 2))
                painter.setPen(self.colors['BLACK_PIECE_BORDER'])
                painter.setBrush(self.colors['BLACK_PIECE'])
                painter.drawEllipse(offset_center, scaled_radius, scaled_radius)
        # ------------------------------------
        else:
            # --- 效果3: 绘制普通（未选中/未悬停）的棋子或障碍 ---
            # 普通状态：不缩放，不偏移
            shadow_offset = 3
            shadow_color = QColor(0, 0, 0, 70)
            shadow_center = center + QPoint(shadow_offset, shadow_offset)
            painter.setBrush(shadow_color)
            painter.setPen(Qt.PenStyle.NoPen)

            # 根据棋子类型绘制不同的阴影形状
            if piece in [WHITE_AMAZON, BLACK_AMAZON]:
                # 棋子：圆形阴影
                painter.drawEllipse(shadow_center, radius, radius)
            elif piece == OBSTACLE:
                # 障碍物：矩形阴影
                rect_origin = QRect(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
                shadow_rect = rect_origin.translated(shadow_offset, shadow_offset)
                painter.drawRect(shadow_rect)

            # 绘制实际的棋子或障碍物
            if piece == WHITE_AMAZON:
                # 白棋：使用 WHITE_PIECE 颜色
                # painter.setPen(QPen(QColor("black"), 2))
                painter.setPen(self.colors['WHITE_PIECE_BORDER'])
                painter.setBrush(self.colors['WHITE_PIECE'])
                painter.drawEllipse(center, radius, radius)
            elif piece == BLACK_AMAZON:
                # 黑棋：使用 BLACK_PIECE 颜色
                # painter.setPen(QPen(QColor("black"), 2))
                painter.setPen(self.colors['BLACK_PIECE_BORDER'])
                painter.setBrush(self.colors['BLACK_PIECE'])
                painter.drawEllipse(center, radius, radius)
            elif piece == OBSTACLE:
                # 障碍物：使用配色方案的障碍物颜色，无边框
                painter.setBrush(self.colors['OBSTACLE'])
                painter.setPen(Qt.PenStyle.NoPen)
                rect = QRect(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
                painter.drawRect(rect)

        # 绘制最后一步移动的轨迹提示
        if self.last_turn:
            # 获取上一步的移动信息：起始位置、移动位置、箭头位置
            _start_pos, move_pos, arrow_pos = self.last_turn
            overlay_radius = int(self.grid_size * 0.3)

            # 只在棋子未被选中时显示轨迹提示
            if not is_selected:
                # 计算上一步的玩家（当前玩家的对手）
                last_player = -self.simulator.current_player
                # 根据上一步的玩家，选择提示的边框颜色，使其与棋子颜色形成对比
                pen_color = QColor("black")
                if self.color_scheme_key == 'RB':
                    # 红蓝配色下，蓝棋（原白棋）用白色描边，红棋（原黑棋）用黑色描边
                    pen_color = self.colors['WHITE_PIECE_BORDER'] if last_player == WHITE_AMAZON else self.colors['BLACK_PIECE_BORDER']
                else:  # 默认黑白配色
                    # 白棋用黑色描边，黑棋用白色描边
                    pen_color = self.colors['BLACK_PIECE_BORDER'] if last_player == WHITE_AMAZON else self.colors['WHITE_PIECE_BORDER']

                if (r, c) == move_pos:
                    # 在移动目标位置绘制圆圈提示
                    pen = QPen(pen_color, 3)
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(center, overlay_radius, overlay_radius)
                elif (r, c) == arrow_pos:
                    # 在箭头位置绘制矩形提示
                    pen = QPen(pen_color, 3)
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    rect = QRect(center.x() - overlay_radius, center.y() - overlay_radius, overlay_radius * 2,
                                 overlay_radius * 2)
                    painter.drawRect(rect)

    def draw_last_move_indicator(self, painter: QPainter):
        """
        绘制上一步移动的路径箭头，但仅在没有棋子被选中的时候显示。
        """
        # 如果当前有棋子被选中，则不绘制上一轮的轨迹线
        if self.selected_piece_pos is not None:
            return

        if not self.last_turn:
            return

        arrow_color = QColor(0, 0, 0, 180)

        start_pos, move_pos, arrow_pos = self.last_turn
        start_coord = self.get_coord_from_row_col(start_pos[0], start_pos[1])
        move_coord = self.get_coord_from_row_col(move_pos[0], move_pos[1])
        arrow_coord = self.get_coord_from_row_col(arrow_pos[0], arrow_pos[1])

        pen = QPen(arrow_color, 4, Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(arrow_color)

        self.draw_arrow(painter, start_coord, move_coord)
        self.draw_arrow(painter, move_coord, arrow_coord)

    def draw_arrow(self, painter: QPainter, p1: QPoint, p2: QPoint):
        """在 p1 和 p2 之间绘制一条带箭头的线，箭头指向 p2。"""
        painter.drawLine(p1, p2)
        angle = math.atan2(p1.y() - p2.y(), p1.x() - p2.x())
        arrow_size = 12.0
        head_p1 = p2 + QPoint(int(arrow_size * math.cos(angle + math.pi / 6)),
                              int(arrow_size * math.sin(angle + math.pi / 6)))
        head_p2 = p2 + QPoint(int(arrow_size * math.cos(angle - math.pi / 6)),
                              int(arrow_size * math.sin(angle - math.pi / 6)))
        arrow_head = QPolygon([p2, head_p1, head_p2])
        painter.drawPolygon(arrow_head)

    # --- 坐标转换工具 ---
    def get_coord_from_row_col(self, r: int, c: int) -> QPoint:
        """根据棋盘的行列计算绘图中心点坐标。"""
        center_x = self.margin + c * self.grid_size + self.grid_size // 2
        center_y = self.margin + r * self.grid_size + self.grid_size // 2
        return QPoint(center_x, center_y)

    def get_row_col_from_coord(self, x: int, y: int) -> tuple[int | None, int | None]:
        """根据像素坐标计算棋盘的行列。"""
        if not (self.margin <= x < self.margin + self.board_dim * self.grid_size and
                self.margin <= y < self.margin + self.board_dim * self.grid_size):
            return None, None
        col = (x - self.margin) // self.grid_size
        row = (y - self.margin) // self.grid_size
        return row, col