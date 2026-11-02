import hashlib
from pathlib import Path

import numpy as np
import pytest

from solids.domain.metrics import Validity
from solids.geometry.qc import QC_VERSION, analyze_mesh



def box(origin=(0.0, 0.0, 0.0), size=10.0):
    """Closed, consistently oriented box with positive signed volume (from trimesh)."""
    import trimesh

    mesh = trimesh.creation.box(extents=(size, size, size))
    vertices = (mesh.vertices + np.asarray(origin) + size / 2).tolist()
    return [tuple(v) for v in vertices], [tuple(f) for f in mesh.faces.tolist()]


def write_obj(path: Path, vertices, faces) -> Path:
    lines = [f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in vertices] + [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in faces]
    path.write_text("\n".join(lines) + "\n")
    return path


def inverted(faces):
    return [(a, c, b) for a, b, c in faces]


def merged(*boxes):
    verts, faces = [], []
    for v, f in boxes:
        faces += [(a + len(verts), b + len(verts), c + len(verts)) for a, b, c in f]
        verts += v
    return verts, faces


def test_clean_closed_outward_box_has_no_problems_and_valid_volume(tmp_path):
    r = analyze_mesh(write_obj(tmp_path / "a.obj", *box()))
    assert r["status"] == "ok" and r["problems"] == []
    assert r["watertight"] is True and r["open_edges"] == 0 and r["non_manifold_edges"] == 0
    assert r["components"].value == 1 and r["components"].validity is Validity.VALID
    assert r["volume_m3"].value == pytest.approx(1000.0) and r["orientation"] == "outward"
    assert r["fitness"] == {"pca": True, "volume": True, "boolean": True, "visualization": True}
    assert r["self_intersections"].value == 0


def test_inverted_orientation_never_becomes_a_valid_volume(tmp_path):
    v, f = box()
    r = analyze_mesh(write_obj(tmp_path / "a.obj", v, inverted(f)))
    assert r["orientation"] == "inverted" and r["signed_volume_m3"] == pytest.approx(-1000.0)
    assert r["volume_m3"].validity is Validity.UNAVAILABLE and r["volume_m3"].value is None
    assert "inverted_orientation" in r["problems"]
    assert r["fitness"]["volume"] is False and r["fitness"]["boolean"] is False
    assert r["fitness"]["pca"] is True and r["fitness"]["visualization"] is True


def test_open_surface_reports_open_edges_and_no_volume(tmp_path):
    v, f = box()
    r = analyze_mesh(write_obj(tmp_path / "a.obj", v, f[:-2]))
    assert r["watertight"] is False and r["open_edges"] > 0
    assert {"not_watertight", "open_edges"} <= set(r["problems"])
    assert r["volume_m3"].value is None and r["fitness"]["volume"] is False


def test_two_separate_components_are_counted(tmp_path):
    r = analyze_mesh(write_obj(tmp_path / "a.obj", *merged(box(), box((100.0, 0.0, 0.0)))))
    assert r["components"].value == 2 and "multiple_components" in r["problems"]


def test_duplicate_and_degenerate_faces_are_detected(tmp_path):
    v, f = box()
    r = analyze_mesh(write_obj(tmp_path / "a.obj", v, f + [f[0], (0, 0, 1)]))
    assert r["duplicate_faces"] >= 1 and r["degenerate_faces"] >= 1
    assert {"duplicate_faces", "degenerate_faces"} <= set(r["problems"])


def test_duplicate_vertices_are_detected_without_merging_them(tmp_path):
    v, f = box()
    first = next(i for i, face in enumerate(f) if 0 in face)
    f[first] = tuple(8 if idx == 0 else idx for idx in f[first])  # a face now uses a copy of vertex 0
    r = analyze_mesh(write_obj(tmp_path / "a.obj", v + [v[0]], f))
    assert r["duplicate_vertices"] == 1 and "duplicate_vertices" in r["problems"]
    assert r["vertices"] == 9  # the original vertex count is preserved: nothing was merged


def test_non_manifold_edge_is_detected(tmp_path):
    v, f = box()
    a, b, _ = f[0]
    r = analyze_mesh(write_obj(tmp_path / "a.obj", v + [(5.0, 5.0, -10.0)], f + [(a, b, 8), (b, a, 8)]))
    assert r["non_manifold_edges"] >= 1 and "non_manifold_edges" in r["problems"]


def test_overlapping_shells_in_one_mesh_report_self_intersections(tmp_path):
    r = analyze_mesh(write_obj(tmp_path / "a.obj", *merged(box(), box((5.0, 5.0, 5.0)))))
    assert r["self_intersections"].validity is Validity.VALID and r["self_intersections"].value > 0
    assert "self_intersections" in r["problems"]
    assert r["fitness"]["boolean"] is False


def test_unreadable_files_fail_individually_with_a_reason(tmp_path):
    (tmp_path / "a.obj").write_text("hello\n")
    r = analyze_mesh(tmp_path / "a.obj")
    assert r["status"] == "failed" and r["error"]
    assert r["fitness"] == {"pca": False, "volume": False, "boolean": False, "visualization": False}


def test_the_original_file_is_never_modified(tmp_path):
    v, f = box()
    path = write_obj(tmp_path / "a.obj", v, inverted(f))
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    analyze_mesh(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_result_is_strict_json_serialisable(tmp_path):
    import json
    from solids.geometry.qc import to_jsonable
    r = analyze_mesh(write_obj(tmp_path / "a.obj", *box()))
    json.dumps(to_jsonable(r), allow_nan=False)
    assert QC_VERSION
