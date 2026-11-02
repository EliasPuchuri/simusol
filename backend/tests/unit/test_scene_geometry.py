import numpy as np
import pytest

from solids.geometry.scene import common_origin, to_scene_coordinates

E0, N0, Z0 = 367_800.0, 8_827_600.0, 3_300.0


def cube(center, size=10.0):
    c = np.array(center, dtype=float)
    return c + size / 2 * np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], dtype=float)


def test_origin_is_the_center_of_the_joint_bounds():
    a, b = cube((E0, N0, Z0)), cube((E0 + 100, N0 - 40, Z0 + 20))
    origin = common_origin([(a.min(0), a.max(0)), (b.min(0), b.max(0))])
    assert origin == pytest.approx((E0 + 50, N0 - 20, Z0 + 10))


def test_axis_contract_is_y_up_with_north_pointing_to_minus_z():
    origin = (E0, N0, Z0)
    scene = to_scene_coordinates(np.array([[E0 + 5, N0 + 7, Z0 + 3]]), origin)
    assert scene.dtype == np.float32
    assert scene[0].tolist() == pytest.approx([5, 3, -7])


def test_both_periods_share_one_translation_so_a_shift_stays_visible():
    prev, curr = cube((E0, N0, Z0)), cube((E0 + 0.5, N0 + 0.25, Z0))  # a real half-metre shift in UTM
    origin = common_origin([(m.min(0), m.max(0)) for m in (prev, curr)])
    sp, sc = to_scene_coordinates(prev, origin), to_scene_coordinates(curr, origin)
    assert (sc - sp).mean(0) == pytest.approx([0.5, 0.0, -0.25], abs=1e-4)


def test_centering_each_mesh_alone_would_hide_the_shift():
    prev, curr = cube((E0, N0, Z0)), cube((E0 + 0.5, N0, Z0))
    each = [to_scene_coordinates(m, tuple(m.mean(0))) for m in (prev, curr)]
    assert (each[1] - each[0]).mean(0) == pytest.approx([0, 0, 0], abs=1e-6)  # the bug the contract avoids


def test_utm_magnitudes_do_not_lose_precision_after_the_common_origin():
    m = cube((E0, N0, Z0), size=1.0)
    scene = to_scene_coordinates(m, (E0, N0, Z0))
    assert np.ptp(scene[:, 0]) == pytest.approx(1.0, abs=1e-6)


def test_empty_bounds_are_rejected():
    with pytest.raises(ValueError):
        common_origin([])
