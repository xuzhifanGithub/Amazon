"""Window-scoped lifecycle manager for gameplay KataGo engine profiles."""
from __future__ import annotations

from contextlib import contextmanager
import logging
import threading

from src.ai.amazons_engine import AmazonsKataGoEngine
from src.ai.ai_profile import KataSearchConfig


logger = logging.getLogger(__name__)


class EngineManager:
    """Own engines keyed by immutable search settings, never by board state."""

    def __init__(self, engine_factory=AmazonsKataGoEngine):
        self._engine_factory = engine_factory
        self.engines: dict[
            tuple[
                str, int, str, bool | None, KataSearchConfig | None
            ], AmazonsKataGoEngine
        ] = {}
        self._lock = threading.RLock()
        self._usage_lock = threading.Lock()
        self._active_operations = 0
        self._reset_pending = False
        self._synced_turns = 0

    @staticmethod
    def _close_engines(engines, force: bool = False) -> None:
        for engine in engines:
            try:
                if force and hasattr(engine, "abort"):
                    engine.abort()
                else:
                    engine.close()
            except Exception:
                logger.exception("关闭 KataGo 引擎失败")

    def _detach_engines_locked(self):
        engines = tuple(self.engines.values())
        self.engines.clear()
        self._synced_turns = 0
        self._reset_pending = False
        return engines

    def has_game_engine(self, backend: str, visits: int,
                        mode: str = "gameplay",
                        score_utility_enabled: bool | None = None,
                        search_config: KataSearchConfig | None = None) -> bool:
        """Return whether a matching initialized engine is already pooled."""
        search_config = (
            search_config.normalized() if search_config is not None else None)
        key = (
            backend,
            int(visits),
            mode,
            score_utility_enabled,
            search_config,
        )
        with self._lock:
            return key in self.engines

    def get_game_engine(self, backend: str, visits: int, history, play_turn,
                        mode: str = "gameplay",
                        score_utility_enabled: bool | None = None,
                        search_config: KataSearchConfig | None = None,
                        position=None, set_position=None):
        search_config = (
            search_config.normalized() if search_config is not None else None)
        key = (
            backend,
            int(visits),
            mode,
            score_utility_enabled,
            search_config,
        )
        history = tuple(history)
        with self._lock:
            engine = self.engines.get(key)
            if engine is not None:
                return engine

        # Engine startup and history replay can take minutes on first OpenCL
        # use.  They must not hold the manager state lock, otherwise a GUI
        # reset cannot even mark the active request as stale.
        engine = self._engine_factory(
            backend=backend,
            max_visits=key[1],
            score_utility_enabled=score_utility_enabled,
            search_config=search_config,
        )
        try:
            if position is not None and set_position is not None:
                set_position(engine, *position)
            else:
                for index, turn in enumerate(history):
                    play_turn(engine, 1 if index % 2 == 0 else -1, *turn)
        except Exception:
            try:
                engine.close()
            finally:
                raise

        duplicate = None
        with self._lock:
            duplicate = self.engines.get(key)
            if duplicate is None:
                self.engines[key] = engine
                self._synced_turns = len(history)
                return engine
        engine.close()
        return duplicate

    @contextmanager
    def game_engine(self, backend: str, visits: int, history, play_turn,
                    mode: str = "gameplay",
                    score_utility_enabled: bool | None = None,
                    search_config: KataSearchConfig | None = None,
                    position=None, set_position=None):
        """Lease an engine for one complete search.

        Reset, undo, and sync requests never write into a search in progress.
        They instead invalidate the pool, which is rebuilt from the next
        request's immutable history snapshot after the active lease ends.
        """
        self._usage_lock.acquire()
        stale_engines = ()
        engine = None
        lease_failed = False
        try:
            with self._lock:
                if self._reset_pending:
                    stale_engines = self._detach_engines_locked()
                self._active_operations += 1
            self._close_engines(stale_engines)
            engine = self.get_game_engine(
                backend, visits, history, play_turn, mode=mode,
                score_utility_enabled=score_utility_enabled,
                search_config=search_config,
                position=position, set_position=set_position)
            try:
                yield engine
            except BaseException:
                # A GTP/search failure may leave the subprocess dead or its
                # board partially advanced. Never reuse that instance.
                lease_failed = True
                raise
        finally:
            stale_engines = []
            with self._lock:
                self._active_operations = max(0, self._active_operations - 1)
                if lease_failed and engine is not None:
                    for key, pooled_engine in tuple(self.engines.items()):
                        if pooled_engine is engine:
                            del self.engines[key]
                            stale_engines.append(engine)
                    if not self.engines:
                        self._synced_turns = 0
                if self._active_operations == 0 and self._reset_pending:
                    stale_engines.extend(self._detach_engines_locked())
            self._close_engines(stale_engines)
            self._usage_lock.release()

    def sync_turn(self, player, start_pos, move_pos, arrow_pos, play_turn,
                  committed_turns: int):
        """Commit a validated turn, or rebuild later if an engine is busy."""
        with self._lock:
            if self._active_operations:
                self._reset_pending = True
                return False
            if committed_turns <= self._synced_turns:
                return True
            for key, engine in tuple(self.engines.items()):
                if key[2] == "gameplay":
                    play_turn(engine, player, start_pos, move_pos, arrow_pos)
            self._synced_turns = committed_turns
            return True

    def undo_turn(self, committed_turns: int):
        """Undo once, or rebuild from history later if an engine is busy."""
        with self._lock:
            if self._active_operations:
                self._reset_pending = True
                return False
            if committed_turns >= self._synced_turns:
                return True
            for key, engine in tuple(self.engines.items()):
                if key[2] == "gameplay":
                    engine.undo()
            self._synced_turns = committed_turns
            return True

    def clear_board(self):
        with self._lock:
            if self._active_operations:
                self._reset_pending = True
                return False
            for key, engine in tuple(self.engines.items()):
                if key[2] == "gameplay":
                    engine.clear_board()
            self._synced_turns = 0
            return True

    def close_all(self, force: bool = False):
        """Close now when idle, otherwise close when the active lease ends."""
        with self._lock:
            if self._active_operations and not force:
                self._reset_pending = True
                return False
            engines = self._detach_engines_locked()
        self._close_engines(engines, force=force)
        return True
