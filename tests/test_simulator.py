import numpy as np

from src.core.simulator import AmazonsSimulator, BLACK_AMAZON, OBSTACLE


OPENING_TURN = ((6, 0), (5, 0), (6, 0))


def test_initial_state_and_reset_clear_all_history():
    game = AmazonsSimulator()
    assert np.count_nonzero(game.board == BLACK_AMAZON) == 4
    assert game.execute_turn(*OPENING_TURN)
    game.reset()
    assert game.current_player == BLACK_AMAZON
    assert len(game.history) == 1
    assert game.history_do_chess == []
    assert not game.game_over


def test_legal_turn_can_be_executed_and_undone():
    game = AmazonsSimulator()
    before = game.board.copy()
    assert game.is_legal_turn(*OPENING_TURN)
    assert game.execute_turn(*OPENING_TURN)
    assert game.board[6, 0] == OBSTACLE
    assert len(game.history_do_chess) == 1
    assert game.undo()
    assert np.array_equal(game.board, before)
    assert game.current_player == BLACK_AMAZON


def test_invalid_coordinates_and_obstacles_are_rejected():
    game = AmazonsSimulator()
    assert not game.is_legal_turn((-1, 0), (0, 0), (1, 0))
    assert not game.is_legal_turn((100, 0), (0, 0), (1, 0))
    assert game.get_valid_moves(-1, 0) == []
    game.board[5, 5] = OBSTACLE
    assert game.get_valid_moves(5, 5) == []


def test_failed_turn_does_not_mutate_history_or_board():
    game = AmazonsSimulator()
    before = game.board.copy()
    assert not game.execute_turn((6, 0), (6, 1), (6, 1))
    assert np.array_equal(game.board, before)
    assert len(game.history) == 1
    assert game.history_do_chess == []
