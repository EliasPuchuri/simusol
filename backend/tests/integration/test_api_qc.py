import hashlib
import io
import time
from pathlib import Path

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

from solids.api.app import create_app
from solids.infrastructure.catalog import Catalog

FAKES = "support.qc_fakes:analyze"
DONE = {"completed", "completed_with_issues", "failed"}


def obj_bytes(faces_transform=lambda f: f, drop=0, extra="") -> bytes:
    mesh = trimesh.creation.box(extents=(10, 10, 10))
    faces = faces_transform(mesh.faces.tolist())
    faces = faces[: len(faces) - drop] if drop else faces
    lines = [f"v {x:.5f} {y:.5f} {z:.5f}" for x, y, z in (mesh.vertices + 5)] + [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in faces]
    return (extra + "\n".join(lines) + "\n").encode()


GOOD = obj_bytes()
INVERTED = obj_bytes(lambda f: [(a, c, b) for a, b, c in f])
OPEN = obj_bytes(drop=2)


@pytest.fixture
def env(tmp_path, monkeypatch):
    log = tmp_path / "qc.log"
    monkeypatch.setenv("QC_FAKE_LOG", str(log))
    app = create_app(tmp_path / "data", qc_target=FAKES, qc_timeout=3.0)
    with TestClient(app) as client:
        yield client, tmp_path, log


def dataset(client, files):
    d = client.post("/api/v1/datasets", json={"name": "M", "period_label": "2025", "period_kind": "annual"}).json()
    for name, content in files.items():
        assert client.post(f"/api/v1/datasets/{d['id']}/files", files={"file": (name, content)}).status_code == 201
    return d["id"]


def run_qc(client, dataset_id, timeout=90):
    r = client.post(f"/api/v1/datasets/{dataset_id}/qc")
    assert r.status_code in (200, 202), r.text
    end = time.time() + timeout
    while time.time() < end:
        body = client.get(f"/api/v1/datasets/{dataset_id}/qc").json()
        if body["run"] and body["run"]["state"] in DONE:
            return body
        time.sleep(0.2)
    raise AssertionError("QC did not finish")


def test_qc_reports_each_file_and_never_calls_an_inverted_volume_valid(env):
    client, _, _ = env
    ds = dataset(client, {"good_3pt.obj": GOOD, "inv_3.obj": INVERTED, "open.obj": OPEN})
    body = run_qc(client, ds)
    assert body["run"]["state"] == "completed" and (body["run"]["done"], body["run"]["total"]) == (3, 3)
    by = {r["filename"]: r for r in body["results"]}
    assert by["good_3pt.obj"]["status"] == "ok" and by["good_3pt.obj"]["key"] == "good_3"
    assert by["inv_3.obj"]["status"] == "with_issues" and "inverted_orientation" in by["inv_3.obj"]["problems"]
    assert by["inv_3.obj"]["volume_m3"]["value"] is None and by["inv_3.obj"]["volume_m3"]["reason"] == "inverted_orientation"
    assert by["open.obj"]["open_edges"] > 0
    assert body["summary"] == {"ok": 1, "with_issues": 2, "failed": 0, "pending": 0}


def test_a_crashing_file_does_not_stop_the_batch(env):
    client, _, _ = env
    ds = dataset(client, {"a.obj": GOOD, "crash.obj": obj_bytes(extra="#crash\n"), "b.obj": INVERTED})
    body = run_qc(client, ds)
    assert body["run"]["state"] == "completed_with_issues"
    by = {r["filename"]: r for r in body["results"]}
    assert by["crash.obj"]["status"] == "failed" and by["crash.obj"]["error"]
    assert by["a.obj"]["status"] == "ok" and by["b.obj"]["status"] == "with_issues"
    assert body["summary"]["failed"] == 1


def test_results_are_reused_by_content_hash(env):
    client, _, log = env
    ds1 = dataset(client, {"a.obj": GOOD, "b.obj": INVERTED})
    run_qc(client, ds1)
    analyzed = len(log.read_text().split())
    ds2 = dataset(client, {"same_name_other.obj": GOOD, "b2.obj": INVERTED})  # identical bytes, other names
    body = run_qc(client, ds2)
    assert len(log.read_text().split()) == analyzed  # nothing was analyzed again
    assert body["run"]["state"] == "completed" and {r["status"] for r in body["results"]} == {"ok", "with_issues"}


def test_failed_files_are_retried_on_the_next_run(env):
    client, _, log = env
    ds = dataset(client, {"crash.obj": obj_bytes(extra="#crash\n")})
    run_qc(client, ds)
    run_qc(client, ds)
    assert len(log.read_text().split()) == 2


def test_results_before_any_run_are_pending(env):
    client, _, _ = env
    ds = dataset(client, {"a.obj": GOOD})
    body = client.get(f"/api/v1/datasets/{ds}/qc").json()
    assert body["run"] is None and body["summary"]["pending"] == 1 and body["results"][0]["status"] == "pending"


def test_csv_report_has_one_row_per_solid_and_honest_blanks(env):
    client, _, _ = env
    ds = dataset(client, {"inv_3pt.obj": INVERTED})
    run_qc(client, ds)
    r = client.get(f"/api/v1/datasets/{ds}/qc.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "reporte_parte0.csv" in r.headers["content-disposition"]
    text = r.content.decode("utf-8-sig")
    assert r.content.startswith(b"\xef\xbb\xbf")
    header, row = text.strip().splitlines()
    cols, vals = header.split(";"), row.split(";")
    rec = dict(zip(cols, vals))
    assert rec["Archivo"] == "inv_3pt.obj" and rec["Clave"] == "inv_3" and rec["Periodo"] == "2025"
    assert rec["Volumen_m3"] == "" and rec["Volumen_motivo"] == "inverted_orientation"  # never 0, never abs()
    assert float(rec["Volumen_firmado_m3"]) == pytest.approx(-1000.0)
    assert "inverted_orientation" in rec["Problemas"] and rec["Superposicion_con_otros_cuerpos"] == "no_evaluada"


def test_empty_or_unknown_dataset(env):
    client, _, _ = env
    empty = client.post("/api/v1/datasets", json={"name": "M", "period_label": "x", "period_kind": "annual"}).json()["id"]
    assert client.post(f"/api/v1/datasets/{empty}/qc").status_code == 422
    assert client.post("/api/v1/datasets/nope/qc").status_code == 404
    assert client.get("/api/v1/datasets/nope/qc").status_code == 404
    assert client.get("/api/v1/datasets/nope/qc.csv").status_code == 404


def test_a_run_left_running_by_a_restart_is_marked_interrupted(tmp_path):
    (tmp_path / "data").mkdir()
    catalog = Catalog(tmp_path / "data" / "catalog.sqlite3")
    app = create_app(tmp_path / "data", qc_target=FAKES)
    with TestClient(app) as client:
        ds = dataset(client, {"a.obj": GOOD})
    catalog.create_qc_run(ds, total=1, state="running")
    with TestClient(create_app(tmp_path / "data", qc_target=FAKES)) as client:
        run = client.get(f"/api/v1/datasets/{ds}/qc").json()["run"]
    assert run["state"] == "failed" and run["error"] == "interrupted by a restart"


def test_the_originals_are_never_touched_by_qc(env):
    client, tmp_path, _ = env
    ds = dataset(client, {"a.obj": INVERTED})
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (tmp_path / "data" / "originals").glob("*.obj")}
    run_qc(client, ds)
    assert before and {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before} == before
