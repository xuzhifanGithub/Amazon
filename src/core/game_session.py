"""Single source of truth for UI-side game lifecycle state."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SessionState(str, Enum):
    IDLE = "idle"
    ANIMATING = "animating"
    AI_THINKING = "ai_thinking"
    GAME_OVER = "game_over"


@dataclass(slots=True)
class GameSessionController:
    """Tracks revisioned async work without duplicating simulator history."""

    revision: int = 0
    state: SessionState = SessionState.IDLE

    def invalidate(self, state: SessionState = SessionState.IDLE) -> int:
        self.revision += 1
        self.state = state
        return self.revision

    def begin_animation(self) -> None:
        self.state = SessionState.ANIMATING

    def begin_ai(self) -> None:
        self.state = SessionState.AI_THINKING

    def finish_turn(self, game_over: bool = False) -> None:
        self.state = SessionState.GAME_OVER if game_over else SessionState.IDLE
