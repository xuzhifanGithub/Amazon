"""Fit a cheap MCTS value proxy to KataAmazon self-play search targets.

The feature implementation mirrors the handcrafted evaluator in ``cmcts.cpp``.
All positions are normalized so that the player to move is RED/current and the
opponent is BLUE, which matches the perspective of KataGo's training targets.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
import json
from pathlib import Path
import tarfile
import numpy as np


BOARD_SIZE = 10
BOARD_AREA = BOARD_SIZE * BOARD_SIZE
PHASE_SCALE = 92.0
TERRITORY_SCALE = 92.0
MOBILITY_SCALE = 32.0
PHASE_DEGREE = 3

DIRECTIONS = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)

FEATURE_NAMES = (
    "t1",
    "t2",
    "c1",
    "c2",
    "mobility",
    "w",
    "empty_count",
    "secure_territory",
    "contested_count",
    "queen_mobility",
    "weakest_queen_mobility",
    "queen_mobility_balance",
    "liberties",
    "weakest_liberties",
    "trapped_queens",
    "reach_overlap",
    "center_control",
    "queen_spread",
    "combat_mobility",
    "weakest_combat_mobility",
    "active_queens",
    "exclusive_queen_redundancy",
    "active_area_count",
    "blocker_queens",
    "blocker_swing",
    "gateway_control",
    "queen_load_min",
    "queen_load_balance",
    "access_redundancy",
    "territory_dead_end_risk",
    "territory_cut_risk",
    "second_weakest_combat_mobility",
    "strongest_combat_mobility",
    "combat_mobility_balance",
    "combat_active_queens",
)

# Divisors only keep the optimizer inputs near unit scale. The subsequent
# weighted standardization removes the exact choice from the fitted function.
FEATURE_DIVISORS = np.asarray(
    (
        92.0,
        92.0,
        92.0,
        92.0,
        32.0,
        92.0,
        92.0,
        92.0,
        92.0,
        128.0,
        32.0,
        32.0,
        32.0,
        8.0,
        4.0,
        128.0,
        16.0,
        48.0,
        32.0,
        32.0,
        4.0,
        4.0,
        8.0,
        4.0,
        92.0,
        92.0,
        32.0,
        32.0,
        92.0,
        16.0,
        92.0,
        32.0,
        32.0,
        32.0,
        4.0,
    ),
    dtype=np.float64,
)

FORMULA_DEFAULT_FEATURES = ("t1", "t2", "c1", "c2", "mobility")

STRUCTURAL_FEATURE_GROUPS = {
    "combat": (
        "combat_mobility",
        "weakest_combat_mobility",
        "second_weakest_combat_mobility",
        "strongest_combat_mobility",
        "combat_mobility_balance",
        "combat_active_queens",
    ),
    "areas": (
        "active_queens",
        "exclusive_queen_redundancy",
        "active_area_count",
    ),
    "gates": ("blocker_queens", "blocker_swing", "gateway_control"),
    "assignment": (
        "queen_load_min",
        "queen_load_balance",
        "access_redundancy",
    ),
    "endgame": ("territory_dead_end_risk", "territory_cut_risk"),
}

_NEIGHBORS = tuple(
    tuple(
        next_row * BOARD_SIZE + next_column
        for row_delta, column_delta in DIRECTIONS
        if 0 <= (next_row := position // BOARD_SIZE + row_delta) < BOARD_SIZE
        and 0 <= (next_column := position % BOARD_SIZE + column_delta) < BOARD_SIZE
    )
    for position in range(BOARD_AREA)
)


@dataclass(frozen=True)
class FitRows:
    features: np.ndarray
    target: np.ndarray
    outcome_value: np.ndarray
    td_slow_value: np.ndarray
    td_medium_value: np.ndarray
    td_fast_value: np.ndarray
    raw_nn_value: np.ndarray
    sample_weight: np.ndarray
    visits: np.ndarray
    game_hash_chunks: np.ndarray


def mask_feature_rows(rows: FitRows, enabled_names: set[str]) -> FitRows:
    """Zero disabled columns while retaining a fixed C++ model input schema."""

    unknown = enabled_names.difference(FEATURE_NAMES)
    if unknown:
        raise ValueError(f"unknown feature names: {sorted(unknown)}")
    features = rows.features.copy()
    for index, name in enumerate(FEATURE_NAMES):
        if name not in enabled_names:
            features[:, index] = 0.0
    return FitRows(
        features=features,
        target=rows.target,
        outcome_value=rows.outcome_value,
        td_slow_value=rows.td_slow_value,
        td_medium_value=rows.td_medium_value,
        td_fast_value=rows.td_fast_value,
        raw_nn_value=rows.raw_nn_value,
        sample_weight=rows.sample_weight,
        visits=rows.visits,
        game_hash_chunks=rows.game_hash_chunks,
    )


def _shift(mask: np.ndarray, row_delta: int, col_delta: int) -> np.ndarray:
    """Move true cells by ``(row_delta, col_delta)`` without wrapping."""

    result = np.zeros_like(mask)
    src_r0 = max(0, -row_delta)
    src_r1 = min(BOARD_SIZE, BOARD_SIZE - row_delta)
    src_c0 = max(0, -col_delta)
    src_c1 = min(BOARD_SIZE, BOARD_SIZE - col_delta)
    dst_r0 = src_r0 + row_delta
    dst_r1 = src_r1 + row_delta
    dst_c0 = src_c0 + col_delta
    dst_c1 = src_c1 + col_delta
    result[..., dst_r0:dst_r1, dst_c0:dst_c1] = mask[
        ..., src_r0:src_r1, src_c0:src_c1
    ]
    return result


def _queen_distances(open_mask: np.ndarray, sources: np.ndarray) -> np.ndarray:
    batch_size = open_mask.shape[0]
    unreachable = np.int16(127)
    distances = np.full(
        (batch_size, BOARD_SIZE, BOARD_SIZE), unreachable, dtype=np.int16
    )
    distances[sources] = 0
    unseen = open_mask.copy()
    frontier = sources.copy()
    distance = 1

    while frontier.any():
        reached = np.zeros_like(open_mask)
        for row_delta, col_delta in DIRECTIONS:
            ray = _shift(frontier, row_delta, col_delta) & open_mask
            while ray.any():
                reached |= ray
                ray = _shift(ray, row_delta, col_delta) & open_mask

        new_frontier = reached & unseen
        if not new_frontier.any():
            break
        distances[new_frontier] = distance
        unseen[new_frontier] = False
        frontier = new_frontier
        distance += 1

    return distances


def _king_distances(open_mask: np.ndarray, sources: np.ndarray) -> np.ndarray:
    batch_size = open_mask.shape[0]
    unreachable = np.int16(127)
    distances = np.full(
        (batch_size, BOARD_SIZE, BOARD_SIZE), unreachable, dtype=np.int16
    )
    distances[sources] = 0
    unseen = open_mask.copy()
    frontier = sources.copy()
    distance = 1

    while frontier.any():
        reached = np.zeros_like(open_mask)
        for row_delta, col_delta in DIRECTIONS:
            reached |= _shift(frontier, row_delta, col_delta)
        new_frontier = reached & unseen
        if not new_frontier.any():
            break
        distances[new_frontier] = distance
        unseen[new_frontier] = False
        frontier = new_frontier
        distance += 1

    return distances


def _individual_queen_masks(queen_plane: np.ndarray) -> np.ndarray:
    batch_size = queen_plane.shape[0]
    row_ids, rows, cols = np.nonzero(queen_plane)
    expected_row_ids = np.repeat(np.arange(batch_size), 4)
    if row_ids.size != batch_size * 4 or not np.array_equal(row_ids, expected_row_ids):
        raise ValueError("every position must contain exactly four queens per side")

    result = np.zeros(
        (batch_size, 4, BOARD_SIZE, BOARD_SIZE), dtype=np.bool_
    )
    queen_ids = np.tile(np.arange(4), batch_size)
    result[row_ids, queen_ids, rows, cols] = True
    return result


def _individual_queen_distances(
    open_mask: np.ndarray, queen_plane: np.ndarray
) -> np.ndarray:
    """Return exact QueenMove distances for each of the four queens."""

    queen_masks = _individual_queen_masks(queen_plane)
    batch_size = open_mask.shape[0]
    repeated_open = np.repeat(open_mask[:, None, :, :], 4, axis=1)
    distances = _queen_distances(
        repeated_open.reshape(-1, BOARD_SIZE, BOARD_SIZE),
        queen_masks.reshape(-1, BOARD_SIZE, BOARD_SIZE),
    )
    return distances.reshape(batch_size, 4, BOARD_SIZE, BOARD_SIZE)


def _queen_geometry(
    open_mask: np.ndarray,
    queen_plane: np.ndarray,
    contested_destination_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return local queen mobility statistics, including fighting mobility."""

    queen_masks = _individual_queen_masks(queen_plane)
    open_with_queen_axis = open_mask[:, None, :, :]
    neighbor_counts = np.zeros_like(open_mask, dtype=np.float64)
    for row_delta, col_delta in DIRECTIONS:
        neighbor_counts += _shift(open_mask, row_delta, col_delta)
    neighbor_counts = neighbor_counts[:, None, :, :]

    legacy_mobility = np.zeros((open_mask.shape[0], 4), dtype=np.float64)
    direct_mobility = np.zeros((open_mask.shape[0], 4), dtype=np.float64)
    combat_mobility = np.zeros((open_mask.shape[0], 4), dtype=np.float64)
    reach_count = np.zeros_like(open_mask, dtype=np.int16)
    combat_mask = (
        np.zeros_like(open_with_queen_axis)
        if contested_destination_mask is None
        else contested_destination_mask[:, None, :, :]
    )
    for row_delta, col_delta in DIRECTIONS:
        ray = _shift(queen_masks, row_delta, col_delta) & open_with_queen_axis
        distance = 1
        while ray.any():
            direct_mobility += ray.sum(axis=(2, 3))
            reach_count += ray.sum(axis=1, dtype=np.int16)
            combat_mobility += (2.0 ** (-distance)) * (
                ray * combat_mask * neighbor_counts
            ).sum(axis=(2, 3))
            if distance <= 2:
                legacy_mobility += (2.0 ** (1 - distance)) * (
                    ray * neighbor_counts
                ).sum(axis=(2, 3))
            ray = _shift(ray, row_delta, col_delta) & open_with_queen_axis
            distance += 1

    liberties = (queen_masks * neighbor_counts).sum(axis=(2, 3))
    reach_overlap = np.maximum(reach_count - 1, 0).sum(axis=(1, 2))
    return (
        legacy_mobility,
        direct_mobility,
        liberties,
        reach_overlap,
        combat_mobility,
    )


def _tarjan_cut_swing(traversable: np.ndarray, empty: np.ndarray) -> np.ndarray:
    """Return empty-square swing for each articulation vertex of one board."""

    traversable = np.asarray(traversable, dtype=np.bool_).reshape(BOARD_AREA)
    empty = np.asarray(empty, dtype=np.bool_).reshape(BOARD_AREA)
    discovery = np.full(BOARD_AREA, -1, dtype=np.int16)
    low = np.zeros(BOARD_AREA, dtype=np.int16)
    parent = np.full(BOARD_AREA, -1, dtype=np.int16)
    subtree_empty = np.zeros(BOARD_AREA, dtype=np.int16)
    component_nodes: list[list[int]] = []
    time = 0

    def collect(start: int) -> list[int]:
        nodes: list[int] = []
        stack = [start]
        seen[start] = True
        while stack:
            node = stack.pop()
            nodes.append(node)
            for neighbor in _NEIGHBORS[node]:
                if traversable[neighbor] and not seen[neighbor]:
                    seen[neighbor] = True
                    stack.append(neighbor)
        return nodes

    seen = np.zeros(BOARD_AREA, dtype=np.bool_)
    for start in np.flatnonzero(traversable):
        if not seen[start]:
            component_nodes.append(collect(int(start)))

    cut_swing = np.zeros(BOARD_AREA, dtype=np.float64)
    for nodes in component_nodes:
        component_empty = int(empty[nodes].sum())
        root = nodes[0]

        def visit(node: int) -> None:
            nonlocal time
            discovery[node] = time
            low[node] = time
            time += 1
            subtree_empty[node] = int(empty[node])
            separated_empty: list[int] = []
            for neighbor in _NEIGHBORS[node]:
                if not traversable[neighbor]:
                    continue
                if discovery[neighbor] < 0:
                    parent[neighbor] = node
                    visit(neighbor)
                    subtree_empty[node] += subtree_empty[neighbor]
                    low[node] = min(low[node], low[neighbor])
                    if low[neighbor] >= discovery[node]:
                        separated_empty.append(int(subtree_empty[neighbor]))
                elif neighbor != parent[node]:
                    low[node] = min(low[node], discovery[neighbor])

            separated_sum = sum(separated_empty)
            remainder = component_empty - int(empty[node]) - separated_sum
            parts = separated_empty + ([remainder] if remainder > 0 else [])
            total_after_removal = component_empty - int(empty[node])
            if len([part for part in parts if part > 0]) >= 2:
                cut_swing[node] = total_after_removal - max(parts)

        visit(root)
    return cut_swing


def _area_structure_features(
    current_queens: np.ndarray,
    opponent_queens: np.ndarray,
    obstacles: np.ndarray,
    current_queen_distance: np.ndarray,
    opponent_queen_distance: np.ndarray,
) -> np.ndarray:
    """Compute topology features on 8-connected non-arrow board regions."""

    batch_size = current_queens.shape[0]
    result = np.zeros((batch_size, 8), dtype=np.float64)
    for batch in range(batch_size):
        current = current_queens[batch].reshape(BOARD_AREA)
        opponent = opponent_queens[batch].reshape(BOARD_AREA)
        empty = ~(current | opponent | obstacles[batch].reshape(BOARD_AREA))
        traversable = ~obstacles[batch].reshape(BOARD_AREA)
        component = np.full(BOARD_AREA, -1, dtype=np.int16)
        components: list[list[int]] = []
        for start in np.flatnonzero(traversable):
            if component[start] >= 0:
                continue
            component_id = len(components)
            nodes: list[int] = []
            stack = [int(start)]
            component[start] = component_id
            while stack:
                node = stack.pop()
                nodes.append(node)
                for neighbor in _NEIGHBORS[node]:
                    if traversable[neighbor] and component[neighbor] < 0:
                        component[neighbor] = component_id
                        stack.append(neighbor)
            components.append(nodes)

        active_queens = 0.0
        exclusive_redundancy = 0.0
        active_area_count = 0.0
        current_dead_end_risk = 0.0
        opponent_dead_end_risk = 0.0
        current_cut_risk = 0.0
        opponent_cut_risk = 0.0
        cut_swing = _tarjan_cut_swing(traversable, empty)
        for nodes in components:
            current_count = int(current[nodes].sum())
            opponent_count = int(opponent[nodes].sum())
            empty_count = int(empty[nodes].sum())
            if empty_count == 0:
                continue
            if current_count and opponent_count:
                active_area_count += 1.0
                active_queens += current_count - opponent_count
                continue
            if not (current_count or opponent_count):
                continue

            owner_count = current_count or opponent_count
            dead_ends = sum(
                1
                for node in nodes
                if empty[node]
                and sum(traversable[neighbor] for neighbor in _NEIGHBORS[node]) <= 1
            )
            dead_end_risk = max(0, dead_ends - owner_count)
            area_cut_risk = float(
                sum(cut_swing[node] for node in nodes if empty[node])
            )
            if current_count:
                exclusive_redundancy -= max(0, current_count - 1)
                current_dead_end_risk += dead_end_risk
                current_cut_risk += area_cut_risk
            else:
                exclusive_redundancy += max(0, opponent_count - 1)
                opponent_dead_end_risk += dead_end_risk
                opponent_cut_risk += area_cut_risk

        blocker_queens = float(cut_swing[current].astype(bool).sum()) - float(
            cut_swing[opponent].astype(bool).sum()
        )
        blocker_swing = float(cut_swing[current].sum() - cut_swing[opponent].sum())
        gateway_control = 0.0
        current_distance = current_queen_distance[batch].reshape(BOARD_AREA)
        opponent_distance = opponent_queen_distance[batch].reshape(BOARD_AREA)
        for node in np.flatnonzero(empty & (cut_swing > 0.0)):
            if current_distance[node] < 127 and opponent_distance[node] < 127:
                if current_distance[node] < opponent_distance[node]:
                    gateway_control += cut_swing[node]
                elif opponent_distance[node] < current_distance[node]:
                    gateway_control -= cut_swing[node]

        result[batch] = (
            active_queens,
            exclusive_redundancy,
            active_area_count,
            blocker_queens,
            blocker_swing,
            gateway_control,
            opponent_dead_end_risk - current_dead_end_risk,
            opponent_cut_risk - current_cut_risk,
        )
    return result


def _queen_assignment_features(
    open_mask: np.ndarray,
    current_queens: np.ndarray,
    opponent_queens: np.ndarray,
    contested: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Measure how evenly the fastest queens cover currently contested space."""

    current_distance = _individual_queen_distances(open_mask, current_queens)
    opponent_distance = _individual_queen_distances(open_mask, opponent_queens)

    def loads_and_redundancy(
        distances: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        minimum = distances.min(axis=1, keepdims=True)
        fastest = (distances == minimum) & (minimum < 127)
        fastest_count = fastest.sum(axis=1)
        weights = np.divide(
            fastest,
            fastest_count[:, None, :, :],
            out=np.zeros_like(fastest, dtype=np.float64),
            where=fastest_count[:, None, :, :] > 0,
        )
        loads = (weights * contested[:, None, :, :]).sum(axis=(2, 3))
        redundancy = np.where(
            contested, np.maximum(fastest_count - 1, 0), 0
        ).sum(axis=(1, 2))
        return loads, redundancy.astype(np.float64)

    current_loads, current_redundancy = loads_and_redundancy(current_distance)
    opponent_loads, opponent_redundancy = loads_and_redundancy(opponent_distance)
    return (
        current_loads.min(axis=1) - opponent_loads.min(axis=1),
        opponent_loads.std(axis=1) - current_loads.std(axis=1),
        current_redundancy - opponent_redundancy,
    )


def _queen_position_features(queen_plane: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return rotationally symmetric center and pairwise-spread scores."""

    queen_masks = _individual_queen_masks(queen_plane)
    row_grid, column_grid = np.indices((BOARD_SIZE, BOARD_SIZE))
    center_grid = 4.5 - np.maximum(
        np.abs(row_grid - 4.5), np.abs(column_grid - 4.5)
    )
    center = (queen_masks * center_grid).sum(axis=(1, 2, 3))

    positions = np.argwhere(queen_plane)[:, 1:].reshape(-1, 4, 2)
    spread = np.zeros(queen_plane.shape[0], dtype=np.float64)
    for first in range(4):
        for second in range(first + 1, 4):
            spread += np.max(
                np.abs(positions[:, first] - positions[:, second]), axis=1
            )
    return center, spread


def _mobility_penalty(mobility: np.ndarray) -> np.ndarray:
    return np.where(
        mobility <= 5.0,
        -0.4 * mobility + 7.0,
        85.0 / (12.0 + mobility),
    )


def combat_detail_features(
    current_combat_mobility: np.ndarray,
    opponent_combat_mobility: np.ndarray,
) -> np.ndarray:
    """Summarize the four per-queen fighting-mobility values."""

    current_combat_mobility = np.asarray(
        current_combat_mobility, dtype=np.float64
    )
    opponent_combat_mobility = np.asarray(
        opponent_combat_mobility, dtype=np.float64
    )
    if (
        current_combat_mobility.ndim != 2
        or current_combat_mobility.shape[1] != 4
        or opponent_combat_mobility.shape != current_combat_mobility.shape
    ):
        raise ValueError("combat mobility arrays must have shape (N, 4)")

    current_sorted = np.sort(current_combat_mobility, axis=1)
    opponent_sorted = np.sort(opponent_combat_mobility, axis=1)
    return np.column_stack(
        (
            current_sorted[:, 1] - opponent_sorted[:, 1],
            current_sorted[:, 3] - opponent_sorted[:, 3],
            opponent_combat_mobility.std(axis=1)
            - current_combat_mobility.std(axis=1),
            (current_combat_mobility > 0.0).sum(axis=1)
            - (opponent_combat_mobility > 0.0).sum(axis=1),
        )
    )


def evaluate_feature_batch(
    current_queens: np.ndarray,
    opponent_queens: np.ndarray,
    obstacles: np.ndarray,
) -> np.ndarray:
    """Return cheap, side-relative structural features for complete turns."""

    current_queens = np.asarray(current_queens, dtype=np.bool_)
    opponent_queens = np.asarray(opponent_queens, dtype=np.bool_)
    obstacles = np.asarray(obstacles, dtype=np.bool_)
    expected_tail = (BOARD_SIZE, BOARD_SIZE)
    if (
        current_queens.ndim != 3
        or current_queens.shape[1:] != expected_tail
        or opponent_queens.shape != current_queens.shape
        or obstacles.shape != current_queens.shape
    ):
        raise ValueError("feature planes must have shape (N, 10, 10)")
    if np.any(current_queens & opponent_queens) or np.any(
        (current_queens | opponent_queens) & obstacles
    ):
        raise ValueError("queens and obstacles must not overlap")

    open_mask = ~(current_queens | opponent_queens | obstacles)

    current_t1 = _queen_distances(open_mask, current_queens)
    opponent_t1 = _queen_distances(open_mask, opponent_queens)
    t1 = (
        ((current_t1 < opponent_t1) & open_mask).sum(axis=(1, 2))
        - ((current_t1 > opponent_t1) & open_mask).sum(axis=(1, 2))
    ).astype(np.float64)

    both_reachable = open_mask & (current_t1 < 127) & (opponent_t1 < 127)
    current_reachable = open_mask & (current_t1 < 127)
    opponent_reachable = open_mask & (opponent_t1 < 127)
    distance_difference = np.abs(current_t1 - opponent_t1).astype(np.float64)
    w = np.where(both_reachable, np.exp2(-distance_difference), 0.0).sum(
        axis=(1, 2)
    )
    c1 = (
        np.where(current_reachable, np.exp2(-current_t1.astype(np.float64)), 0.0)
        - np.where(
            opponent_reachable,
            np.exp2(-opponent_t1.astype(np.float64)),
            0.0,
        )
    ).sum(axis=(1, 2))
    secure_territory = (
        (current_reachable & ~opponent_reachable).sum(axis=(1, 2))
        - (opponent_reachable & ~current_reachable).sum(axis=(1, 2))
    ).astype(np.float64)
    contested_count = both_reachable.sum(axis=(1, 2)).astype(np.float64)

    current_t2 = _king_distances(open_mask, current_queens)
    opponent_t2 = _king_distances(open_mask, opponent_queens)
    t2 = (
        ((current_t2 < opponent_t2) & open_mask).sum(axis=(1, 2))
        - ((current_t2 > opponent_t2) & open_mask).sum(axis=(1, 2))
    ).astype(np.float64)
    king_distance_margin = (
        opponent_t2.astype(np.float64) - current_t2.astype(np.float64)
    ) / 6.0
    c2 = np.where(
        open_mask & ~((current_t2 == 127) & (opponent_t2 == 127)),
        np.clip(king_distance_margin, -1.0, 1.0),
        0.0,
    ).sum(axis=(1, 2))

    (
        current_legacy_mobility,
        current_direct_mobility,
        current_liberties,
        current_reach_overlap,
        current_combat_mobility,
    ) = _queen_geometry(
        open_mask, current_queens, contested_destination_mask=opponent_reachable
    )
    (
        opponent_legacy_mobility,
        opponent_direct_mobility,
        opponent_liberties,
        opponent_reach_overlap,
        opponent_combat_mobility,
    ) = _queen_geometry(
        open_mask, opponent_queens, contested_destination_mask=current_reachable
    )
    mobility = _mobility_penalty(opponent_legacy_mobility).sum(
        axis=1
    ) - _mobility_penalty(current_legacy_mobility).sum(axis=1)
    queen_mobility = current_direct_mobility.sum(
        axis=1
    ) - opponent_direct_mobility.sum(axis=1)
    weakest_queen_mobility = current_direct_mobility.min(
        axis=1
    ) - opponent_direct_mobility.min(axis=1)
    queen_mobility_balance = opponent_direct_mobility.std(
        axis=1
    ) - current_direct_mobility.std(axis=1)
    liberties = current_liberties.sum(axis=1) - opponent_liberties.sum(axis=1)
    weakest_liberties = current_liberties.min(
        axis=1
    ) - opponent_liberties.min(axis=1)
    trapped_queens = (opponent_liberties <= 2).sum(axis=1) - (
        current_liberties <= 2
    ).sum(axis=1)
    reach_overlap = current_reach_overlap - opponent_reach_overlap
    combat_mobility = (30.0 / (5.0 + opponent_combat_mobility)).sum(
        axis=1
    ) - (30.0 / (5.0 + current_combat_mobility)).sum(axis=1)
    weakest_combat_mobility = current_combat_mobility.min(
        axis=1
    ) - opponent_combat_mobility.min(axis=1)
    combat_details = combat_detail_features(
        current_combat_mobility, opponent_combat_mobility
    )

    area_structure = _area_structure_features(
        current_queens,
        opponent_queens,
        obstacles,
        current_t1,
        opponent_t1,
    )
    (
        queen_load_min,
        queen_load_balance,
        access_redundancy,
    ) = _queen_assignment_features(
        open_mask,
        current_queens,
        opponent_queens,
        both_reachable,
    )

    current_center, current_spread = _queen_position_features(current_queens)
    opponent_center, opponent_spread = _queen_position_features(opponent_queens)
    center_control = current_center - opponent_center
    queen_spread = current_spread - opponent_spread
    empty_count = open_mask.sum(axis=(1, 2)).astype(np.float64)

    return np.column_stack(
        (
            t1,
            t2,
            c1,
            c2,
            mobility,
            w,
            empty_count,
            secure_territory,
            contested_count,
            queen_mobility,
            weakest_queen_mobility,
            queen_mobility_balance,
            liberties,
            weakest_liberties,
            trapped_queens,
            reach_overlap,
            center_control,
            queen_spread,
            combat_mobility,
            weakest_combat_mobility,
            area_structure[:, 0],
            area_structure[:, 1],
            area_structure[:, 2],
            area_structure[:, 3],
            area_structure[:, 4],
            area_structure[:, 5],
            queen_load_min,
            queen_load_balance,
            access_redundancy,
            area_structure[:, 6],
            area_structure[:, 7],
            combat_details[:, 0],
            combat_details[:, 1],
            combat_details[:, 2],
            combat_details[:, 3],
        )
    )


def rows_from_npz(npz: np.lib.npyio.NpzFile, chunk_size: int = 2048) -> FitRows:
    packed = npz["binaryInputNCHWPacked"]
    global_input = npz["globalInputNC"]
    global_targets = npz["globalTargetsNC"]

    complete_turn = (global_input[:, 0] == 0.0) & (global_input[:, 1] == 0.0)
    complete_turn &= global_targets[:, 25] > 0.0
    complete_turn &= global_targets[:, 60] > 0.0
    selected = np.flatnonzero(complete_turn)

    feature_chunks: list[np.ndarray] = []
    for start in range(0, selected.size, chunk_size):
        row_indices = selected[start : start + chunk_size]
        planes = np.unpackbits(packed[row_indices, :4, :], axis=2)[
            :, :, :BOARD_AREA
        ].reshape(-1, 4, BOARD_SIZE, BOARD_SIZE)
        if not np.all(planes[:, 1].sum(axis=(1, 2)) == 4) or not np.all(
            planes[:, 2].sum(axis=(1, 2)) == 4
        ):
            raise ValueError("decoded complete-turn row has an invalid queen count")
        feature_chunks.append(
            evaluate_feature_batch(planes[:, 1], planes[:, 2], planes[:, 3])
        )

    features = (
        np.concatenate(feature_chunks, axis=0)
        if feature_chunks
        else np.empty((0, len(FEATURE_NAMES)), dtype=np.float64)
    )
    target_rows = global_targets[selected]
    return FitRows(
        features=features,
        target=(target_rows[:, 16] - target_rows[:, 17]).astype(np.float64),
        outcome_value=(target_rows[:, 0] - target_rows[:, 1]).astype(np.float64),
        td_slow_value=(target_rows[:, 4] - target_rows[:, 5]).astype(np.float64),
        td_medium_value=(target_rows[:, 8] - target_rows[:, 9]).astype(np.float64),
        td_fast_value=(target_rows[:, 12] - target_rows[:, 13]).astype(np.float64),
        raw_nn_value=target_rows[:, 57].astype(np.float64),
        sample_weight=target_rows[:, 25].astype(np.float64),
        visits=target_rows[:, 60].astype(np.float64),
        game_hash_chunks=target_rows[:, 41:47].astype(np.uint64),
    )


def load_rows_from_selfplay_tar(
    archive: str | Path,
    max_files: int | None = None,
    progress: bool = True,
) -> FitRows:
    archive = Path(archive)
    all_rows: list[FitRows] = []
    with tarfile.open(archive, "r") as tar:
        members = sorted(
            (
                member
                for member in tar.getmembers()
                if "/tdata/" in member.name and member.name.endswith(".npz")
            ),
            key=lambda member: member.name,
        )
        if max_files is not None:
            members = members[:max_files]
        if not members:
            raise ValueError(f"no tdata NPZ files found in {archive}")

        for index, member in enumerate(members, start=1):
            extracted = tar.extractfile(member)
            if extracted is None:
                raise OSError(f"could not read {member.name}")
            with np.load(io.BytesIO(extracted.read())) as npz:
                rows = rows_from_npz(npz)
            all_rows.append(rows)
            if progress:
                print(
                    f"[{index:02d}/{len(members):02d}] {Path(member.name).name}: "
                    f"{rows.features.shape[0]} complete-turn rows",
                    flush=True,
                )

    def concatenate(field: str) -> np.ndarray:
        return np.concatenate([getattr(rows, field) for rows in all_rows], axis=0)

    return FitRows(
        features=concatenate("features"),
        target=concatenate("target"),
        outcome_value=concatenate("outcome_value"),
        td_slow_value=concatenate("td_slow_value"),
        td_medium_value=concatenate("td_medium_value"),
        td_fast_value=concatenate("td_fast_value"),
        raw_nn_value=concatenate("raw_nn_value"),
        sample_weight=concatenate("sample_weight"),
        visits=concatenate("visits"),
        game_hash_chunks=concatenate("game_hash_chunks"),
    )


def save_rows(path: str | Path, rows: FitRows) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        feature_names=np.asarray(FEATURE_NAMES),
        features=rows.features,
        target=rows.target,
        outcome_value=rows.outcome_value,
        td_slow_value=rows.td_slow_value,
        td_medium_value=rows.td_medium_value,
        td_fast_value=rows.td_fast_value,
        raw_nn_value=rows.raw_nn_value,
        sample_weight=rows.sample_weight,
        visits=rows.visits,
        game_hash_chunks=rows.game_hash_chunks,
    )


def load_rows(path: str | Path) -> FitRows:
    with np.load(path) as npz:
        if "feature_names" in npz:
            cached_feature_names = tuple(npz["feature_names"].tolist())
            if cached_feature_names != FEATURE_NAMES:
                raise ValueError(
                    "feature cache schema does not match the current evaluator"
                )
        elif npz["features"].shape[1] != len(FEATURE_NAMES):
            raise ValueError(
                "legacy feature cache has the wrong width; extract it again"
            )
        return FitRows(
            features=npz["features"],
            target=npz["target"],
            outcome_value=(
                npz["outcome_value"] if "outcome_value" in npz else npz["target"]
            ),
            td_slow_value=(
                npz["td_slow_value"] if "td_slow_value" in npz else npz["target"]
            ),
            td_medium_value=(
                npz["td_medium_value"]
                if "td_medium_value" in npz
                else npz["target"]
            ),
            td_fast_value=(
                npz["td_fast_value"] if "td_fast_value" in npz else npz["target"]
            ),
            raw_nn_value=npz["raw_nn_value"],
            sample_weight=npz["sample_weight"],
            visits=npz["visits"],
            game_hash_chunks=npz["game_hash_chunks"],
        )


def split_buckets(game_hash_chunks: np.ndarray) -> np.ndarray:
    """Assign whole games to deterministic 80/10/10 buckets."""

    chunks = np.asarray(game_hash_chunks, dtype=np.uint64)
    mixed = np.full(chunks.shape[0], np.uint64(0x9E3779B97F4A7C15))
    with np.errstate(over="ignore"):
        for column in range(chunks.shape[1]):
            mixed ^= chunks[:, column] + np.uint64(0x9E3779B97F4A7C15)
            mixed *= np.uint64(0xBF58476D1CE4E5B9)
            mixed ^= mixed >> np.uint64(29)
    return (mixed % np.uint64(100)).astype(np.int8)


def design_matrix(features: np.ndarray) -> np.ndarray:
    features = np.asarray(features, dtype=np.float64)
    if features.ndim != 2 or features.shape[1] != len(FEATURE_NAMES):
        raise ValueError(f"features must have shape (N, {len(FEATURE_NAMES)})")
    phase_index = FEATURE_NAMES.index("w")
    phase = np.clip(features[:, phase_index] / PHASE_SCALE, 0.0, 1.0)
    phase_basis = np.column_stack([phase**degree for degree in range(4)])
    columns = [phase_basis]
    columns.extend(
        (features[:, index] / FEATURE_DIVISORS[index])[:, None] * phase_basis
        for index, name in enumerate(FEATURE_NAMES)
        if name != "w"
    )
    return np.column_stack(columns)


def predict_value(features: np.ndarray, coefficients: np.ndarray) -> np.ndarray:
    logits = design_matrix(features) @ np.asarray(coefficients, dtype=np.float64)
    return np.tanh(0.5 * logits)


def formula_design_matrix(
    features: np.ndarray,
    phase_name: str = "empty_count",
    degree: int = 3,
    coefficient_feature_names: tuple[str, ...] = FORMULA_DEFAULT_FEATURES,
) -> np.ndarray:
    """Build phase-polynomial terms for an interpretable value formula."""

    features = np.asarray(features, dtype=np.float64)
    if features.ndim != 2 or features.shape[1] != len(FEATURE_NAMES):
        raise ValueError(f"features must have shape (N, {len(FEATURE_NAMES)})")
    if phase_name not in FEATURE_NAMES:
        raise ValueError(f"unknown phase feature: {phase_name}")
    if degree < 0 or degree > 6:
        raise ValueError("formula degree must be between 0 and 6")
    unknown = set(coefficient_feature_names).difference(FEATURE_NAMES)
    if unknown:
        raise ValueError(f"unknown formula features: {sorted(unknown)}")
    if phase_name in coefficient_feature_names:
        raise ValueError("phase feature must not also be a coefficient feature")

    phase_index = FEATURE_NAMES.index(phase_name)
    phase = np.clip(
        features[:, phase_index] / FEATURE_DIVISORS[phase_index], 0.0, 1.0
    )
    phase_basis = np.column_stack(
        [phase**power for power in range(degree + 1)]
    )
    groups = [np.ones(features.shape[0], dtype=np.float64)]
    groups.extend(
        features[:, FEATURE_NAMES.index(name)]
        / FEATURE_DIVISORS[FEATURE_NAMES.index(name)]
        for name in coefficient_feature_names
    )
    return np.column_stack(
        [group[:, None] * phase_basis for group in groups]
    )


def predict_formula_value(
    features: np.ndarray, model: dict[str, object]
) -> np.ndarray:
    matrix = formula_design_matrix(
        features,
        phase_name=str(model["phase_name"]),
        degree=int(model["phase_degree"]),
        coefficient_feature_names=tuple(model["coefficient_feature_names"]),
    )
    coefficients = np.asarray(model["coefficients"], dtype=np.float64).ravel()
    return np.tanh(0.5 * (matrix @ coefficients))


def _mlp_raw_inputs(features: np.ndarray) -> np.ndarray:
    features = np.asarray(features, dtype=np.float64)
    if features.ndim != 2 or features.shape[1] != len(FEATURE_NAMES):
        raise ValueError(
            f"features must have shape (N, {len(FEATURE_NAMES)})"
        )
    return features / FEATURE_DIVISORS


def predict_relu_value(features: np.ndarray, model: dict[str, np.ndarray]) -> np.ndarray:
    inputs = (_mlp_raw_inputs(features) - model["input_mean"]) / model[
        "input_scale"
    ]
    hidden = np.maximum(
        inputs @ model["hidden_weights"].T + model["hidden_bias"], 0.0
    )
    logits = hidden @ model["output_weights"] + float(model["output_bias"])
    return np.tanh(0.5 * logits)


def _weighted_mean(values: np.ndarray, weight: np.ndarray) -> float:
    return float(np.sum(values * weight) / np.sum(weight))


def _rankdata(values: np.ndarray) -> np.ndarray:
    """Return average ranks for ties without requiring SciPy at deployment."""

    values = np.asarray(values)
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    boundaries = np.r_[
        0, np.flatnonzero(sorted_values[1:] != sorted_values[:-1]) + 1, values.size
    ]
    ranks = np.empty(values.size, dtype=np.float64)
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        ranks[order[start:end]] = 0.5 * (start + end - 1)
    return ranks


def regression_metrics(
    target: np.ndarray,
    prediction: np.ndarray,
    weight: np.ndarray,
) -> dict[str, float]:
    residual = prediction - target
    target_probability = 0.5 * (target + 1.0)
    prediction_probability = 0.5 * (prediction + 1.0)
    if target.size > 1 and np.std(target) > 0 and np.std(prediction) > 0:
        pearson = float(np.corrcoef(target, prediction)[0, 1])
        spearman = float(
            np.corrcoef(_rankdata(target), _rankdata(prediction))[0, 1]
        )
    else:
        pearson = float("nan")
        spearman = float("nan")
    return {
        "rows": int(target.size),
        "weighted_rmse": _weighted_mean(residual**2, weight) ** 0.5,
        "weighted_mae": _weighted_mean(np.abs(residual), weight),
        "weighted_brier": _weighted_mean(
            (prediction_probability - target_probability) ** 2, weight
        ),
        "pearson": pearson,
        "spearman": spearman,
        "sign_accuracy": _weighted_mean(
            (np.signbit(prediction) == np.signbit(target)).astype(np.float64),
            weight,
        ),
    }


def fit_formula_value_model(
    rows: FitRows,
    phase_name: str = "empty_count",
    degree: int = 3,
    coefficient_feature_names: tuple[str, ...] = FORMULA_DEFAULT_FEATURES,
    regularization: float = 1e-5,
    max_iterations: int = 80,
    progress: bool = True,
) -> tuple[dict[str, object], dict[str, object]]:
    """Fit a convex phase-dependent logistic formula with damped Newton steps."""

    buckets = split_buckets(rows.game_hash_chunks)
    masks = {
        "train": buckets < 80,
        "validation": (buckets >= 80) & (buckets < 90),
        "test": buckets >= 90,
    }
    train_mask = masks["train"]
    matrix = formula_design_matrix(
        rows.features,
        phase_name=phase_name,
        degree=degree,
        coefficient_feature_names=coefficient_feature_names,
    )
    x_train = matrix[train_mask]
    target = np.clip(
        0.5 * (rows.target[train_mask] + 1.0), 1e-6, 1.0 - 1e-6
    )
    weight = rows.sample_weight[train_mask]
    normalizer = float(np.sum(weight))
    column_scale = np.sqrt(np.average(x_train * x_train, axis=0, weights=weight))
    column_scale[column_scale < 1e-8] = 1.0
    x_scaled = x_train / column_scale
    coefficients = np.zeros(x_scaled.shape[1], dtype=np.float64)
    penalty_mask = np.ones_like(coefficients)
    penalty_mask[: degree + 1] = 0.0

    def sigmoid(logits: np.ndarray) -> np.ndarray:
        probabilities = np.empty_like(logits)
        positive = logits >= 0.0
        probabilities[positive] = 1.0 / (1.0 + np.exp(-logits[positive]))
        negative_exp = np.exp(logits[~positive])
        probabilities[~positive] = negative_exp / (1.0 + negative_exp)
        return probabilities

    def objective(candidate: np.ndarray) -> float:
        logits = x_scaled @ candidate
        cross_entropy = np.logaddexp(0.0, logits) - target * logits
        return float(np.sum(weight * cross_entropy) / normalizer) + (
            0.5
            * regularization
            * float(np.sum((candidate * penalty_mask) ** 2))
        )

    current_objective = objective(coefficients)
    iterations = 0
    for iteration in range(1, max_iterations + 1):
        logits = x_scaled @ coefficients
        probabilities = sigmoid(logits)
        gradient = x_scaled.T @ (weight * (probabilities - target)) / normalizer
        gradient += regularization * coefficients * penalty_mask
        curvature_weight = weight * probabilities * (1.0 - probabilities)
        hessian = (
            x_scaled.T @ (x_scaled * curvature_weight[:, None]) / normalizer
        )
        diagonal = np.diag_indices_from(hessian)
        hessian[diagonal] += regularization * penalty_mask + 1e-9
        step_direction = np.linalg.solve(hessian, gradient)

        step_size = 1.0
        accepted = False
        while step_size >= 1.0 / 1024.0:
            candidate = coefficients - step_size * step_direction
            candidate_objective = objective(candidate)
            if candidate_objective < current_objective:
                coefficients = candidate
                current_objective = candidate_objective
                accepted = True
                break
            step_size *= 0.5
        iterations = iteration
        if progress:
            print(
                f"formula iteration {iteration:02d}: "
                f"train BCE={current_objective:.8f} step={step_size:.4f}",
                flush=True,
            )
        if not accepted or np.max(np.abs(step_size * step_direction)) < 1e-8:
            break

    fitted_coefficients = coefficients / column_scale
    group_count = 1 + len(coefficient_feature_names)
    model: dict[str, object] = {
        "phase_name": phase_name,
        "phase_degree": degree,
        "coefficient_feature_names": tuple(coefficient_feature_names),
        "coefficients": fitted_coefficients.reshape(group_count, degree + 1),
    }
    metrics: dict[str, object] = {
        "optimizer": {
            "type": "damped_newton",
            "iterations": iterations,
            "train_bce": current_objective,
            "regularization": regularization,
        }
    }
    for split_name, split_mask in masks.items():
        prediction = predict_formula_value(rows.features[split_mask], model)
        metrics[split_name] = regression_metrics(
            rows.target[split_mask], prediction, rows.sample_weight[split_mask]
        )
        metrics[f"raw_nn_{split_name}"] = regression_metrics(
            rows.target[split_mask],
            np.clip(rows.raw_nn_value[split_mask], -1.0, 1.0),
            rows.sample_weight[split_mask],
        )
    return model, metrics


def fit_logistic_value_model(
    rows: FitRows,
    regularization: float = 1e-5,
) -> tuple[np.ndarray, dict[str, object]]:
    from scipy.optimize import minimize

    buckets = split_buckets(rows.game_hash_chunks)
    masks = {
        "train": buckets < 80,
        "validation": (buckets >= 80) & (buckets < 90),
        "test": buckets >= 90,
    }
    train_mask = masks["train"]
    x_train = design_matrix(rows.features[train_mask])
    y_train = np.clip(0.5 * (rows.target[train_mask] + 1.0), 1e-5, 1.0 - 1e-5)
    w_train = rows.sample_weight[train_mask]
    column_scale = np.sqrt(
        np.average(x_train * x_train, axis=0, weights=w_train)
    )
    column_scale[column_scale < 1e-8] = 1.0
    x_scaled = x_train / column_scale
    penalty_mask = np.ones(x_scaled.shape[1], dtype=np.float64)
    penalty_mask[0] = 0.0

    def objective(scaled_coefficients: np.ndarray) -> tuple[float, np.ndarray]:
        logits = x_scaled @ scaled_coefficients
        probabilities = np.empty_like(logits)
        positive = logits >= 0
        probabilities[positive] = 1.0 / (1.0 + np.exp(-logits[positive]))
        negative_exp = np.exp(logits[~positive])
        probabilities[~positive] = negative_exp / (1.0 + negative_exp)
        cross_entropy = np.logaddexp(0.0, logits) - y_train * logits
        normalizer = np.sum(w_train)
        loss = float(np.sum(w_train * cross_entropy) / normalizer)
        loss += 0.5 * regularization * float(
            np.sum((scaled_coefficients * penalty_mask) ** 2)
        )
        gradient = x_scaled.T @ (w_train * (probabilities - y_train)) / normalizer
        gradient += regularization * scaled_coefficients * penalty_mask
        return loss, gradient

    result = minimize(
        objective,
        np.zeros(x_scaled.shape[1], dtype=np.float64),
        method="L-BFGS-B",
        jac=True,
        options={"maxiter": 1000, "ftol": 1e-12, "gtol": 1e-8},
    )
    if not result.success:
        raise RuntimeError(f"value fit failed: {result.message}")
    coefficients = result.x / column_scale

    metrics: dict[str, object] = {
        "optimizer": {
            "success": bool(result.success),
            "iterations": int(result.nit),
            "loss": float(result.fun),
            "regularization": regularization,
        }
    }
    for split_name, split_mask in masks.items():
        prediction = predict_value(rows.features[split_mask], coefficients)
        metrics[split_name] = regression_metrics(
            rows.target[split_mask], prediction, rows.sample_weight[split_mask]
        )
        metrics[f"raw_nn_{split_name}"] = regression_metrics(
            rows.target[split_mask],
            np.clip(rows.raw_nn_value[split_mask], -1.0, 1.0),
            rows.sample_weight[split_mask],
        )
    return coefficients, metrics


def fit_relu_value_model(
    rows: FitRows,
    hidden_size: int = 32,
    epochs: int = 80,
    batch_size: int = 4096,
    learning_rate: float = 3e-3,
    weight_decay: float = 1e-5,
    patience: int = 12,
    seed: int = 217,
    progress: bool = True,
) -> tuple[dict[str, np.ndarray], dict[str, object]]:
    buckets = split_buckets(rows.game_hash_chunks)
    masks = {
        "train": buckets < 80,
        "validation": (buckets >= 80) & (buckets < 90),
        "test": buckets >= 90,
    }
    train_mask = masks["train"]
    validation_mask = masks["validation"]

    raw_inputs = _mlp_raw_inputs(rows.features)
    train_weight = rows.sample_weight[train_mask]
    input_mean = np.average(raw_inputs[train_mask], axis=0, weights=train_weight)
    input_scale = np.sqrt(
        np.average(
            (raw_inputs[train_mask] - input_mean) ** 2,
            axis=0,
            weights=train_weight,
        )
    )
    input_scale[input_scale < 1e-6] = 1.0
    inputs = ((raw_inputs - input_mean) / input_scale).astype(np.float32)
    targets = np.clip(0.5 * (rows.target + 1.0), 1e-5, 1.0 - 1e-5).astype(
        np.float32
    )
    weights = rows.sample_weight.astype(np.float32)

    generator = np.random.default_rng(seed)
    hidden_weights = (
        generator.standard_normal((hidden_size, inputs.shape[1]))
        * np.sqrt(2.0 / inputs.shape[1])
    ).astype(np.float32)
    hidden_bias = np.zeros(hidden_size, dtype=np.float32)
    output_weights = (
        generator.standard_normal(hidden_size) * np.sqrt(1.0 / hidden_size)
    ).astype(np.float32)
    output_bias = np.zeros(1, dtype=np.float32)
    parameters = [hidden_weights, hidden_bias, output_weights, output_bias]
    first_moments = [np.zeros_like(parameter) for parameter in parameters]
    second_moments = [np.zeros_like(parameter) for parameter in parameters]
    beta1 = 0.9
    beta2 = 0.999
    epsilon = 1e-8
    step = 0

    train_indices = np.flatnonzero(train_mask)
    validation_indices = np.flatnonzero(validation_mask)

    def logits_for(indices: np.ndarray) -> np.ndarray:
        hidden = np.maximum(
            inputs[indices] @ hidden_weights.T + hidden_bias, 0.0
        )
        return hidden @ output_weights + output_bias[0]

    def cross_entropy(indices: np.ndarray) -> float:
        logits = logits_for(indices).astype(np.float64)
        target = targets[indices].astype(np.float64)
        weight = weights[indices].astype(np.float64)
        losses = np.logaddexp(0.0, logits) - target * logits
        return float(np.sum(losses * weight) / np.sum(weight))

    best_validation_loss = float("inf")
    best_parameters: list[np.ndarray] | None = None
    epochs_without_improvement = 0
    epochs_completed = 0
    for epoch in range(1, epochs + 1):
        generator.shuffle(train_indices)
        for start in range(0, train_indices.size, batch_size):
            indices = train_indices[start : start + batch_size]
            batch_inputs = inputs[indices]
            batch_targets = targets[indices]
            batch_weights = weights[indices]
            pre_activation = batch_inputs @ hidden_weights.T + hidden_bias
            hidden = np.maximum(pre_activation, 0.0)
            logits = hidden @ output_weights + output_bias[0]
            probabilities = np.empty_like(logits)
            positive = logits >= 0
            probabilities[positive] = 1.0 / (1.0 + np.exp(-logits[positive]))
            negative_exp = np.exp(logits[~positive])
            probabilities[~positive] = negative_exp / (1.0 + negative_exp)

            logit_gradient = (
                (probabilities - batch_targets)
                * batch_weights
                / np.sum(batch_weights)
            )
            output_weight_gradient = hidden.T @ logit_gradient
            output_weight_gradient += weight_decay * output_weights
            output_bias_gradient = np.asarray(
                [np.sum(logit_gradient)], dtype=np.float32
            )
            hidden_gradient = logit_gradient[:, None] * output_weights[None, :]
            hidden_gradient *= pre_activation > 0.0
            hidden_weight_gradient = hidden_gradient.T @ batch_inputs
            hidden_weight_gradient += weight_decay * hidden_weights
            hidden_bias_gradient = hidden_gradient.sum(axis=0)
            gradients = [
                hidden_weight_gradient,
                hidden_bias_gradient,
                output_weight_gradient,
                output_bias_gradient,
            ]

            step += 1
            correction1 = 1.0 - beta1**step
            correction2 = 1.0 - beta2**step
            for parameter, gradient, first, second in zip(
                parameters, gradients, first_moments, second_moments
            ):
                first *= beta1
                first += (1.0 - beta1) * gradient
                second *= beta2
                second += (1.0 - beta2) * gradient * gradient
                parameter -= learning_rate * (first / correction1) / (
                    np.sqrt(second / correction2) + epsilon
                )

        epochs_completed = epoch
        validation_loss = cross_entropy(validation_indices)
        if progress and (epoch == 1 or epoch % 5 == 0):
            print(
                f"epoch {epoch:03d}: validation BCE={validation_loss:.6f}",
                flush=True,
            )
        if validation_loss < best_validation_loss - 1e-6:
            best_validation_loss = validation_loss
            best_parameters = [parameter.copy() for parameter in parameters]
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= patience:
                break

    if best_parameters is None:
        raise RuntimeError("ReLU value fit did not produce a checkpoint")
    hidden_weights[:], hidden_bias[:], output_weights[:], output_bias[:] = best_parameters
    model = {
        "input_mean": input_mean.astype(np.float64),
        "input_scale": input_scale.astype(np.float64),
        "hidden_weights": hidden_weights.astype(np.float64),
        "hidden_bias": hidden_bias.astype(np.float64),
        "output_weights": output_weights.astype(np.float64),
        "output_bias": np.asarray(output_bias[0], dtype=np.float64),
    }
    metrics: dict[str, object] = {
        "optimizer": {
            "type": "Adam",
            "epochs": epochs_completed,
            "best_validation_bce": best_validation_loss,
            "hidden_size": hidden_size,
            "batch_size": batch_size,
            "learning_rate": learning_rate,
            "weight_decay": weight_decay,
            "seed": seed,
        }
    }
    for split_name, split_mask in masks.items():
        prediction = predict_relu_value(rows.features[split_mask], model)
        metrics[split_name] = regression_metrics(
            rows.target[split_mask], prediction, rows.sample_weight[split_mask]
        )
        metrics[f"raw_nn_{split_name}"] = regression_metrics(
            rows.target[split_mask],
            np.clip(rows.raw_nn_value[split_mask], -1.0, 1.0),
            rows.sample_weight[split_mask],
        )
    return model, metrics


def model_document(
    coefficients: np.ndarray,
    metrics: dict[str, object],
    rows: FitRows,
) -> dict[str, object]:
    coefficient_names = ("bias",) + tuple(
        name for name in FEATURE_NAMES if name != "w"
    )
    coefficients = np.asarray(coefficients, dtype=np.float64).reshape(
        len(coefficient_names), PHASE_DEGREE + 1
    )
    return {
        "schema_version": 1,
        "teacher_model": "candidate_gen217",
        "teacher_target": "complete-turn immediate MCTS win-loss, globalTargetsNC[16]-[17]",
        "teacher_visits": {
            "min": float(np.min(rows.visits)),
            "median": float(np.median(rows.visits)),
            "max": float(np.max(rows.visits)),
        },
        "rows": int(rows.features.shape[0]),
        "feature_order": list(FEATURE_NAMES),
        "phase_scale": PHASE_SCALE,
        "territory_scale": TERRITORY_SCALE,
        "mobility_scale": MOBILITY_SCALE,
        "phase_degree": PHASE_DEGREE,
        "formula": "value=tanh(0.5*sum(poly(feature,w)*normalized_feature))",
        "coefficients": {
            name: coefficients[index].tolist()
            for index, name in enumerate(coefficient_names)
        },
        "metrics": metrics,
    }


def formula_model_document(
    model: dict[str, object],
    metrics: dict[str, object],
    rows: FitRows,
) -> dict[str, object]:
    phase_name = str(model["phase_name"])
    coefficient_feature_names = tuple(model["coefficient_feature_names"])
    return {
        "schema_version": 1,
        "model_type": "phase_formula",
        "teacher_model": "candidate_gen217",
        "teacher_target": "complete-turn immediate MCTS win-loss, globalTargetsNC[16]-[17]",
        "teacher_visits": {
            "min": float(np.min(rows.visits)),
            "median": float(np.median(rows.visits)),
            "max": float(np.max(rows.visits)),
        },
        "rows": int(rows.features.shape[0]),
        "feature_order": list(FEATURE_NAMES),
        "feature_divisors": FEATURE_DIVISORS.tolist(),
        "phase_name": phase_name,
        "phase_index": FEATURE_NAMES.index(phase_name),
        "phase_divisor": float(
            FEATURE_DIVISORS[FEATURE_NAMES.index(phase_name)]
        ),
        "phase_degree": int(model["phase_degree"]),
        "coefficient_feature_names": list(coefficient_feature_names),
        "coefficient_feature_indices": [
            FEATURE_NAMES.index(name) for name in coefficient_feature_names
        ],
        "coefficient_feature_divisors": [
            float(FEATURE_DIVISORS[FEATURE_NAMES.index(name)])
            for name in coefficient_feature_names
        ],
        "formula": "value=tanh(0.5*(poly(bias,phase)+sum(poly(k_i,phase)*normalized_feature_i)))",
        "coefficients": np.asarray(model["coefficients"]).tolist(),
        "metrics": metrics,
    }


def relu_model_document(
    model: dict[str, np.ndarray],
    metrics: dict[str, object],
    rows: FitRows,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "model_type": "relu_mlp",
        "teacher_model": "candidate_gen217",
        "teacher_target": "complete-turn immediate MCTS win-loss, globalTargetsNC[16]-[17]",
        "teacher_visits": {
            "min": float(np.min(rows.visits)),
            "median": float(np.median(rows.visits)),
            "max": float(np.max(rows.visits)),
        },
        "rows": int(rows.features.shape[0]),
        "feature_order": list(FEATURE_NAMES),
        "input_scales_before_standardization": FEATURE_DIVISORS.tolist(),
        "formula": "value=tanh(0.5*(W2*relu(W1*standardize(features)+b1)+b2))",
        "deployment": {
            "legacy_value_blend": 0.75,
            "rich_value_blend": 0.25,
            "reason": "head-to-head selected residual blend",
        },
        "input_mean": model["input_mean"].tolist(),
        "input_scale": model["input_scale"].tolist(),
        "hidden_weights": model["hidden_weights"].tolist(),
        "hidden_bias": model["hidden_bias"].tolist(),
        "output_weights": model["output_weights"].tolist(),
        "output_bias": float(model["output_bias"]),
        "metrics": metrics,
    }


def write_model_json(path: str | Path, document: dict[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
