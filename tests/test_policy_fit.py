import numpy as np

from src.ai.policy_fit import _legal_mask


def _empty_planes():
    return np.zeros((6, 100), dtype=np.uint8)


def test_stage_zero_only_selects_mobile_current_queens():
    planes = _empty_planes()
    planes[1, [0, 99]] = 1
    planes[3, [1, 10, 88, 89, 98]] = 1
    legal = _legal_mask(planes, 0)
    assert legal[0]
    assert not legal[99]
    assert legal.sum() == 1


def test_stage_one_destination_mask_follows_clear_queen_rays():
    planes = _empty_planes()
    planes[1, 44] = 1
    planes[2, 47] = 1
    planes[4, 44] = 1
    legal = _legal_mask(planes, 1)
    assert legal[45] and legal[46]
    assert not legal[47] and not legal[48]
    assert legal[4] and legal[84]


def test_stage_two_arrow_can_return_to_vacated_square():
    planes = _empty_planes()
    planes[1, 55] = 1
    planes[5, 55] = 1
    legal = _legal_mask(planes, 2)
    assert legal[44]
    assert legal[0]
    assert not legal[55]
