from types import SimpleNamespace

from src.ai.amazon_ai_agent import AIWorker
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
