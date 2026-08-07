"""Persistent, per-side search-strength settings."""
from __future__ import annotations

from dataclasses import dataclass


MCTS_MIN_SECONDS = 0.5
MCTS_MAX_SECONDS = 10.0
MCTS_STEP_SECONDS = 0.5
KATA_MIN_VISITS = 100
KATA_MAX_VISITS = 2000
KATA_STEP_VISITS = 50


@dataclass(frozen=True, slots=True)
class AIProfile:
    """Search parameters captured when an AI turn starts."""

    mcts_seconds: float = 1.0
    kata_visits: int = 600

    def normalized(self) -> "AIProfile":
        seconds = max(MCTS_MIN_SECONDS, min(MCTS_MAX_SECONDS, float(self.mcts_seconds)))
        seconds = round(seconds / MCTS_STEP_SECONDS) * MCTS_STEP_SECONDS
        visits = max(KATA_MIN_VISITS, min(KATA_MAX_VISITS, int(self.kata_visits)))
        visits = round(visits / KATA_STEP_VISITS) * KATA_STEP_VISITS
        return AIProfile(seconds, visits)


def default_kata_visits(backend: str | None = None) -> int:
    return 400 if backend == "legacy" else 600


def load_profile(settings, side_key: str, backend: str | None = None) -> AIProfile:
    """Read one side's settings while accepting old/invalid settings files."""
    default = AIProfile(kata_visits=default_kata_visits(backend))
    profile = AIProfile(
        settings.value(f"ai/{side_key}/mcts_seconds", default.mcts_seconds, type=float),
        settings.value(f"ai/{side_key}/kata_visits", default.kata_visits, type=int),
    ).normalized()
    return profile


def save_profile(settings, side_key: str, profile: AIProfile) -> AIProfile:
    profile = profile.normalized()
    settings.setValue(f"ai/{side_key}/mcts_seconds", profile.mcts_seconds)
    settings.setValue(f"ai/{side_key}/kata_visits", profile.kata_visits)
    return profile
