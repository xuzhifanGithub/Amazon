"""Persistent, per-side search-strength settings."""
from __future__ import annotations

from dataclasses import dataclass


MCTS_MIN_SECONDS = 0.5
MCTS_MAX_SECONDS = 10.0
MCTS_STEP_SECONDS = 0.5
KATA_MIN_VISITS = 100
KATA_MAX_VISITS = 2000
KATA_STEP_VISITS = 50

SEARCH_CONFIG_DEFAULT = "default"
SEARCH_CONFIG_STRONGEST = "strongest"
SEARCH_CONFIG_CUSTOM = "custom"
SEARCH_CONFIG_MODES = {
    SEARCH_CONFIG_DEFAULT,
    SEARCH_CONFIG_STRONGEST,
    SEARCH_CONFIG_CUSTOM,
}


@dataclass(frozen=True, slots=True)
class KataSearchConfig:
    """Hashable KataGo overrides used by one pooled engine instance."""

    move_temperature_early: float = 0.5
    move_temperature: float = 0.1
    policy_temperature: float = 1.1
    cpuct_exploration: float = 0.9
    cpuct_exploration_log: float = 0.6
    cpuct_exploration_base: int = 500
    use_graph_search: bool = True
    root_noise_enabled: bool = False
    subtree_value_bias_factor: float = 0.0
    num_search_threads: int = 8

    def normalized(self) -> "KataSearchConfig":
        return KataSearchConfig(
            max(0.0, min(5.0, float(self.move_temperature_early))),
            max(0.0, min(5.0, float(self.move_temperature))),
            max(0.01, min(5.0, float(self.policy_temperature))),
            max(0.1, min(3.0, float(self.cpuct_exploration))),
            max(0.0, min(3.0, float(self.cpuct_exploration_log))),
            max(1, min(10000, int(self.cpuct_exploration_base))),
            bool(self.use_graph_search),
            bool(self.root_noise_enabled),
            max(0.0, min(1.0, float(self.subtree_value_bias_factor))),
            max(1, min(32, int(self.num_search_threads))),
        )


# Fixed-budget competitive profile. One search thread matches the formal
# gen223_b evaluations and avoids multi-thread virtual-loss/scheduling noise.
STRONGEST_KATA_SEARCH_CONFIG = KataSearchConfig(
    move_temperature_early=0.0,
    move_temperature=0.0,
    policy_temperature=1.0,
    cpuct_exploration=1.0,
    cpuct_exploration_log=0.45,
    cpuct_exploration_base=500,
    use_graph_search=False,
    root_noise_enabled=False,
    subtree_value_bias_factor=0.0,
    num_search_threads=1,
)


@dataclass(frozen=True, slots=True)
class AIProfile:
    """Search parameters captured when an AI turn starts."""

    mcts_seconds: float = 1.0
    kata_visits: int = 600
    score_utility_enabled: bool = False
    search_config_mode: str = SEARCH_CONFIG_DEFAULT
    move_temperature_early: float = 0.5
    move_temperature: float = 0.1
    policy_temperature: float = 1.1
    cpuct_exploration: float = 0.9
    cpuct_exploration_log: float = 0.6
    cpuct_exploration_base: int = 500
    use_graph_search: bool = True
    root_noise_enabled: bool = False
    subtree_value_bias_factor: float = 0.0
    num_search_threads: int = 8

    @property
    def strongest_config_enabled(self) -> bool:
        return self.search_config_mode == SEARCH_CONFIG_STRONGEST

    def normalized(self) -> "AIProfile":
        mode = str(self.search_config_mode)
        if mode not in SEARCH_CONFIG_MODES:
            mode = SEARCH_CONFIG_DEFAULT
        seconds = max(MCTS_MIN_SECONDS, min(MCTS_MAX_SECONDS, float(self.mcts_seconds)))
        seconds = round(seconds / MCTS_STEP_SECONDS) * MCTS_STEP_SECONDS
        visits = max(KATA_MIN_VISITS, min(KATA_MAX_VISITS, int(self.kata_visits)))
        visits = round(visits / KATA_STEP_VISITS) * KATA_STEP_VISITS
        custom_config = KataSearchConfig(
            self.move_temperature_early,
            self.move_temperature,
            self.policy_temperature,
            self.cpuct_exploration,
            self.cpuct_exploration_log,
            self.cpuct_exploration_base,
            self.use_graph_search,
            self.root_noise_enabled,
            self.subtree_value_bias_factor,
            self.num_search_threads,
        ).normalized()
        score_utility_enabled = bool(self.score_utility_enabled)
        if mode == SEARCH_CONFIG_STRONGEST:
            seconds = 1.0
            visits = 600
            score_utility_enabled = False
            custom_config = STRONGEST_KATA_SEARCH_CONFIG
        return AIProfile(
            seconds,
            visits,
            score_utility_enabled,
            mode,
            custom_config.move_temperature_early,
            custom_config.move_temperature,
            custom_config.policy_temperature,
            custom_config.cpuct_exploration,
            custom_config.cpuct_exploration_log,
            custom_config.cpuct_exploration_base,
            custom_config.use_graph_search,
            custom_config.root_noise_enabled,
            custom_config.subtree_value_bias_factor,
            custom_config.num_search_threads,
        )

    def kata_search_config(self) -> KataSearchConfig | None:
        """Return overrides for custom/strongest modes; default uses bundled cfg."""
        profile = self.normalized()
        if profile.search_config_mode == SEARCH_CONFIG_DEFAULT:
            return None
        return KataSearchConfig(
            profile.move_temperature_early,
            profile.move_temperature,
            profile.policy_temperature,
            profile.cpuct_exploration,
            profile.cpuct_exploration_log,
            profile.cpuct_exploration_base,
            profile.use_graph_search,
            profile.root_noise_enabled,
            profile.subtree_value_bias_factor,
            profile.num_search_threads,
        )


def default_kata_visits(backend: str | None = None) -> int:
    return 400 if backend == "legacy" else 600


def load_profile(settings, side_key: str, backend: str | None = None) -> AIProfile:
    """Read one side's settings while accepting old/invalid settings files."""
    default = AIProfile(kata_visits=default_kata_visits(backend))
    mode = settings.value(
        f"ai/{side_key}/search_config_mode", "", type=str)
    if not mode:
        # Accept the short-lived boolean setting written by development builds.
        mode = (
            SEARCH_CONFIG_STRONGEST
            if settings.value(
                f"ai/{side_key}/strongest_config_enabled", False, type=bool)
            else SEARCH_CONFIG_DEFAULT
        )
    profile = AIProfile(
        settings.value(f"ai/{side_key}/mcts_seconds", default.mcts_seconds, type=float),
        settings.value(f"ai/{side_key}/kata_visits", default.kata_visits, type=int),
        settings.value(
            f"ai/{side_key}/score_utility_enabled",
            default.score_utility_enabled,
            type=bool,
        ),
        mode,
        settings.value(
            f"ai/{side_key}/move_temperature_early",
            default.move_temperature_early,
            type=float,
        ),
        settings.value(
            f"ai/{side_key}/move_temperature",
            default.move_temperature,
            type=float,
        ),
        settings.value(
            f"ai/{side_key}/policy_temperature",
            default.policy_temperature,
            type=float,
        ),
        settings.value(
            f"ai/{side_key}/cpuct_exploration",
            default.cpuct_exploration,
            type=float,
        ),
        settings.value(
            f"ai/{side_key}/cpuct_exploration_log",
            default.cpuct_exploration_log,
            type=float,
        ),
        settings.value(
            f"ai/{side_key}/cpuct_exploration_base",
            default.cpuct_exploration_base,
            type=int,
        ),
        settings.value(
            f"ai/{side_key}/use_graph_search",
            default.use_graph_search,
            type=bool,
        ),
        settings.value(
            f"ai/{side_key}/root_noise_enabled",
            default.root_noise_enabled,
            type=bool,
        ),
        settings.value(
            f"ai/{side_key}/subtree_value_bias_factor",
            default.subtree_value_bias_factor,
            type=float,
        ),
        settings.value(
            f"ai/{side_key}/num_search_threads",
            default.num_search_threads,
            type=int,
        ),
    ).normalized()
    return profile


def save_profile(settings, side_key: str, profile: AIProfile) -> AIProfile:
    profile = profile.normalized()
    values = {
        "mcts_seconds": profile.mcts_seconds,
        "kata_visits": profile.kata_visits,
        "score_utility_enabled": profile.score_utility_enabled,
        "search_config_mode": profile.search_config_mode,
        "move_temperature_early": profile.move_temperature_early,
        "move_temperature": profile.move_temperature,
        "policy_temperature": profile.policy_temperature,
        "cpuct_exploration": profile.cpuct_exploration,
        "cpuct_exploration_log": profile.cpuct_exploration_log,
        "cpuct_exploration_base": profile.cpuct_exploration_base,
        "use_graph_search": profile.use_graph_search,
        "root_noise_enabled": profile.root_noise_enabled,
        "subtree_value_bias_factor": profile.subtree_value_bias_factor,
        "num_search_threads": profile.num_search_threads,
    }
    for key, value in values.items():
        settings.setValue(f"ai/{side_key}/{key}", value)
    return profile
