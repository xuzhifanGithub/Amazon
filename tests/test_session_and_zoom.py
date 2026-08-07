from src.core.game_session import GameSessionController, SessionState
from src.core.simulator import AmazonsSimulator
from src.gui.amazon_board_widget import BoardWidget


def test_session_revision_invalidates_stale_work():
    session = GameSessionController()
    assert session.revision == 0
    session.begin_ai()
    assert session.state is SessionState.AI_THINKING
    assert session.invalidate() == 1
    assert session.state is SessionState.IDLE
    session.begin_animation()
    session.finish_turn(True)
    assert session.state is SessionState.GAME_OVER


def test_board_zoom_updates_geometry_and_resets_cache(qapp):
    board = BoardWidget(AmazonsSimulator())
    normal_size = board.size()
    board._static_board_cache = object()
    board._piece_layer_cache = object()
    board.set_zoom_percent(140)
    assert board.zoom_percent == 140
    assert board.size().width() > normal_size.width()
    assert board._static_board_cache is None
    assert board._piece_layer_cache is None
    board.set_zoom_percent(77)
    assert board.zoom_percent == 100


def test_shared_engine_manager_skips_duplicate_sync():
    from src.ai.engine_manager import EngineManager

    calls = []

    class Engine:
        def undo(self):
            calls.append("undo")

        def clear_board(self):
            calls.append("clear")

        def close(self):
            pass

    manager = EngineManager(lambda **_kwargs: Engine())
    manager.get_game_engine("gpu", 600, (), lambda *_args: None)
    manager.sync_turn(1, (6, 0), (5, 0), (6, 0),
                      lambda *_args: calls.append("play"), 1)
    manager.sync_turn(1, (6, 0), (5, 0), (6, 0),
                      lambda *_args: calls.append("play"), 1)
    manager.undo_turn(0)
    manager.undo_turn(0)
    assert calls == ["play", "undo"]
