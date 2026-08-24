import numpy as np

from src.ai.value_fit import FEATURE_NAMES, evaluate_feature_batch


def _initial_planes():
    current = np.zeros((1, 10, 10), dtype=bool)
    opponent = np.zeros_like(current)
    obstacles = np.zeros_like(current)
    current[0, 0, 3] = True
    current[0, 0, 6] = True
    current[0, 3, 0] = True
    current[0, 3, 9] = True
    opponent[0, 6, 0] = True
    opponent[0, 6, 9] = True
    opponent[0, 9, 3] = True
    opponent[0, 9, 6] = True
    return current, opponent, obstacles


def test_initial_position_is_symmetric():
    current, opponent, obstacles = _initial_planes()
    features = evaluate_feature_batch(current, opponent, obstacles)[0]
    by_name = dict(zip(FEATURE_NAMES, features))
    for name in FEATURE_NAMES:
        if name not in {
            "w",
            "empty_count",
            "contested_count",
            "active_area_count",
        }:
            np.testing.assert_allclose(by_name[name], 0.0, atol=1e-12)
    assert 0.0 <= by_name["w"] <= 92.0
    assert by_name["empty_count"] == 92.0
    assert by_name["active_area_count"] == 1.0


def test_swapping_sides_negates_signed_features():
    current, opponent, obstacles = _initial_planes()
    obstacles[0, 4, 4] = True
    obstacles[0, 5, 4] = True
    forward = evaluate_feature_batch(current, opponent, obstacles)[0]
    reverse = evaluate_feature_batch(opponent, current, obstacles)[0]
    invariant = {"w", "empty_count", "contested_count", "active_area_count"}
    for index, name in enumerate(FEATURE_NAMES):
        if name in invariant:
            assert reverse[index] == forward[index]
        else:
            np.testing.assert_allclose(reverse[index], -forward[index], atol=1e-12)


def test_rotation_preserves_features():
    current, opponent, obstacles = _initial_planes()
    obstacles[0, 2, 2] = True
    obstacles[0, 7, 4] = True
    original = evaluate_feature_batch(current, opponent, obstacles)
    rotated = evaluate_feature_batch(
        np.rot90(current, axes=(1, 2)),
        np.rot90(opponent, axes=(1, 2)),
        np.rot90(obstacles, axes=(1, 2)),
    )
    np.testing.assert_allclose(rotated, original, atol=1e-12)


def test_phase_weight_excludes_occupied_squares():
    current, opponent, obstacles = _initial_planes()
    obstacles[0, 1:9, 5] = True
    features = evaluate_feature_batch(current, opponent, obstacles)[0]
    by_name = dict(zip(FEATURE_NAMES, features))
    empty_count = 100 - current.sum() - opponent.sum() - obstacles.sum()
    assert 0.0 <= by_name["w"] <= empty_count
    assert by_name["empty_count"] == empty_count
