import hashlib
import time

import pytest
from fastapi.testclient import TestClient

from solids.api.app import create_app
from solids.infrastructure.catalog import Catalog
from support.meshes import cube, obj_bytes

QC, CHAR, CMP = "support.qc_fakes:analyze", "support.qc_fakes:characterize", "support.qc_fakes:compare"
SINGLE = "support.qc_fakes:single"
DONE = {"completed", "completed_with_issues", "failed"}
U = (367_800.0, 8_827_600.0, 3_300.0)


@pytest.fixture
def env(tmp_path, monkeypatch):
    log = tmp_path / "calls.log"
    monkeypatch.setenv("QC_FAKE_LOG", str(log))
    app = create_app(tmp_path / "data", qc_target=QC, char_target=CHAR, compare_target=CMP, compare_timeout=20.0, single_target=SINGLE)
    with TestClient(app) as client:
        yield client, tmp_path, log


def period(client, label, files, close=True):
    d = client.post("/api/v1/datasets", json={"name": "M", "period_label": label, "period_kind": "annual"}).json()
    for name, content in files.items():
        assert client.post(f"/api/v1/datasets/{d['id']}/files", files={"file": (name, content)}).status_code == 201
    if close:
        client.post(f"/api/v1/datasets/{d['id']}/finalize")
    return d["id"]


def run(client, prev, curr, timeout=120):
    r = client.post("/api/v1/comparisons", json={"previous": prev, "current": curr})
    assert r.status_code in (200, 202), r.text
    end = time.time() + timeout
    while time.time() < end:
        body = client.get("/api/v1/comparisons", params={"previous": prev, "current": curr}).json()
        if body["run"] and body["run"]["state"] in DONE:
            return body
        time.sleep(0.3)
    raise AssertionError("comparison did not finish")


def standard(client):
    prev = period(client, "2025", {"a_3pt.obj": obj_bytes(cube(U)), "b_3pt.obj": obj_bytes(cube(U)), "old_3pt.obj": obj_bytes(cube(U, 7))})
    curr = period(client, "2026", {"a_3.obj": obj_bytes(cube(U)), "b_3.obj": obj_bytes(cube((U[0] + 8, U[1], U[2]))), "new_3.obj": obj_bytes(cube(U, 9))})
    return prev, curr


def rows(body):
    return {r["key"]: r for r in body["rows"]}


def test_each_pair_gets_a_state_with_a_description_and_the_inventory_gives_nuevo_and_eliminado(env):
    client, _, _ = env
    body = run(client, *standard(client))
    r = rows(body)
    assert body["run"]["state"] == "completed" and body["provisional"] is True
    assert r["a_3"]["state"] == "SIN CAMBIOS" and r["a_3"]["subtype"] == "IDENTICO" and r["a_3"]["description"].startswith("SIN CAMBIO")
    assert r["b_3"]["state"] == "VARIABLE" and "TRASLACION" in r["b_3"]["events"] and "TRASLACIÓN" in r["b_3"]["description"]
    assert r["old_3"]["state"] == "ELIMINADO" and "no existe en el periodo actual" in r["old_3"]["description"] and "renombr" in r["old_3"]["description"]
    assert r["new_3"]["state"] == "NUEVO" and "no existía en el periodo anterior" in r["new_3"]["description"]
    assert body["summary"] == {"SIN CAMBIOS": 1, "VARIABLE": 1, "NUEVO": 1, "ELIMINADO": 1, "sin_clasificar": 0, "pendientes": 0}
    m = r["b_3"]["metrics"]
    assert m["iou_pct"] == pytest.approx(100 * 200 / 1800, rel=1e-4) and m["centroid_m"] == pytest.approx(8.0, abs=1e-3)
    assert r["b_3"]["checks"] and r["b_3"]["profile"] == "pilot-v1-provisional"


def test_before_any_run_pairs_are_pending_but_new_and_removed_are_already_known(env):
    client, _, _ = env
    prev, curr = standard(client)
    body = client.get("/api/v1/comparisons", params={"previous": prev, "current": curr}).json()
    assert body["run"] is None and body["summary"]["pendientes"] == 2
    r = rows(body)
    assert r["a_3"]["status"] == "pending" and r["a_3"]["state"] is None
    assert r["old_3"]["state"] == "ELIMINADO" and r["new_3"]["state"] == "NUEVO"


def test_a_pair_that_kills_the_process_is_unassigned_never_variable(env):
    client, _, _ = env
    prev = period(client, "2025", {"a_3pt.obj": obj_bytes(cube(U)), "x_3pt.obj": obj_bytes(cube(U), "#crash\n")})
    curr = period(client, "2026", {"a_3.obj": obj_bytes(cube(U)), "x_3.obj": obj_bytes(cube(U))})
    body = run(client, prev, curr)
    r = rows(body)
    assert body["run"]["state"] == "completed_with_issues"
    assert r["x_3"]["state"] is None and r["x_3"]["status"] == "failed" and r["x_3"]["incidents"]  # RC-29
    assert r["a_3"]["state"] == "SIN CAMBIOS"
    assert body["summary"]["sin_clasificar"] == 1 and body["summary"]["VARIABLE"] == 0


def test_results_are_reused_by_content_hash(env):
    client, _, log = env
    prev, curr = standard(client)
    run(client, prev, curr)
    done = len(log.read_text().split())
    run(client, prev, curr)
    assert len(log.read_text().split()) == done


def test_both_periods_must_exist_be_different_and_closed(env):
    client, _, _ = env
    closed = period(client, "2025", {"a.obj": obj_bytes(cube(U))})
    still_open = period(client, "2026", {"a.obj": obj_bytes(cube(U))}, close=False)
    post = lambda p, c: client.post("/api/v1/comparisons", json={"previous": p, "current": c}).status_code
    assert post(closed, still_open) == 409 and post(closed, closed) == 422 and post(closed, "nope") == 404
    assert client.get("/api/v1/comparisons", params={"previous": closed, "current": "nope"}).status_code == 404
    assert client.get("/api/v1/comparisons/report.csv", params={"previous": closed, "current": still_open}).status_code == 409


def test_the_run_also_fills_part_1_for_every_solid_of_the_comparison(env):
    client, _, _ = env
    prev, curr = standard(client)
    run(client, prev, curr)
    assert client.get(f"/api/v1/datasets/{prev}/characterization").json()["summary"]["ok"] == 3  # a_3 and b_3 (paired) and old_3 (only in this period)


def test_csv_part2_follows_the_contract_and_leaves_failures_blank(env):
    client, _, _ = env
    prev = period(client, "2025", {"a_3pt.obj": obj_bytes(cube(U)), "x_3pt.obj": obj_bytes(cube(U), "#crash\n"), "old_3pt.obj": obj_bytes(cube(U))})
    curr = period(client, "2026", {"a_3.obj": obj_bytes(cube((U[0] + 8, U[1], U[2]))), "x_3.obj": obj_bytes(cube(U)), "new_3.obj": obj_bytes(cube(U))})
    run(client, prev, curr)
    r = client.get("/api/v1/comparisons/report.csv", params={"previous": prev, "current": curr})
    assert r.status_code == 200 and "reporte_parte2.csv" in r.headers["content-disposition"] and r.content.startswith(b"\xef\xbb\xbf")
    header, *lines = r.content.decode("utf-8-sig").strip().splitlines()
    recs = {d["Cuerpo"]: d for d in (dict(zip(header.split(";"), ln.split(";"))) for ln in lines)}
    a, x, old, new = recs["a_3"], recs["x_3"], recs["old_3"], recs["new_3"]
    assert (a["Mesh_anterior"], a["Mesh_actual"], a["Periodo_anterior"], a["Periodo_actual"]) == ("a_3pt.obj", "a_3.obj", "2025", "2026")
    assert a["Estado"] == "VARIABLE" and float(a["IoU_pct"]) == pytest.approx(100 * 200 / 1800, rel=1e-4) and a["Volumen_provisional"] == "si"
    assert float(a["V_anterior_m3"]) == pytest.approx(1000.0) and a["Descripcion"].startswith("TRASLACIÓN")
    assert x["Estado"] == "" and x["IoU_pct"] == "" and x["Estado_tecnico"] == "failed"  # failure is never VARIABLE or SIN CAMBIOS
    assert old["Estado"] == "ELIMINADO" and old["Mesh_actual"] == "" and old["IoU_pct"] == ""
    assert new["Estado"] == "NUEVO" and new["Mesh_anterior"] == ""


def test_runs_left_running_are_interrupted_on_restart(tmp_path):
    (tmp_path / "data").mkdir()
    catalog = Catalog(tmp_path / "data" / "catalog.sqlite3")
    with TestClient(create_app(tmp_path / "data", qc_target=QC, char_target=CHAR, compare_target=CMP, single_target=SINGLE)) as client:
        prev, curr = standard(client)
    catalog.create_comparison_run(prev, curr, total=2, state="running")
    with TestClient(create_app(tmp_path / "data", qc_target=QC, char_target=CHAR, compare_target=CMP, single_target=SINGLE)) as client:
        body = client.get("/api/v1/comparisons", params={"previous": prev, "current": curr}).json()
    assert body["run"]["state"] == "failed" and body["run"]["error"] == "interrupted by a restart"


def test_the_originals_are_never_touched(env):
    client, tmp_path, _ = env
    prev, curr = standard(client)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (tmp_path / "data" / "originals").glob("*.obj")}
    run(client, prev, curr)
    assert before and {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before} == before


def test_new_and_removed_solids_get_a_provisional_volume_and_part_1(env):
    client, _, _ = env
    body = run(client, *standard(client))
    r = rows(body)
    assert r["new_3"]["volumes"]["current_m3"] == pytest.approx(729.0) and r["new_3"]["volumes"]["previous_m3"] is None
    assert r["old_3"]["volumes"]["previous_m3"] == pytest.approx(343.0)
    assert r["new_3"]["characterization"]["current"]["status"] == "ok" and r["old_3"]["characterization"]["previous"]["status"] == "ok"
    assert r["new_3"]["state"] == "NUEVO" and r["old_3"]["state"] == "ELIMINADO"  # states come from the inventory, not from metrics


def test_total_volumes_sum_every_solid_of_each_period_and_say_what_they_are(env):
    client, _, _ = env
    body = run(client, *standard(client))
    t = body["totals"]
    assert t["available"] is True and t["provisional"] is True
    assert t["previous"]["sum_m3"] == pytest.approx(1000 + 1000 + 343) and t["current"]["sum_m3"] == pytest.approx(1000 + 1000 + 729)
    assert (t["previous"]["counted"], t["previous"]["total"]) == (3, 3)
    assert t["difference_m3"] == pytest.approx(386.0) and t["difference_pct"] == pytest.approx(100 * 386 / 2343)
    assert {"sum_of_bodies_not_union", "overlap_not_evaluated"} <= set(t["warnings"])


def _find_overlaps(client, dataset_id, timeout=120):
    client.post(f"/api/v1/datasets/{dataset_id}/overlaps")
    end = time.time() + timeout
    while time.time() < end:
        body = client.get(f"/api/v1/datasets/{dataset_id}/overlaps").json()
        if body["run"] and body["run"]["state"] in DONE:
            return body
        time.sleep(0.3)
    raise AssertionError("overlap run did not finish")


def test_totals_say_the_overlaps_were_not_evaluated_until_they_are(env):
    client, _, _ = env
    t = run(client, *standard(client))["totals"]
    assert t["previous"]["overlap"] == {"evaluated": False, "pairs": None, "pairwise_common_m3": None}
    assert "overlap_not_evaluated" in t["warnings"] and "overlap_found" not in t["warnings"]


def test_totals_report_how_many_solids_overlap_once_each_period_was_analysed(env):
    client, _, _ = env
    prev, curr = standard(client)
    _find_overlaps(client, prev)
    _find_overlaps(client, curr)
    t = run(client, prev, curr)["totals"]
    assert t["previous"]["overlap"]["evaluated"] is True and t["previous"]["overlap"]["pairs"] == 3
    assert t["previous"]["overlap"]["pairwise_common_m3"] == pytest.approx(1000 + 343 + 343)
    assert t["current"]["overlap"]["pairs"] == 3 and t["current"]["overlap"]["pairwise_common_m3"] == pytest.approx(200 + 729 + 121.5)
    assert "overlap_found" in t["warnings"] and "overlap_not_evaluated" not in t["warnings"]


def test_only_one_period_analysed_still_counts_as_not_evaluated(env):
    client, _, _ = env
    prev, curr = standard(client)
    _find_overlaps(client, prev)
    t = run(client, prev, curr)["totals"]
    assert t["previous"]["overlap"]["evaluated"] is True and t["current"]["overlap"]["evaluated"] is False
    assert "overlap_not_evaluated" in t["warnings"]


def test_totals_are_not_available_before_the_comparison_is_calculated(env):
    client, _, _ = env
    prev, curr = standard(client)
    body = client.get("/api/v1/comparisons", params={"previous": prev, "current": curr}).json()
    assert body["totals"]["available"] is False


def test_a_solid_without_a_valid_volume_is_excluded_from_the_totals_and_listed(env):
    client, _, _ = env
    open_mesh = cube(U)
    open_mesh.faces = open_mesh.faces[:-2]
    prev = period(client, "2025", {"x_3pt.obj": obj_bytes(open_mesh), "a_3pt.obj": obj_bytes(cube(U))})
    curr = period(client, "2026", {"x_3.obj": obj_bytes(cube(U, 6)), "a_3.obj": obj_bytes(cube(U))})
    t = run(client, prev, curr)["totals"]
    assert t["previous"]["sum_m3"] == pytest.approx(1000.0) and (t["previous"]["counted"], t["previous"]["total"]) == (1, 2)
    assert t["previous"]["excluded"] == [{"key": "x_3", "reason": "not_watertight:previous"}]
    assert t["current"]["sum_m3"] == pytest.approx(1000 + 216) and "excluded_solids" in t["warnings"]


def test_a_crashing_removed_solid_keeps_its_state_but_is_excluded_from_totals(env):
    client, _, _ = env
    prev = period(client, "2025", {"a_3pt.obj": obj_bytes(cube(U)), "gone_3pt.obj": obj_bytes(cube(U, 8), "#crash\n")})
    curr = period(client, "2026", {"a_3.obj": obj_bytes(cube(U))})
    body = run(client, prev, curr)
    r = rows(body)
    assert body["run"]["state"] == "completed_with_issues" and r["gone_3"]["state"] == "ELIMINADO" and r["gone_3"]["volumes"] is None
    assert body["totals"]["previous"]["excluded"] == [{"key": "gone_3", "reason": "single_failed"}]


def test_singles_are_reused_by_content_hash(env):
    client, _, log = env
    prev, curr = standard(client)
    run(client, prev, curr)
    done = len(log.read_text().split())
    run(client, prev, curr)
    assert len(log.read_text().split()) == done
