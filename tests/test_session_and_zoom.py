import threading

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


def test_shared_engine_reset_is_deferred_until_full_search_finishes():
    from src.ai.engine_manager import EngineManager

    created = []
    replayed = []

    class Engine:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    def factory(**_kwargs):
        engine = Engine()
        created.append(engine)
        return engine

    manager = EngineManager(factory)
    with manager.game_engine("gpu", 600, (), lambda *_args: None) as engine:
        assert manager.close_all() is False
        assert not engine.closed

    assert engine.closed
    with manager.game_engine(
            "gpu", 600, [((6, 0), (5, 0), (6, 0))],
            lambda _engine, player, *turn: replayed.append((player, turn))):
        pass
    assert len(created) == 2
    assert replayed == [(1, ((6, 0), (5, 0), (6, 0)))]
    manager.close_all()


def test_engine_startup_does_not_block_reset_request():
    from src.ai.engine_manager import EngineManager

    startup_entered = threading.Event()
    continue_startup = threading.Event()

    class Engine:
        def close(self):
            pass

    def factory(**_kwargs):
        startup_entered.set()
        assert continue_startup.wait(2)
        return Engine()

    manager = EngineManager(factory)

    def search():
        with manager.game_engine("gpu", 600, (), lambda *_args: None):
            pass

    worker = threading.Thread(target=search)
    worker.start()
    assert startup_entered.wait(1)
    assert manager.close_all() is False
    continue_startup.set()
    worker.join(2)
    assert not worker.is_alive()
    assert not manager.engines
