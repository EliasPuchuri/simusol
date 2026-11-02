import hashlib

import pytest

from solids.geometry.pair_metrics import PAIR_VERSION, compute_pair_metrics
from support.meshes import bent_slab, cube, obj_bytes, slab

UTM = (367_800.0, 8_827_600.0, 3_300.0)


def write(tmp_path, name, mesh):
    path = tmp_path / name
    path.write_bytes(obj_bytes(mesh))
    return path


def pair(tmp_path, a, b):
    return compute_pair_metrics(write(tmp_path, "a.obj", a), write(tmp_path, "b.obj", b))


def test_identical_solids_in_utm_coordinates_give_a_perfect_match(tmp_path):
    r = pair(tmp_path, cube(UTM), cube(UTM))
    m = r["metrics"]
    assert r["status"] == "ok" and r["pair_version"] == PAIR_VERSION and r["provisional"] is True
    assert m["iou_pct"] == pytest.approx(100.0, abs=1e-6) and m["delta_volume_pct"] == pytest.approx(0.0, abs=1e-9)
    assert m["p95_m"] == pytest.approx(0.0, abs=1e-6) and m["centroid_m"] == pytest.approx(0.0, abs=1e-6)
    assert r["volumes"]["previous_m3"] == pytest.approx(1000.0) and r["volumes"]["intersection_m3"] == pytest.approx(1000.0)


def test_half_overlapping_cubes_have_known_volumetric_metrics(tmp_path):
    r = pair(tmp_path, cube(UTM), cube((UTM[0] + 5, UTM[1], UTM[2])))
    m = r["metrics"]
    assert r["volumes"]["intersection_m3"] == pytest.approx(500.0, rel=1e-6)
    assert m["iou_pct"] == pytest.approx(100 * 500 / 1500, rel=1e-6)
    assert m["added_pct"] == pytest.approx(50.0) and m["removed_pct"] == pytest.approx(50.0)
    assert m["delta_volume_pct"] == pytest.approx(0.0, abs=1e-9) and m["no_coincidence_pct"] == pytest.approx(50.0)
    assert m["centroid_m"] == pytest.approx(5.0, abs=1e-6) and m["p95_m"] > 0.5


def test_growth_uses_the_documented_bases(tmp_path):
    r = pair(tmp_path, cube(UTM, 10), cube(UTM, 12))  # concentric, the second contains the first
    m, v = r["metrics"], r["volumes"]
    assert v["intersection_m3"] == pytest.approx(1000.0, rel=1e-6)
    assert m["delta_volume_pct"] == pytest.approx(100 * (1728 - 1000) / 1000)          # signed, base = previous
    assert m["delta_volume_sym_pct"] == pytest.approx(100 * 728 / 1728)                  # symmetric, base = max
    assert m["added_pct"] == pytest.approx(100 * 728 / 1728) and m["removed_pct"] == pytest.approx(0.0, abs=1e-9)
    assert v["added_m3"] == pytest.approx(728.0) and v["removed_m3"] == pytest.approx(0.0, abs=1e-6)


def test_inverted_orientation_is_normalised_on_a_copy_and_flagged(tmp_path):
    a, b = cube(UTM, invert=True), cube(UTM, invert=True)
    pa, pb = write(tmp_path, "a.obj", a), write(tmp_path, "b.obj", b)
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (pa, pb)]
    r = compute_pair_metrics(pa, pb)
    assert r["metrics"]["iou_pct"] == pytest.approx(100.0, abs=1e-6) and r["volumes"]["previous_m3"] == pytest.approx(1000.0)
    assert r["provisional"] is True and {"inverted_orientation_normalized:previous", "inverted_orientation_normalized:current"} <= set(r["warnings"])
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in (pa, pb)] == before  # originals untouched


def test_an_open_surface_gets_no_volumetric_metrics_but_keeps_the_geometric_ones(tmp_path):
    open_mesh = cube(UTM)
    open_mesh.faces = open_mesh.faces[:-2]
    r = pair(tmp_path, open_mesh, cube(UTM))
    assert r["status"] == "ok" and r["metrics"]["iou_pct"] is None and r["volumes"]["previous_m3"] is None
    assert r["reasons"]["iou_pct"] == "not_watertight:previous"
    assert r["metrics"]["centroid_m"] is not None and r["metrics"]["p95_m"] is not None  # never replaced by zero


def test_components_are_counted_per_period(tmp_path):
    import trimesh
    two = trimesh.util.concatenate([cube(UTM), cube((UTM[0] + 100, UTM[1], UTM[2]))])
    r = pair(tmp_path, cube(UTM), two)
    assert r["components"] == {"previous": 1, "current": 2}


def test_characterization_of_both_periods_is_embedded_for_part_2(tmp_path):
    r = pair(tmp_path, slab(120, 30), slab(120, 30))
    assert r["characterization"]["previous"]["body_type"] == "TABULAR" and r["characterization"]["current"]["status"] == "ok"


def test_local_curvature_change_is_measured_on_spatially_matching_segments(tmp_path):
    same = pair(tmp_path, bent_slab(), bent_slab())
    changed = pair(tmp_path, slab(90, 20, extents=(115, 60, 3)), bent_slab(40))
    assert same["metrics"]["local_change_deg"] == pytest.approx(0.0, abs=1.0)
    assert changed["metrics"]["local_change_deg"] > 10.0 and changed["metrics"]["local_segments_compared"] >= 4


def test_result_is_reproducible_and_strict_json(tmp_path):
    import json
    a, b = cube(UTM), cube((UTM[0] + 2, UTM[1], UTM[2]))
    first, second = pair(tmp_path, a, b), pair(tmp_path, a, b)
    assert first == second
    json.dumps(first, allow_nan=False)


def test_unreadable_files_fail_the_pair_with_a_reason(tmp_path):
    (tmp_path / "a.obj").write_text("hello\n")
    r = compute_pair_metrics(tmp_path / "a.obj", write(tmp_path, "b.obj", cube(UTM)))
    assert r["status"] == "failed" and r["error"] and r["metrics"] is None
