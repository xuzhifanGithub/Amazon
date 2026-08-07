from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen

from src.core.simulator import WHITE_AMAZON


def draw_hint_overlay(board, painter: QPainter):
    """Draw the complete S/M/A path for a BoardWidget-like object."""
    if board.hint_side == WHITE_AMAZON:
        best_ring = QColor(0, 80, 220)
        best_fill = QColor(30, 144, 255, 90)
        other_ring = QColor(90, 170, 255)
        other_fill = QColor(120, 190, 255, 55)
    else:
        best_ring = QColor(210, 30, 30)
        best_fill = QColor(255, 70, 70, 90)
        other_ring = QColor(240, 120, 120)
        other_fill = QColor(255, 150, 150, 55)

    move_color = QColor(0, 145, 175)
    arrow_color = QColor(225, 135, 15)
    radius = int(board.grid_size * 0.4)
    turn_centers = None

    if board.hint_best_turn and board.hint_moves:
        size = board.board_dim
        turn_centers = tuple(
            QPointF(board.get_coord_from_row_col(pos // size, pos % size))
            for pos in board.hint_best_turn
        )
        start_center, move_center, arrow_center = turn_centers
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(
            QColor(move_color.red(), move_color.green(), move_color.blue(), 165),
            3, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(start_center, move_center)
        painter.setPen(QPen(
            QColor(arrow_color.red(), arrow_color.green(), arrow_color.blue(), 175),
            3, Qt.PenStyle.DotLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(move_center, arrow_center)
        painter.restore()

    for index, (row, col, win_rate) in enumerate(board.hint_moves):
        if not (0 <= row < board.board_dim and 0 <= col < board.board_dim):
            continue
        center = QPointF(board.get_coord_from_row_col(row, col))
        ring_color = best_ring if index == 0 else other_ring
        fill_color = best_fill if index == 0 else other_fill
        painter.setPen(QPen(ring_color, 2, Qt.PenStyle.DashLine))
        painter.setBrush(QBrush(fill_color))
        painter.drawEllipse(center, radius, radius)
        _draw_rate_badge(
            board, painter, center, "S" if index == 0 else "C",
            win_rate, ring_color, vertical_anchor=-1)

    if turn_centers is None:
        return

    _start_center, move_center, arrow_center = turn_centers
    move_radius = int(board.grid_size * 0.22)
    painter.setPen(QPen(QColor(255, 255, 255, 230), 4))
    painter.setBrush(QBrush(QColor(
        move_color.red(), move_color.green(), move_color.blue(), 115)))
    painter.drawEllipse(move_center, move_radius, move_radius)
    painter.setPen(QPen(move_color, 2.5))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(move_center, move_radius, move_radius)

    if board.hint_stage_win_rates:
        move_win = board.hint_stage_win_rates[1]
        if move_win is not None:
            _draw_rate_badge(
                board, painter, move_center, "M", move_win, move_color,
                vertical_anchor=1)

    x_half = int(board.grid_size * 0.22)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor(
        arrow_color.red(), arrow_color.green(), arrow_color.blue(), 55)))
    painter.drawEllipse(arrow_center, x_half + 4, x_half + 4)
    painter.setPen(QPen(
        arrow_color, 3.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(
        QPointF(arrow_center.x() - x_half, arrow_center.y() - x_half),
        QPointF(arrow_center.x() + x_half, arrow_center.y() + x_half))
    painter.drawLine(
        QPointF(arrow_center.x() + x_half, arrow_center.y() - x_half),
        QPointF(arrow_center.x() - x_half, arrow_center.y() + x_half))

    if board.hint_stage_win_rates:
        arrow_win = board.hint_stage_win_rates[2]
        if arrow_win is not None:
            _draw_rate_badge(
                board, painter, arrow_center, "A", arrow_win, arrow_color,
                vertical_anchor=1)


def _draw_rate_badge(board, painter: QPainter, center: QPointF, stage: str,
                     win_rate: float, color: QColor, vertical_anchor: int):
    width = board.grid_size * 0.76
    height = board.grid_size * 0.28
    offset_y = vertical_anchor * board.grid_size * 0.27
    badge_rect = QRectF(
        center.x() - width / 2,
        center.y() + offset_y - height / 2,
        width,
        height,
    )

    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(0, 0, 0, 65))
    painter.drawRoundedRect(badge_rect.translated(1.5, 2.0), 7, 7)

    background = QColor(color)
    background.setAlpha(225)
    painter.setBrush(background)
    painter.setPen(QPen(QColor(255, 255, 255, 205), 1.2))
    painter.drawRoundedRect(badge_rect, 7, 7)

    stage_diameter = height * 0.72
    stage_center = QPointF(
        badge_rect.left() + height * 0.55, badge_rect.center().y())
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 235))
    painter.drawEllipse(stage_center, stage_diameter / 2, stage_diameter / 2)
    painter.setFont(QFont("Arial", 7, QFont.Weight.Bold))
    painter.setPen(color.darker(145))
    painter.drawText(
        QRectF(
            stage_center.x() - stage_diameter / 2,
            stage_center.y() - stage_diameter / 2,
            stage_diameter,
            stage_diameter,
        ),
        Qt.AlignmentFlag.AlignCenter,
        stage,
    )

    painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
    painter.setPen(QColor(255, 255, 255))
    painter.drawText(
        QRectF(
            badge_rect.left() + height * 1.02,
            badge_rect.top(),
            badge_rect.width() - height * 1.12,
            badge_rect.height(),
        ),
        Qt.AlignmentFlag.AlignCenter,
        f"{win_rate:.0f}%",
    )
    painter.restore()
