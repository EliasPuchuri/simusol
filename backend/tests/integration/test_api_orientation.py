import pytest
from fastapi.testclient import TestClient

from solids.api.app import create_app

OBJ = b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
HEAD = "archivo;tipo_orientacion;azimuth_grados;dip_grados;metodo;origen;observaciones"
GOOD = f"{HEAD}\nwf_a_3pt.obj;planar;45,5;60;Studio RM;;\nwf_b_3.obj;axial;225;10;Leapfrog;;\n"


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path / "data", max_file_bytes=1024))


def dataset(client, with_files=("wf_a_3pt.obj",)):
    d = client.post("/api/v1/datasets", json={"name": "M", "period_label": "2025", "period_kind": "annual"}).json()
    for name in with_files:
        client.post(f"/api/v1/datasets/{d['id']}/files", files={"file": (name, OBJ)})
    return d


def send(client, dataset_id, body: str | bytes, name="ref.csv"):
    data = body.encode() if isinstance(body, str) else body
    return client.post(f"/api/v1/datasets/{dataset_id}/orientation-reference", files={"file": (name, data)})


def test_template_is_downloadable_as_csv_attachment(client):
    r = client.get("/api/v1/templates/orientation-reference")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"] and ".csv" in r.headers["content-disposition"]
    assert r.content.startswith(b"\xef\xbb\xbf") and b"azimuth_grados" in r.content


def test_valid_upload_is_saved_and_reported(client):
    d = dataset(client)
    r = send(client, d["id"], GOOD)
    assert r.status_code == 200
    body = r.json()
    assert body["saved"] == 2 and body["ignored_examples"] == 0
    assert [w["code"] for w in body["warnings"]] == ["not_in_dataset"]  # wf_b_3 is not in the period
    rows = client.get(f"/api/v1/datasets/{d['id']}/orientation-reference").json()["rows"]
    assert [(x["filename"], x["orientation_type"], x["azimuth"], x["dip"]) for x in rows] == [
        ("wf_a_3pt.obj", "planar", 45.5, 60.0), ("wf_b_3.obj", "axial", 225.0, 10.0)]


def test_invalid_upload_returns_every_issue_and_saves_nothing(client):
    d = dataset(client)
    send(client, d["id"], GOOD)
    bad = f"{HEAD}\nwf_a_3pt.obj;planar;400;60;Studio RM;;\nwf_b_3.obj;oblicuo;1;2;Studio RM;;\n"
    r = send(client, d["id"], bad)
    assert r.status_code == 422
    errors = r.json()["detail"]["errors"]
    assert [(e["code"], e["line"]) for e in errors] == [("azimuth_range", 2), ("bad_type", 3)]
    assert len(client.get(f"/api/v1/datasets/{d['id']}/orientation-reference").json()["rows"]) == 2  # untouched


def test_second_valid_upload_replaces_the_table(client):
    d = dataset(client)
    send(client, d["id"], GOOD)
    send(client, d["id"], f"{HEAD}\nwf_a_3.obj;planar;1;2;Studio RM;;\n")
    rows = client.get(f"/api/v1/datasets/{d['id']}/orientation-reference").json()["rows"]
    assert [x["filename"] for x in rows] == ["wf_a_3.obj"]


def test_untouched_template_is_rejected_with_a_clear_code(client):
    d = dataset(client)
    r = send(client, d["id"], client.get("/api/v1/templates/orientation-reference").content)
    assert r.status_code == 422
    assert [e["code"] for e in r.json()["detail"]["errors"]] == ["no_rows"]
    assert r.json()["detail"]["ignored_examples"] >= 3


def test_detail_exposes_the_reference_count_and_closed_periods_accept_it(client):
    d = dataset(client)
    assert client.get(f"/api/v1/datasets/{d['id']}").json()["orientation_reference_count"] == 0
    client.post(f"/api/v1/datasets/{d['id']}/finalize")
    assert send(client, d["id"], GOOD).status_code == 200
    assert client.get(f"/api/v1/datasets/{d['id']}").json()["orientation_reference_count"] == 2


def test_unknown_dataset_and_oversized_file(client):
    assert send(client, "nope", GOOD).status_code == 404
    assert client.get("/api/v1/datasets/nope/orientation-reference").status_code == 404
    d = dataset(client)
    assert send(client, d["id"], "x" * (1024 * 1024 + 1)).status_code == 413
