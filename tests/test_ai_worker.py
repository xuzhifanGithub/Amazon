from contextlib import contextmanager
from types import SimpleNamespace

from unittest.mock import Mock

from src.ai.amazon_ai_agent import AIWorker, HintWorker
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


def test_kata_worker_holds_snapshot_engine_context_for_complete_turn():
    calls = []

    class FakeKata:
        last_winrate = 63.0
        last_visits = 700

        def get_best_turn(self, player):
            calls.append(("search", player))
            return "A1", "B2", "C3"

        @staticmethod
        def _convert_coord(coord):
            return {"A1": (0, 0), "B2": (1, 1), "C3": (2, 2)}[coord]

    @contextmanager
    def provider(backend, visits, history):
        calls.append(("acquire", backend, visits, history))
        yield FakeKata()
        calls.append(("release",))

    history = (((6, 0), (5, 0), (6, 0)),)
    worker = AIWorker(
        10, None, None, 1, "kataAmazon",
        engine_provider=provider, engine_backend="gpu",
        kata_visits=700, history=history)
    outcomes = []
    worker.finished.connect(outcomes.append)

    worker.run()

    assert calls == [
        ("acquire", "gpu", 700, history),
        ("search", 1),
        ("release",),
    ]
    assert outcomes[0].result.best_pos_from == 0
    assert outcomes[0].result.best_pos_to == 11
    assert outcomes[0].result.best_pos_stone == 22
    assert outcomes[0].result.win_pro == 63.0


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
