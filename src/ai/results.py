from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BestResult:
    """A normalized AI move and its optional analysis metadata."""

    best_pos_from: int | None = None
    best_pos_to: int | None = None
    best_pos_stone: int | None = None
    win_pro: float | None = None
    max_apt: int | None = None
    select_pro: float | None = None
    score_lead: float | None = None
    score_selfplay: float | None = None
    score_stdev: float | None = None
    utility: float | None = None
    policy_prior: float | None = None


@dataclass(slots=True, frozen=True)
class AIOutcome:
    """Result envelope used across worker-thread boundaries."""

    result: BestResult | None = None
    error: str | None = None
    resigned: bool = False

    @classmethod
    def success(cls, result: BestResult) -> "AIOutcome":
        return cls(result=result)

    @classmethod
    def failure(cls, message: str) -> "AIOutcome":
        return cls(error=message)

    @classmethod
    def resignation(cls) -> "AIOutcome":
        return cls(resigned=True)


@dataclass(slots=True, frozen=True)
class HintCandidate:
    """One complete candidate turn, always expressed in the requester's view."""

    start: int
    move: int | None = None
    arrow: int | None = None
    stage_win_rates: tuple[float | None, float | None, float | None] = (None, None, None)
    visits: tuple[int | None, int | None, int | None] = (None, None, None)


@dataclass(slots=True, frozen=True)
class HintOutcome:
    """Complete, versioned response for a three-stage hint request."""

    request_id: int
    # ``tuple[int, float]`` is retained so older callers/plugins keep working.
    candidates: tuple[HintCandidate | tuple[int, float], ...] = ()
    best_turn: tuple[int, int, int] | None = None
    stage_win_rates: tuple[float | None, float | None, float | None] | None = None
    error: str | None = None
