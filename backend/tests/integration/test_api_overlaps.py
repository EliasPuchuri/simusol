import time

import pytest
from fastapi.testclient import TestClient

from solids.api.app import create_app
from support.meshes import cube, obj_bytes

U = (367_800.0, 8_827_600.0, 3_300.0)
at = lambda dx=0.0: (U[0] + dx, U[1], U[2])
DONE = {"completed", "completed_with_issues", "failed"}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "data", overlap_timeout=60.0)) as c:
        yield c


def period(client, files, label="2025"):
    d = client.post("/api/v1/datasets", json={"name": "M", "period_label": label, "period_kind": "annual"}).json()
    for name, mesh in files.items():
        assert client.post(f"/api/v1/datasets/{d['id']}/files", files={"file": (name, obj_bytes(mesh))}).status_code == 201
    client.post(f"/api/v1/datasets/{d['id']}/finalize")
    return d["id"]


def run(client, dataset_id, timeout=120):
    r = client.post(f"/api/v1/datasets/{dataset_id}/overlaps")
    assert r.status_code in (200, 202), r.text
    end = time.time() + timeout
    while time.time() < end:
        body = client.get(f"/api/v1/datasets/{dataset_id}/overlaps").json()
        if body["run"] and body["run"]["state"] in DONE:
            return body
        time.sleep(0.3)
    raise AssertionError("overlap run did not finish")


def test_nothing_is_reported_before_the_analysis_runs(client):
    d = period(client, {"a.obj": cube(at(), 10), "b.obj": cube(at(5), 10)})
    body = client.get(f"/api/v1/datasets/{d}/overlaps").json()
    assert body["evaluated"] is False and body["pairs"] == [] and body["run"] is None


def test_finds_the_overlapping_pair_once_with_both_solids_and_the_volume(client):
    d = period(client, {"a.obj": cube(at(), 10), "b.obj": cube(at(5), 10), "far.obj": cube(at(500), 10)})
    body = run(client, d)
    assert body["run"]["state"] == "completed" and body["evaluated"] is True
    s = body["summary"]
    assert (s["solids"], s["pairs"], s["discarded"], s["overlapping"]) == (3, 3, 2, 1)
    assert len(body["pairs"]) == 1
    p = body["pairs"][0]
    assert (p["a"], p["b"], p["relation"]) == ("a.obj", "b.obj", "overlap")
    assert p["common_m3"] == pytest.approx(500.0, rel=1e-6) and p["common_pct_of_smaller"] == pytest.approx(50.0, rel=1e-6)


def test_touching_solids_are_reported_as_contact_and_separated_ones_are_not_listed(client):
    d = period(client, {"a.obj": cube(at(), 10), "b.obj": cube(at(10), 10)})
    body = run(client, d)
    assert body["summary"]["contact"] == 1 and body["summary"]["overlapping"] == 0
    assert [p["relation"] for p in body["pairs"]] == ["contact"]


def test_an_unclosed_solid_is_listed_as_not_evaluable_with_its_reason(client):
    broken = cube(at(), 10)
    broken.faces = broken.faces[:-1]
    d = period(client, {"a.obj": broken, "b.obj": cube(at(5), 10)})
    body = run(client, d)
    assert body["summary"]["not_evaluable"] == 1
    assert body["pairs"][0]["relation"] == "not_evaluable" and body["pairs"][0]["reason"] == "not_watertight:a"
    assert body["pairs"][0]["common_m3"] is None


def test_a_second_run_reuses_the_cache_and_does_not_recompute_any_pair(tmp_path, monkeypatch):
    log = tmp_path / "overlap.log"
    monkeypatch.setenv("OVERLAP_LOG", str(log))
    with TestClient(create_app(tmp_path / "data", overlap_target="support.overlap_fakes:overlap", overlap_timeout=60.0)) as client:
        d = period(client, {"a.obj": cube(at(), 10), "b.obj": cube(at(5), 10), "far.obj": cube(at(500), 10)})
        first = run(client, d)
        assert len(log.read_text().splitlines()) == 1          # only the pair whose boxes touch reaches the boolean
        second = run(client, d)
        assert len(log.read_text().splitlines()) == 1          # nothing was recomputed
        assert second["summary"] == first["summary"] and second["pairs"] == first["pairs"]


def test_a_period_with_fewer_than_two_solids_cannot_be_analysed(client):
    d = period(client, {"a.obj": cube(at(), 10)})
    assert client.post(f"/api/v1/datasets/{d}/overlaps").status_code == 422


def test_unknown_period_is_404(client):
    assert client.post("/api/v1/datasets/nope/overlaps").status_code == 404
    assert client.get("/api/v1/datasets/nope/overlaps").status_code == 404
