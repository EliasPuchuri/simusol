import csv
import io
import time

import pytest
from fastapi.testclient import TestClient

from solids.api.app import create_app
from support.meshes import cube, obj_bytes

QC, CHAR, CMP, SINGLE = "support.qc_fakes:analyze", "support.qc_fakes:characterize", "support.qc_fakes:compare", "support.qc_fakes:single"
U = (367_800.0, 8_827_600.0, 3_300.0)
DONE = {"completed", "completed_with_issues", "failed"}


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "data", qc_target=QC, char_target=CHAR, compare_target=CMP, single_target=SINGLE, compare_timeout=20.0)
    with TestClient(app) as c:
        yield c


def cells(response, column):
    text = response.content.decode("utf-8-sig")
    header, *rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    return [dict(zip(header, r))[column] for r in rows]


def wait(client, url, params=None, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        body = client.get(url, params=params).json()
        if body["run"] and body["run"]["state"] in DONE:
            return
        time.sleep(0.2)
    raise AssertionError("run did not finish")


def test_a_hostile_file_name_or_label_never_reaches_a_spreadsheet_as_a_formula(client):
    mk = lambda label: client.post("/api/v1/datasets", json={"name": "M", "period_label": label, "period_kind": "annual"}).json()["id"]
    prev, curr = mk("=2025"), mk("@2026")
    for ds, name in ((prev, "=evil_3pt.obj"), (curr, "=evil_3.obj")):
        client.post(f"/api/v1/datasets/{ds}/files", files={"file": (name, obj_bytes(cube(U)))})
        client.post(f"/api/v1/datasets/{ds}/finalize")

    client.post(f"/api/v1/datasets/{prev}/qc")
    wait(client, f"/api/v1/datasets/{prev}/qc")
    client.post(f"/api/v1/datasets/{prev}/characterization")
    wait(client, f"/api/v1/datasets/{prev}/characterization")
    client.post("/api/v1/comparisons", json={"previous": prev, "current": curr})
    wait(client, "/api/v1/comparisons", {"previous": prev, "current": curr})
    client.put("/api/v1/comparisons/reviews", json={"previous": prev, "current": curr, "key": "=evil_3", "reviewer": "+boss", "agrees": True, "comment": "=1+1"})

    checks = [
        (client.get(f"/api/v1/datasets/{prev}/qc.csv"), ["Periodo", "Archivo", "Clave"]),
        (client.get(f"/api/v1/datasets/{prev}/characterization.csv"), ["Periodo", "Archivo", "Clave"]),
        (client.get("/api/v1/comparisons/report.csv", params={"previous": prev, "current": curr}), ["Cuerpo", "Mesh_anterior", "Mesh_actual", "Periodo_anterior", "Periodo_actual"]),
        (client.get("/api/v1/comparisons/reviews.csv", params={"previous": prev, "current": curr}), ["Cuerpo", "Revisor", "Comentario", "Periodo_anterior", "Periodo_actual"]),
    ]
    for response, columns in checks:
        assert response.status_code == 200
        for column in columns:
            for value in cells(response, column):
                assert not value.startswith(("=", "+", "-", "@")), (response.url, column, value)
