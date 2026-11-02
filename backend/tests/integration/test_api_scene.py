import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

from solids.api.app import create_app

E0, N0, Z0 = 367_800.0, 8_827_600.0, 3_300.0
FACES = [(1, 3, 2), (2, 3, 4), (5, 6, 7), (6, 8, 7), (1, 2, 5), (2, 6, 5), (3, 7, 4), (4, 7, 8), (1, 5, 3), (3, 5, 7), (2, 4, 6), (4, 8, 6)]


def cube_obj(center, size=10.0) -> bytes:
    cx, cy, cz = center
    pts = [(cx + sx * size / 2, cy + sy * size / 2, cz + sz * size / 2) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    lines = [f"v {x:.4f} {y:.4f} {z:.4f}" for x, y, z in pts] + [f"f {a} {b} {c}" for a, b, c in FACES]
    return ("\n".join(lines) + "\n").encode()


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path / "data"))


def period(client, label, files, close=True):
    d = client.post("/api/v1/datasets", json={"name": "M", "period_label": label, "period_kind": "annual"}).json()
    for name, content in files.items():
        assert client.post(f"/api/v1/datasets/{d['id']}/files", files={"file": (name, content)}).status_code == 201
    if close:
        client.post(f"/api/v1/datasets/{d['id']}/finalize")
    return d["id"]


def scene(client, prev, curr, key):
    return client.get("/api/v1/scene", params={"previous": prev, "current": curr, "key": key})


def glb_vertices(client, url) -> np.ndarray:
    r = client.get(url)
    assert r.status_code == 200 and r.headers["content-type"].startswith("model/gltf-binary")
    return np.asarray(trimesh.load(trimesh.util.wrap_as_stream(r.content), file_type="glb", force="mesh").vertices)


def test_pair_scene_has_both_layers_with_one_shared_origin(client):
    prev = period(client, "2025", {"a_3pt.obj": cube_obj((E0, N0, Z0))})
    curr = period(client, "2026", {"a_3.obj": cube_obj((E0 + 40, N0 + 10, Z0 + 5))})
    r = scene(client, prev, curr, "a_3")
    assert r.status_code == 200
    body = r.json()
    assert [(l["role"], l["filename"], l["status"]) for l in body["layers"]] == [("previous", "a_3pt.obj", "ok"), ("current", "a_3.obj", "ok")]
    assert body["origin"] == {"east": pytest.approx(E0 + 20), "north": pytest.approx(N0 + 5), "elevation": pytest.approx(Z0 + 2.5)}
    assert all(l["triangles"] == 12 and l["vertices"] == 8 for l in body["layers"])


def test_glb_keeps_the_real_shift_and_small_scene_coordinates(client):
    prev = period(client, "2025", {"a_3pt.obj": cube_obj((E0, N0, Z0))})
    curr = period(client, "2026", {"a_3.obj": cube_obj((E0 + 0.5, N0, Z0))})
    layers = {l["role"]: l for l in scene(client, prev, curr, "a_3").json()["layers"]}
    vp, vc = glb_vertices(client, layers["previous"]["url"]), glb_vertices(client, layers["current"]["url"])
    assert np.abs(vp).max() < 10 and np.abs(vc).max() < 10  # no UTM magnitudes in float32
    assert (vc.mean(0) - vp.mean(0)) == pytest.approx([0.5, 0, 0], abs=1e-3)


def test_axes_contract_north_goes_to_minus_z_and_elevation_to_y(client):
    prev = period(client, "2025", {"a.obj": cube_obj((E0, N0, Z0))})
    curr = period(client, "2026", {"a.obj": cube_obj((E0, N0 + 100, Z0 + 20))})
    layers = {l["role"]: l for l in scene(client, prev, curr, "a").json()["layers"]}
    shift = glb_vertices(client, layers["current"]["url"]).mean(0) - glb_vertices(client, layers["previous"]["url"]).mean(0)
    assert shift == pytest.approx([0, 20, -100], abs=1e-3)


def test_solid_only_in_one_period_returns_a_single_layer(client):
    prev = period(client, "2025", {"old.obj": cube_obj((E0, N0, Z0))})
    curr = period(client, "2026", {"new.obj": cube_obj((E0, N0, Z0))})
    assert [l["role"] for l in scene(client, prev, curr, "old").json()["layers"]] == ["previous"]
    assert [l["role"] for l in scene(client, prev, curr, "new").json()["layers"]] == ["current"]
    assert scene(client, prev, curr, "nothing").status_code == 404


def test_a_failing_mesh_does_not_hide_the_other_layer(client):
    prev = period(client, "2025", {"a.obj": cube_obj((E0, N0, Z0))})
    curr = period(client, "2026", {"a.obj": b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 1 1\n"})  # degenerate: no usable triangles? still parses
    body = scene(client, prev, curr, "a").json()
    roles = {l["role"]: l for l in body["layers"]}
    assert roles["previous"]["status"] == "ok"
    assert roles["current"]["status"] in {"ok", "failed"}


def test_ambiguous_key_is_a_conflict_not_a_guess(client):
    prev = period(client, "2025", {"x_3pt.obj": cube_obj((E0, N0, Z0)), "x_3.obj": cube_obj((E0, N0, Z0))})
    curr = period(client, "2026", {"x_3.obj": cube_obj((E0, N0, Z0))})
    assert scene(client, prev, curr, "x_3").status_code == 409


def test_second_request_reuses_the_cached_derivative(client, tmp_path):
    prev = period(client, "2025", {"a.obj": cube_obj((E0, N0, Z0))})
    curr = period(client, "2026", {"a.obj": cube_obj((E0 + 3, N0, Z0))})
    first = scene(client, prev, curr, "a").json()
    derived = list((tmp_path / "data" / "derived").glob("*.glb"))
    stamps = {p: p.stat().st_mtime_ns for p in derived}
    second = scene(client, prev, curr, "a").json()
    assert [l["url"] for l in first["layers"]] == [l["url"] for l in second["layers"]]
    assert {p: p.stat().st_mtime_ns for p in tmp_path.glob("data/derived/*.glb")} == stamps and len(derived) == 2


@pytest.mark.parametrize("name", ["..%2F..%2Fcatalog.sqlite3", "x.glb", "abc_../../etc/passwd.glb", "UPPER.glb"])
def test_asset_endpoint_rejects_unsafe_names(client, name):
    assert client.get(f"/api/v1/scene/assets/{name}").status_code == 404


def test_originals_are_untouched(client, tmp_path):
    content = cube_obj((E0, N0, Z0))
    prev = period(client, "2025", {"a.obj": content})
    curr = period(client, "2026", {"a.obj": content})
    scene(client, prev, curr, "a")
    assert all(p.read_bytes() == content for p in (tmp_path / "data" / "originals").glob("*.obj"))
