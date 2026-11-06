import json

import pytest

from solids.geometry.overlaps import OVERLAP_VERSION, compute_bounds, compute_overlap
from support.meshes import cube, obj_bytes

UTM = (367_800.0, 8_827_600.0, 3_300.0)
at = lambda dx=0.0, dy=0.0, dz=0.0: (UTM[0] + dx, UTM[1] + dy, UTM[2] + dz)


def write(tmp_path, name, mesh):
    path = tmp_path / name
    path.write_bytes(obj_bytes(mesh))
    return path


def overlap(tmp_path, a, b):
    return compute_overlap(write(tmp_path, "a.obj", a), write(tmp_path, "b.obj", b))


def test_bounds_are_the_original_utm_extremes(tmp_path):
    r = compute_bounds(write(tmp_path, "a.obj", cube(UTM, 10)))
    assert r["status"] == "ok" and r["version"] == OVERLAP_VERSION
    assert r["min"] == pytest.approx([UTM[0] - 5, UTM[1] - 5, UTM[2] - 5], abs=1e-3)
    assert r["max"] == pytest.approx([UTM[0] + 5, UTM[1] + 5, UTM[2] + 5], abs=1e-3)


def test_unreadable_file_fails_with_a_reason_and_no_numbers(tmp_path):
    bad = tmp_path / "x.obj"
    bad.write_text("not an obj")
    r = compute_bounds(bad)
    assert r["status"] == "failed" and r["error"] and r["min"] is None


def test_half_overlapping_cubes_share_a_known_volume(tmp_path):
    r = overlap(tmp_path, cube(at(), 10), cube(at(dx=5), 10))
    assert r["status"] == "ok" and r["relation"] == "overlap"
    assert r["common_m3"] == pytest.approx(500.0, rel=1e-6)
    assert r["volumes"] == {"a_m3": pytest.approx(1000.0), "b_m3": pytest.approx(1000.0)}
    assert r["common_pct_of_smaller"] == pytest.approx(50.0, rel=1e-6)


def test_a_solid_inside_another_shares_all_of_its_volume(tmp_path):
    r = overlap(tmp_path, cube(at(), 20), cube(at(), 4))
    assert r["relation"] == "overlap" and r["common_m3"] == pytest.approx(64.0, rel=1e-6)
    assert r["common_pct_of_smaller"] == pytest.approx(100.0, rel=1e-6)


def test_separated_solids_do_not_overlap_and_zero_is_a_computed_result(tmp_path):
    r = overlap(tmp_path, cube(at(), 10), cube(at(dx=50), 10))
    assert r["relation"] == "disjoint" and r["common_m3"] == 0.0


def test_faces_that_only_touch_are_contact_not_overlap(tmp_path):
    r = overlap(tmp_path, cube(at(), 10), cube(at(dx=10), 10))
    assert r["relation"] == "contact" and r["common_m3"] == pytest.approx(0.0, abs=1e-6)


def test_a_sliver_below_a_litre_is_numerical_noise_so_it_counts_as_contact(tmp_path):
    r = overlap(tmp_path, cube(at(), 1), cube(at(dx=1 - 1e-4), 1))      # 1 m cubes overlapping by 0.1 mm: 1e-4 m3
    assert r["relation"] == "contact" and 0 < r["common_m3"] < 1e-3


def test_a_thin_but_real_overlap_above_a_litre_is_reported(tmp_path):
    r = overlap(tmp_path, cube(at(), 1), cube(at(dx=1 - 1e-2), 1))      # 1 cm deep: 1e-2 m3
    assert r["relation"] == "overlap" and r["common_m3"] == pytest.approx(1e-2, rel=1e-3)


def test_inverted_orientation_is_normalised_on_a_copy_and_flagged(tmp_path):
    r = overlap(tmp_path, cube(at(), 10, invert=True), cube(at(dx=5), 10))
    assert r["relation"] == "overlap" and r["common_m3"] == pytest.approx(500.0, rel=1e-6)
    assert "inverted_orientation_normalized:a" in r["warnings"]


def test_an_open_surface_cannot_be_evaluated_and_has_no_volume(tmp_path):
    broken = cube(at(), 10)
    broken.faces = broken.faces[:-1]
    r = overlap(tmp_path, broken, cube(at(dx=5), 10))
    assert r["status"] == "ok" and r["relation"] == "not_evaluable"
    assert r["common_m3"] is None and r["common_pct_of_smaller"] is None and r["reason"] == "not_watertight:a"


def test_the_result_is_strict_json(tmp_path):
    json.dumps(overlap(tmp_path, cube(at(), 10), cube(at(dx=5), 10)), allow_nan=False)
