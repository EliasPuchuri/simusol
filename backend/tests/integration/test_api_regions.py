import io

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

from solids.api.app import create_app
from support.meshes import cube, obj_bytes

QC, CHAR, CMP, SINGLE = "support.qc_fakes:analyze", "support.qc_fakes:characterize", "support.qc_fakes:compare", "support.qc_fakes:single"
REG = "support.qc_fakes:regions"
U = (367_800.0, 8_827_600.0, 3_300.0)


@pytest.fixture
def env(tmp_path, monkeypatch):
    log = tmp_path / "calls.log"
    monkeypatch.setenv("QC_FAKE_LOG", str(log))
    app = create_app(tmp_path / "data", qc_target=QC, char_target=CHAR, compare_target=CMP, single_target=SINGLE,
                     regions_target=REG, regions_timeout=30.0)
    with TestClient(app) as client:
        yield client, tmp_path, log


def period(client, label, files):
    d = client.post("/api/v1/datasets", json={"name": "M", "period_label": label, "period_kind": "annual"}).json()
    for name, content in files.items():
        assert client.post(f"/api/v1/datasets/{d['id']}/files", files={"file": (name, content)}).status_code == 201
    client.post(f"/api/v1/datasets/{d['id']}/finalize")
    return d["id"]


def regions(client, prev, curr, key="a_3"):
    return client.get("/api/v1/scene/regions", params={"previous": prev, "current": curr, "key": key})


def glb(client, url) -> np.ndarray:
    r = client.get(url)
    assert r.status_code == 200 and r.headers["content-type"].startswith("model/gltf-binary")
    return np.asarray(trimesh.load(trimesh.util.wrap_as_stream(r.content), file_type="glb", force="mesh").vertices)


def shifted_pair(client, dx=5.0, invert=False):
    prev = period(client, "2025", {"a_3pt.obj": obj_bytes(cube(U, invert=invert))})
    curr = period(client, "2026", {"a_3.obj": obj_bytes(cube((U[0] + dx, U[1], U[2]), invert=invert))})
    return prev, curr


def test_common_added_and_removed_zones_have_the_expected_volumes(env):
    client, _, _ = env
    body = regions(client, *shifted_pair(client)).json()
    r = body["regions"]
    assert body["status"] == "ok" and body["provisional"] is True
    for role in ("common", "added", "removed"):
        assert r[role]["status"] == "ok" and r[role]["volume_m3"] == pytest.approx(500.0, rel=1e-6) and r[role]["triangles"] > 0
    assert body["origin"]["east"] == pytest.approx(U[0] + 2.5)


def test_the_zones_are_in_the_same_scene_coordinates_as_the_two_periods(env):
    client, _, _ = env
    prev, curr = shifted_pair(client)
    zones = regions(client, prev, curr).json()["regions"]
    layers = {l["role"]: l for l in client.get("/api/v1/scene", params={"previous": prev, "current": curr, "key": "a_3"}).json()["layers"]}
    vp, vc = glb(client, layers["previous"]["url"]), glb(client, layers["current"]["url"])
    common, added, removed = (glb(client, zones[k]["url"]) for k in ("common", "added", "removed"))
    # previous spans x in [-7.5, 2.5], current in [-2.5, 7.5] (scene x = East - E0): common is the overlap, the others the rest
    assert (vp[:, 0].min(), vp[:, 0].max()) == pytest.approx((-7.5, 2.5), abs=1e-3)
    assert (common[:, 0].min(), common[:, 0].max()) == pytest.approx((-2.5, 2.5), abs=1e-3)
    assert (removed[:, 0].min(), removed[:, 0].max()) == pytest.approx((-7.5, -2.5), abs=1e-3)
    assert (added[:, 0].min(), added[:, 0].max()) == pytest.approx((2.5, 7.5), abs=1e-3)
    assert np.abs(np.vstack([common, added, removed])).max() < 20  # no UTM magnitudes


def test_identical_solids_have_no_added_or_removed_zone(env):
    client, _, _ = env
    r = regions(client, *shifted_pair(client, dx=0.0)).json()["regions"]
    assert r["common"]["status"] == "ok"
    for role in ("added", "removed"):
        assert r[role]["status"] == "empty" and r[role]["volume_m3"] == 0.0 and "url" not in r[role]


def test_inverted_orientation_is_normalised_on_a_copy_and_flagged(env):
    client, _, _ = env
    body = regions(client, *shifted_pair(client, invert=True)).json()
    assert body["regions"]["common"]["volume_m3"] == pytest.approx(500.0, rel=1e-6)
    assert {"inverted_orientation_normalized:previous", "inverted_orientation_normalized:current"} <= set(body["warnings"])


def test_a_solid_with_an_open_surface_has_unavailable_zones_with_the_reason(env):
    client, _, _ = env
    open_mesh = cube(U)
    open_mesh.faces = open_mesh.faces[:-2]
    prev = period(client, "2025", {"a_3pt.obj": obj_bytes(open_mesh)})
    curr = period(client, "2026", {"a_3.obj": obj_bytes(cube(U))})
    r = regions(client, prev, curr).json()["regions"]
    assert all(r[k]["status"] == "unavailable" and r[k]["reason"] == "not_watertight:previous" for k in r)


def test_only_solids_present_in_both_periods_have_zones(env):
    client, _, _ = env
    prev = period(client, "2025", {"old_3pt.obj": obj_bytes(cube(U))})
    curr = period(client, "2026", {"new_3.obj": obj_bytes(cube(U))})
    assert regions(client, prev, curr, key="old_3").status_code == 404
    assert regions(client, prev, prev, key="old_3").status_code == 422
    assert client.get("/api/v1/scene/regions", params={"previous": prev, "current": "nope", "key": "x"}).status_code == 404


def test_zones_are_cached_by_content(env):
    client, _, log = env
    prev, curr = shifted_pair(client)
    first = regions(client, prev, curr).json()
    done = len(log.read_text().split())
    second = regions(client, prev, curr).json()
    assert len(log.read_text().split()) == done and first["regions"]["common"]["url"] == second["regions"]["common"]["url"]


def test_a_process_that_dies_gives_a_failed_answer_that_is_not_cached(env):
    client, _, log = env
    prev = period(client, "2025", {"a_3pt.obj": obj_bytes(cube(U), "#crash\n")})
    curr = period(client, "2026", {"a_3.obj": obj_bytes(cube(U))})
    body = regions(client, prev, curr).json()
    assert body["status"] == "failed" and body["error"] and body["regions"] is None
    regions(client, prev, curr)
    assert len(log.read_text().split()) == 2  # retried, not cached


@pytest.mark.parametrize("name", ["x.glb", "../catalog.sqlite3", "UPPER-" + "a" * 64 + ".glb", "a" * 64 + "-" + "b" * 64 + "_1_2_3_other.glb"])
def test_asset_names_stay_whitelisted(env, name):
    client, _, _ = env
    assert client.get(f"/api/v1/scene/assets/{name}").status_code == 404
