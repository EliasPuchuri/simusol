import time

import pytest
from fastapi.testclient import TestClient

from solids.api.app import create_app
from solids.infrastructure.catalog import Catalog
from support.meshes import obj_bytes, slab, sphere

QC = "support.qc_fakes:analyze"
CHAR = "support.qc_fakes:characterize"
DONE = {"completed", "completed_with_issues", "failed"}
HEAD = "archivo;tipo_orientacion;azimuth_grados;dip_grados;metodo;origen;observaciones"

SLAB = obj_bytes(slab(120, 30))
SLAB_INVERTED = obj_bytes(slab(120, 30, invert=True))
SPHERE = obj_bytes(sphere())


@pytest.fixture
def env(tmp_path, monkeypatch):
    log = tmp_path / "calls.log"
    monkeypatch.setenv("QC_FAKE_LOG", str(log))
    app = create_app(tmp_path / "data", qc_target=QC, qc_timeout=5.0, char_target=CHAR, char_timeout=3.0)
    with TestClient(app) as client:
        yield client, tmp_path, log


def dataset(client, files, label="2025"):
    d = client.post("/api/v1/datasets", json={"name": "M", "period_label": label, "period_kind": "annual"}).json()
    for name, content in files.items():
        assert client.post(f"/api/v1/datasets/{d['id']}/files", files={"file": (name, content)}).status_code == 201
    return d["id"]


def run(client, ds, path="characterization", timeout=90):
    r = client.post(f"/api/v1/datasets/{ds}/{path}")
    assert r.status_code in (200, 202), r.text
    end = time.time() + timeout
    while time.time() < end:
        body = client.get(f"/api/v1/datasets/{ds}/{path}").json()
        if body["run"] and body["run"]["state"] in DONE:
            return body
        time.sleep(0.2)
    raise AssertionError("run did not finish")


def test_each_solid_gets_its_type_and_orientation(env):
    client, _, _ = env
    ds = dataset(client, {"slab_3pt.obj": SLAB, "ball.obj": SPHERE})
    body = run(client, ds)
    assert body["run"]["state"] == "completed" and body["summary"] == {"ok": 2, "failed": 0, "pending": 0}
    by = {r["filename"]: r for r in body["results"]}
    s, b = by["slab_3pt.obj"], by["ball.obj"]
    assert s["key"] == "slab_3" and s["body_type"] == "TABULAR" and s["orientation"]["type"] == "planar"
    assert s["orientation"]["dip"] == pytest.approx(30, abs=2) and s["eigenvalues"][0] >= s["eigenvalues"][1] >= s["eigenvalues"][2]
    assert b["body_type"] == "GLOBULAR" and b["orientation"]["reason"] == "similar_eigenvalues"
    assert "segments" not in s and "segments" not in s["evidence"]


def test_a_file_that_kills_the_process_fails_alone(env):
    client, _, _ = env
    ds = dataset(client, {"a.obj": SLAB, "crash.obj": obj_bytes(slab(), "#crash\n"), "b.obj": SPHERE})
    body = run(client, ds)
    assert body["run"]["state"] == "completed_with_issues" and body["summary"]["failed"] == 1
    by = {r["filename"]: r for r in body["results"]}
    assert by["crash.obj"]["status"] == "failed" and by["a.obj"]["status"] == "ok" and by["b.obj"]["status"] == "ok"


def test_results_are_reused_by_content_hash_and_failures_are_retried(env):
    client, _, log = env
    run(client, dataset(client, {"a.obj": SLAB}))
    done = len(log.read_text().split())
    body = run(client, dataset(client, {"other_name.obj": SLAB}, label="2026"))
    assert len(log.read_text().split()) == done and body["summary"]["ok"] == 1
    crash = dataset(client, {"crash.obj": obj_bytes(slab(), "#crash\n")}, label="x")
    before = len(log.read_text().split())
    run(client, crash)
    run(client, crash)
    assert len(log.read_text().split()) == before + 2


def test_pending_before_any_run_and_error_cases(env):
    client, _, _ = env
    ds = dataset(client, {"a.obj": SLAB})
    body = client.get(f"/api/v1/datasets/{ds}/characterization").json()
    assert body["run"] is None and body["summary"] == {"ok": 0, "failed": 0, "pending": 1}
    empty = client.post("/api/v1/datasets", json={"name": "M", "period_label": "e", "period_kind": "annual"}).json()["id"]
    assert client.post(f"/api/v1/datasets/{empty}/characterization").status_code == 422
    for path in ("characterization", "characterization.csv"):
        assert client.get(f"/api/v1/datasets/nope/{path}").status_code == 404
    assert client.post("/api/v1/datasets/nope/characterization").status_code == 404


def test_reference_table_is_contrasted_with_the_computed_orientation(env):
    client, _, _ = env
    ds = dataset(client, {"slab_3pt.obj": SLAB, "ball.obj": SPHERE})
    ref = f"{HEAD}\nslab_3.obj;planar;121;31;Studio RM;;\nball.obj;axial;10;20;Studio RM;;\n"
    assert client.post(f"/api/v1/datasets/{ds}/orientation-reference", files={"file": ("r.csv", ref.encode())}).status_code == 200
    by = {r["filename"]: r for r in run(client, ds)["results"]}
    r = by["slab_3pt.obj"]["reference"]
    assert r["method"] == "Studio RM" and r["azimuth"] == 121 and r["comparison"]["comparable"] is True
    assert r["comparison"]["delta_azimuth_deg"] < 3.0 and r["comparison"]["delta_dip_deg"] < 3.0
    assert by["ball.obj"]["reference"]["comparison"] == {"comparable": False, "reason": "not_interpretable"}


def test_without_reference_the_field_is_empty(env):
    client, _, _ = env
    by = {r["filename"]: r for r in run(client, dataset(client, {"a.obj": SLAB}))["results"]}
    assert by["a.obj"]["reference"] is None


def test_csv_part1_lists_type_orientation_and_never_invents_a_volume(env):
    client, _, _ = env
    ds = dataset(client, {"slab_3pt.obj": SLAB_INVERTED, "ball.obj": SPHERE})
    run(client, ds)
    csv1 = client.get(f"/api/v1/datasets/{ds}/characterization.csv")
    assert csv1.status_code == 200 and "reporte_parte1.csv" in csv1.headers["content-disposition"]
    assert csv1.content.startswith(b"\xef\xbb\xbf")
    header, *rows = csv1.content.decode("utf-8-sig").strip().splitlines()
    recs = [dict(zip(header.split(";"), r.split(";"))) for r in rows]
    by = {r["Archivo"]: r for r in recs}
    s = by["slab_3pt.obj"]
    assert (s["Periodo"], s["Clave"], s["Tipo_cuerpo"], s["Tipo_orientacion"]) == ("2025", "slab_3", "TABULAR", "planar")
    assert float(s["Lambda1"]) >= float(s["Lambda2"]) >= float(s["Lambda3"]) > 0
    assert s["Volumen_m3"] == "" and s["Volumen_motivo"] == "qc_pendiente"  # QC has not run: no volume, no zero
    assert by["ball.obj"]["Azimuth"] == "" and by["ball.obj"]["Dip"] == "" and "similar_eigenvalues" in by["ball.obj"]["Observaciones"]
    run(client, ds, "qc")
    after = client.get(f"/api/v1/datasets/{ds}/characterization.csv").content.decode("utf-8-sig").strip().splitlines()
    rec = dict(zip(after[0].split(";"), [r for r in after[1:] if "slab_3pt" in r][0].split(";")))
    assert rec["Volumen_m3"] == "" and rec["Volumen_motivo"] == "inverted_orientation"


def test_runs_left_running_are_marked_interrupted_for_both_kinds(tmp_path):
    (tmp_path / "data").mkdir()
    catalog = Catalog(tmp_path / "data" / "catalog.sqlite3")
    with TestClient(create_app(tmp_path / "data", qc_target=QC, char_target=CHAR)) as client:
        ds = dataset(client, {"a.obj": SLAB})
    catalog.create_run("characterization", ds, total=1, state="running")
    with TestClient(create_app(tmp_path / "data", qc_target=QC, char_target=CHAR)) as client:
        run_ = client.get(f"/api/v1/datasets/{ds}/characterization").json()["run"]
    assert run_["state"] == "failed" and run_["error"] == "interrupted by a restart"
