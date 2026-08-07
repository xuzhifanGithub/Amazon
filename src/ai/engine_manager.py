"""Window-scoped lifecycle manager for gameplay KataGo engine profiles."""
from __future__ import annotations

import logging
import threading

from src.ai.amazons_engine import AmazonsKataGoEngine


logger = logging.getLogger(__name__)


class EngineManager:
    """Own engines keyed by backend and visits, never by mutable board state."""

    def __init__(self, engine_factory=AmazonsKataGoEngine):
        self._engine_factory = engine_factory
        self.engines: dict[tuple[str, int, str], AmazonsKataGoEngine] = {}
        self._lock = threading.RLock()
        self._synced_turns = 0

    def get_game_engine(self, backend: str, visits: int, history, play_turn,
                        mode: str = "gameplay"):
        key = (backend, int(visits), mode)
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
            self._synced_turns = len(tuple(history))
            return engine

    def sync_turn(self, player, start_pos, move_pos, arrow_pos, play_turn,
                  committed_turns: int):
        """Commit a validated simulator turn to every shared gameplay engine once."""
        with self._lock:
            if committed_turns <= self._synced_turns:
                return
            for (_backend, _visits, mode), engine in tuple(self.engines.items()):
                if mode == "gameplay":
                    play_turn(engine, player, start_pos, move_pos, arrow_pos)
            self._synced_turns = committed_turns

    def undo_turn(self, committed_turns: int):
        """Undo one committed turn once, even if both side agents request it."""
        with self._lock:
            if committed_turns >= self._synced_turns:
                return
            for (_backend, _visits, mode), engine in tuple(self.engines.items()):
                if mode == "gameplay":
                    engine.undo()
            self._synced_turns = committed_turns

    def clear_board(self):
        with self._lock:
            for (_backend, _visits, mode), engine in tuple(self.engines.items()):
                if mode == "gameplay":
                    engine.clear_board()
            self._synced_turns = 0

    def close_all(self):
        with self._lock:
            engines = tuple(self.engines.values())
            self.engines.clear()
            self._synced_turns = 0
        for engine in engines:
            try:
                engine.close()
            except Exception:
                logger.exception("关闭 KataGo 引擎失败")
