"""Small lifecycle manager for gameplay KataGo engine profiles."""
from __future__ import annotations

import logging
import threading

from src.ai.amazons_engine import AmazonsKataGoEngine


logger = logging.getLogger(__name__)


class EngineManager:
    """Own engines keyed by backend and visits, never by mutable board state."""

    def __init__(self, engine_factory=AmazonsKataGoEngine):
        self._engine_factory = engine_factory
        self.engines: dict[tuple[str, int], AmazonsKataGoEngine] = {}
        self._lock = threading.RLock()

    def get_game_engine(self, backend: str, visits: int, history, play_turn):
        key = (backend, int(visits))
        with self._lock:
            engine = self.engines.get(key)
            if engine is not None:
                return engine
            engine = self._engine_factory(backend=backend, max_visits=key[1])
            try:
                for index, turn in enumerate(tuple(history)):
                    play_turn(engine, 1 if index % 2 == 0 else -1, *turn)
            except Exception:
                try:
                    engine.close()
                finally:
                    raise
            self.engines[key] = engine
            return engine

    def close_all(self):
        with self._lock:
            engines = tuple(self.engines.values())
            self.engines.clear()
        for engine in engines:
            try:
                engine.close()
            except Exception:
                logger.exception("关闭 KataGo 引擎失败")
