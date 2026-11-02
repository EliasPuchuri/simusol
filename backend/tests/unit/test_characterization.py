import math

import numpy as np
import pytest
import trimesh

from solids.geometry.characterization import (
    PROFILE,
    Params,
    axis_to_trend_plunge,
    characterize_mesh,
    plane_normal_to_azimuth_dip,
)


def write_mesh(path, mesh) -> str:
    lines = [f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in mesh.vertices] + [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in mesh.faces]
    path.write_text("\n".join(lines) + "\n")
    return path


def rotation_to(normal):
    """Rotation matrix that sends +Z to `normal`."""
    return trimesh.geometry.align_vectors([0, 0, 1], normal)[:3, :3]


def dip_normal(azimuth, dip):
    """Upward normal of a plane dipping `dip` degrees toward `azimuth` (dip direction)."""
    a, d = math.radians(azimuth), math.radians(dip)
    return np.array([-math.sin(d) * math.sin(a), -math.sin(d) * math.cos(a), math.cos(d)])


def slab(azimuth=120.0, dip=30.0, extents=(120.0, 60.0, 3.0), center=(0, 0, 0)):
    """Thin plate whose plane has the given dip direction and dip."""
    mesh = trimesh.creation.box(extents=extents)
    n = dip_normal(azimuth, dip)
    # long side of the slab goes along the strike so the PCA axes are well defined
    strike = np.cross([0, 0, 1], n)
    strike = strike / np.linalg.norm(strike)
    updip = np.cross(n, strike)
    basis = np.column_stack((strike, updip, n))
    mesh.vertices = mesh.vertices @ basis.T + np.asarray(center)
    return mesh


def angle_diff(a, b, period=360.0):
    d = abs(a - b) % period
    return min(d, period - d)


# --- angle conversions ----------------------------------------------------------------------

@pytest.mark.parametrize("az,dip", [(120, 30), (0, 45), (270, 80), (359, 10), (45, 89)])
def test_plane_normal_gives_back_azimuth_and_dip(az, dip):
    got = plane_normal_to_azimuth_dip(dip_normal(az, dip))
    assert got["dip"] == pytest.approx(dip, abs=1e-6)
    assert angle_diff(got["azimuth"], az) == pytest.approx(0, abs=1e-6)
    assert 0 <= got["azimuth"] < 360


def test_flipping_the_normal_does_not_change_the_plane():
    n = dip_normal(200, 35)
    assert plane_normal_to_azimuth_dip(-n) == plane_normal_to_azimuth_dip(n)


def test_horizontal_plane_has_no_azimuth_and_vertical_plane_is_flagged():
    flat = plane_normal_to_azimuth_dip([0, 0, 1])
    assert flat["dip"] == pytest.approx(0) and flat["azimuth"] is None and flat["note"] == "horizontal_plane"
    vertical = plane_normal_to_azimuth_dip([1, 0, 0])
    assert vertical["dip"] == pytest.approx(90) and vertical["note"] == "vertical_plane_direction_ambiguous"


@pytest.mark.parametrize("trend,plunge", [(120, 25), (30, 70), (300, 5), (200, 0)])
def test_axis_gives_trend_and_plunge_up_to_the_180_degree_equivalence(trend, plunge):
    t, p = math.radians(trend), math.radians(plunge)
    v = np.array([math.cos(p) * math.sin(t), math.cos(p) * math.cos(t), math.sin(p)])
    for vector in (v, -v):  # the sign of a PCA axis is arbitrary
        got = axis_to_trend_plunge(vector)
        assert got["plunge"] == pytest.approx(plunge, abs=1e-6)
        assert angle_diff(got["trend"], trend, 180.0) == pytest.approx(0, abs=1e-6)


# --- whole-mesh characterization ------------------------------------------------------------

def test_flat_slab_is_tabular_with_the_known_azimuth_and_dip(tmp_path):
    r = characterize_mesh(write_mesh(tmp_path / "a.obj", slab(120, 30)))
    assert r["status"] == "ok" and r["profile"] == PROFILE
    assert r["body_type"] == "TABULAR"
    assert r["orientation"]["type"] == "planar"
    assert angle_diff(r["orientation"]["azimuth"], 120) < 2.0 and r["orientation"]["dip"] == pytest.approx(30, abs=2.0)
    l1, l2, l3 = r["eigenvalues"]
    assert l1 >= l2 >= l3 > 0


def test_cigar_is_globular_with_axial_trend_and_plunge(tmp_path):
    cigar = trimesh.creation.box(extents=(90, 40, 40))
    t, p = math.radians(60), math.radians(20)
    axis = np.array([math.cos(p) * math.sin(t), math.cos(p) * math.cos(t), math.sin(p)])
    cigar.vertices = cigar.vertices @ trimesh.geometry.align_vectors([1, 0, 0], axis)[:3, :3].T
    r = characterize_mesh(write_mesh(tmp_path / "a.obj", cigar))
    assert r["body_type"] == "GLOBULAR" and r["orientation"]["type"] == "axial"
    assert angle_diff(r["orientation"]["azimuth"], 60, 180.0) < 3.0 and r["orientation"]["dip"] == pytest.approx(20, abs=3.0)


def test_sphere_has_no_interpretable_orientation(tmp_path):
    r = characterize_mesh(write_mesh(tmp_path / "a.obj", trimesh.creation.icosphere(subdivisions=3, radius=40)))
    assert r["body_type"] == "GLOBULAR"
    assert r["orientation"]["type"] == "no_interpretable" and r["orientation"]["azimuth"] is None
    assert r["orientation"]["reason"] == "similar_eigenvalues"


def test_bent_slab_is_classified_as_curved_tabular_and_a_flat_one_is_not(tmp_path):
    left, right = slab(90, 20, extents=(60, 60, 3)), slab(90, 20, extents=(60, 60, 3))
    right.apply_transform(trimesh.transformations.rotation_matrix(math.radians(40), [0, 1, 0]))
    right.apply_translation([55, 0, 0])
    bent = trimesh.util.concatenate([left, right])
    r_bent = characterize_mesh(write_mesh(tmp_path / "bent.obj", bent))
    r_flat = characterize_mesh(write_mesh(tmp_path / "flat.obj", slab(90, 20, extents=(120, 60, 3))))
    assert r_flat["body_type"] == "TABULAR"
    assert r_bent["body_type"] == "TABULAR CURVO" and r_bent["evidence"]["local_change_p95_deg"] >= 12.0
    assert "segments" not in r_bent and "segments" not in r_bent["evidence"]  # local orientations are never exposed


def test_result_is_reproducible_and_invariant_to_translation_and_face_order(tmp_path):
    base = slab(210, 55)
    a = characterize_mesh(write_mesh(tmp_path / "a.obj", base))
    again = characterize_mesh(write_mesh(tmp_path / "a2.obj", base))
    assert a["eigenvalues"] == again["eigenvalues"] and a["orientation"] == again["orientation"]

    moved = base.copy()
    moved.apply_translation([367_800.0, 8_827_600.0, 3_300.0])  # UTM magnitudes
    m = characterize_mesh(write_mesh(tmp_path / "m.obj", moved))
    assert m["body_type"] == a["body_type"]
    assert angle_diff(m["orientation"]["azimuth"], a["orientation"]["azimuth"]) < 0.5
    assert m["orientation"]["dip"] == pytest.approx(a["orientation"]["dip"], abs=0.5)

    flipped = base.copy()
    flipped.faces = flipped.faces[:, ::-1]  # inverted global orientation, as in the pilot meshes
    f = characterize_mesh(write_mesh(tmp_path / "f.obj", flipped))
    assert f["body_type"] == a["body_type"] and angle_diff(f["orientation"]["azimuth"], a["orientation"]["azimuth"]) < 0.5


def test_eigenvalues_are_not_presented_as_physical_lengths(tmp_path):
    r = characterize_mesh(write_mesh(tmp_path / "a.obj", slab()))
    assert set(r["dispersion"]) == {"a", "b", "c"}  # standard deviations along the axes, not length/width/thickness
    assert r["dispersion"]["a"] == pytest.approx(math.sqrt(r["eigenvalues"][0]))


def test_unreadable_file_fails_individually(tmp_path):
    (tmp_path / "a.obj").write_text("hello\n")
    r = characterize_mesh(tmp_path / "a.obj")
    assert r["status"] == "failed" and r["error"] and r["body_type"] is None


def test_custom_params_are_recorded_so_results_stay_explainable(tmp_path):
    r = characterize_mesh(write_mesh(tmp_path / "a.obj", slab()), Params(n_points=5000, seed=7))
    assert r["params"]["n_points"] == 5000 and r["params"]["seed"] == 7 and r["params"]["local_curvature_min_deg"] == 12.0
