from contextlib import contextmanager
from types import SimpleNamespace
import threading
import time

from unittest.mock import Mock
import pytest

from src.ai.amazon_ai_agent import (AIWorker, HintWorker, amazon_ai,
                                    amazon_ai_basic, mcts_available)
from src.ai.ai_profile import STRONGEST_KATA_SEARCH_CONFIG
from src.core.simulator import AmazonsSimulator, BLACK_AMAZON
from src.ai.results import AIOutcome


class FakeMcts:
    def __init__(self):
        self.args = None

    def uct_search(self, *_args):
        self.args = _args
        return SimpleNamespace(
            From=60,
            To=50,
            Stone=40,
            pro=55.0,
            attempt=123,
            value=0.25,
        )


def test_mcts_worker_returns_typed_success_outcome():
    engine = FakeMcts()
    worker = AIWorker(10, None, None, 1, 'mcts', engine, mcts_seconds=2.5)
    outcomes = []
    worker.finished.connect(outcomes.append)
    worker.run()
    assert len(outcomes) == 1
    assert isinstance(outcomes[0], AIOutcome)
    assert outcomes[0].error is None
    assert outcomes[0].result.best_pos_from == 60
    assert engine.args[3] == 2.5


def test_18_feature_mcts_worker_uses_the_same_search_contract():
    engine = FakeMcts()
    worker = AIWorker(10, None, None, 1, 'mcts_18', engine, mcts_seconds=3.0)
    outcomes = []
    worker.finished.connect(outcomes.append)

    worker.run()

    assert outcomes[0].error is None
    assert engine.args[3] == 3.0


def test_each_mcts_difficulty_checks_its_own_native_module():
    assert mcts_available('mcts') is (amazon_ai_basic is not None)
    assert mcts_available('mcts_18') is (amazon_ai is not None)
    assert not mcts_available('unknown')


def test_kata_worker_holds_snapshot_engine_context_for_complete_turn():
    calls = []

    class FakeKata:
        last_winrate = 63.0
        last_visits = 700
        last_score_lead = -3.5
        last_score_selfplay = 4.25
        last_score_stdev = 1.1
        last_utility = 0.48
        last_policy_prior = 0.22

        def get_best_turn(self, player):
            calls.append(("search", player))
            return "A1", "B2", "C3"

        @staticmethod
        def _convert_coord(coord):
            return {"A1": (0, 0), "B2": (1, 1), "C3": (2, 2)}[coord]

    @contextmanager
    def provider(backend, visits, history, score_utility_enabled,
                 search_config, position_board, next_player):
        calls.append((
            "acquire", backend, visits, history, score_utility_enabled,
            search_config, position_board, next_player))
        yield FakeKata()
        calls.append(("release",))

    history = (((6, 0), (5, 0), (6, 0)),)
    worker = AIWorker(
        10, None, None, 1, "kataAmazon",
        engine_provider=provider, engine_backend="gpu",
        kata_visits=700, history=history, score_utility_enabled=False,
        search_config=STRONGEST_KATA_SEARCH_CONFIG)
    outcomes = []
    worker.finished.connect(outcomes.append)

    worker.run()

    assert calls == [
        ("acquire", "gpu", 700, history, False,
         STRONGEST_KATA_SEARCH_CONFIG, None, 1),
        ("search", 1),
        ("release",),
    ]
    assert outcomes[0].result.best_pos_from == 0
    assert outcomes[0].result.best_pos_to == 11
    assert outcomes[0].result.best_pos_stone == 22
    assert outcomes[0].result.win_pro == 63.0
    assert outcomes[0].result.score_lead == -3.5
    assert outcomes[0].result.score_selfplay == 4.25
    assert outcomes[0].result.score_stdev == 1.1
    assert outcomes[0].result.utility == 0.48
    assert outcomes[0].result.policy_prior == 0.22


@pytest.mark.parametrize("backend", ["legacy", "z"])
def test_old_kata_workers_do_not_expose_untrained_score_head(backend):
    class FakeLegacyKata:
        last_winrate = 51.0
        last_visits = 400
        last_score_lead = -4.0
        last_score_selfplay = 0.2
        last_score_stdev = 19.0
        last_utility = 0.02
        last_policy_prior = 0.15

        def get_best_turn(self, _player):
            return "A1", "B2", "C3"

        @staticmethod
        def _convert_coord(coord):
            return {"A1": (0, 0), "B2": (1, 1), "C3": (2, 2)}[coord]

    @contextmanager
    def provider(_backend, _visits, _history, _score_utility_enabled,
                 _search_config, _position_board, _next_player):
        yield FakeLegacyKata()

    worker = AIWorker(
        10, None, None, 1, "kataAmazon", engine_provider=provider,
        engine_backend=backend, kata_visits=400)
    outcomes = []
    worker.finished.connect(outcomes.append)

    worker.run()

    assert outcomes[0].result.score_selfplay is None
    assert outcomes[0].result.score_stdev is None
    assert outcomes[0].result.policy_prior == 0.15


def test_kata_worker_reports_resign_as_error_instead_of_ai_resignation():
    class FakeKata:
        last_winrate = None
        last_visits = None

        def get_best_turn(self, _player):
            return "resign", "B2", "C3"

    @contextmanager
    def provider(_backend, _visits, _history, _score_utility_enabled,
                 _search_config, _position_board, _next_player):
        yield FakeKata()

    worker = AIWorker(
        10, None, None, 1, "kataAmazon", engine_provider=provider,
        engine_backend="gpu", kata_visits=600)
    outcomes = []
    worker.finished.connect(outcomes.append)
    worker.run()

    assert outcomes[0].resigned is False
    assert outcomes[0].error


def test_hint_cancel_marks_queued_request_without_killing_idle_engine():
    worker = HintWorker(10)
    worker.engine = Mock()

    worker.abort(17)

    assert worker._was_cancelled(17)
    worker.engine.abort.assert_not_called()

    worker._active_request_id = 17
    worker.abort(17)
    worker.engine.abort.assert_called_once_with()


def test_cancelled_queued_hint_does_not_start_engine():
    worker = HintWorker(10)
    worker._ensure_engine = Mock()
    worker.abort(23)

    worker.analyze({
        "request_id": 23,
        "backend": "gpu",
        "player": 1,
        "top_n": 1,
        "history": (),
    })

    worker._ensure_engine.assert_not_called()
    assert not worker.busy


def test_hint_progress_uses_gui_coordinate_labels():
    class FakeHintEngine:
        def clear_board(self):
            pass

        def ranked_start_candidates(self, _player, _top_n):
            return [("K7", 52.32, 600)]

        @staticmethod
        def gtp_coord_to_gui(coord):
            return {"K7": "J4"}[coord]

        @staticmethod
        def analyze_turn_for_start(_player, _start, start_win, start_visits,
                                   progress_callback=None):
            progress_callback("piece", start_win, start_visits)
            progress_callback("move", 53.0, 500)
            progress_callback("arrow", 54.0, 400)
            return (("K7", "J8", "H7"),
                    (start_win, 53.0, 54.0),
                    (start_visits, 500, 400))

        @staticmethod
        def _convert_coord(coord):
            return {"K7": (6, 9), "J8": (7, 8), "H7": (6, 7)}[coord]

    worker = HintWorker(10)
    worker._ensure_engine = Mock(return_value=FakeHintEngine())
    updates = []
    outcomes = []
    worker.progress.connect(updates.append)
    worker.finished.connect(outcomes.append)

    worker.analyze({
        "request_id": 31,
        "backend": "z",
        "player": BLACK_AMAZON,
        "top_n": 1,
        "history": (),
    })

    progress_text = "\n".join(update["text"] for update in updates)
    assert "J4" in progress_text
    assert "K7" not in progress_text
    assert outcomes[0].error is None


@pytest.mark.skipif(amazon_ai is None, reason="原生 MCTS 模块不可用")
def test_native_mcts_releases_gil_during_search():
    simulator = AmazonsSimulator()
    board, queens = simulator.get_ai_data()
    engine = amazon_ai.AmazonasAI()
    stop = threading.Event()
    heartbeat_ready = threading.Event()
    heartbeats = []

    def heartbeat():
        while not stop.is_set():
            heartbeats.append(time.perf_counter())
            if len(heartbeats) >= 3:
                heartbeat_ready.set()
            time.sleep(0.01)

    observer = threading.Thread(target=heartbeat)
    observer.start()
    assert heartbeat_ready.wait(1)
    search_started = time.perf_counter()
    engine.uct_search(board, queens, BLACK_AMAZON, 0.5, False)
    search_finished = time.perf_counter()
    stop.set()
    observer.join(1)

    during_search = [
        tick for tick in heartbeats if search_started < tick < search_finished]
    assert not observer.is_alive()
    assert len(during_search) >= 3


@pytest.mark.skipif(amazon_ai_basic is None, reason="基础 MCTS 模块不可用")
def test_basic_mcts_original_value_is_normalized():
    simulator = AmazonsSimulator()
    assert simulator.execute_turn((6, 0), (5, 0), (4, 0))
    board, queens = simulator.get_ai_data()

    features = amazon_ai_basic.AmazonasAI().evaluate_features(
        board, queens, simulator.current_player)

    assert -1.0 <= features['value'] <= 1.0
    # This position was about -5.12 in the unbounded original formula.  Keep
    # the sign while proving the native module no longer exposes raw magnitude.
    assert -1.0 < features['value'] < 0.0


@pytest.mark.skipif(amazon_ai_basic is None, reason="基础 MCTS 模块不可用")
def test_basic_mcts_rejects_position_without_legal_move():
    simulator = AmazonsSimulator()
    simulator.board[simulator.board == 0] = 2
    board, queens = simulator.get_ai_data()

    with pytest.raises(RuntimeError, match="no legal move"):
        amazon_ai_basic.AmazonasAI().uct_search(
            board, queens, simulator.current_player, 0.0, False)
