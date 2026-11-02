import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from solids.api.app import create_app

OBJ = b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"


@pytest.fixture
def env(tmp_path):
    app = create_app(tmp_path / "data", max_file_bytes=1024)
    return TestClient(app), tmp_path / "data"


def new_dataset(client, label="2025", **extra):
    body = {"name": "Piloto", "period_label": label, "period_kind": "annual", **extra}
    r = client.post("/api/v1/datasets", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def upload(client, dataset_id, filename, content=OBJ):
    return client.post(
        f"/api/v1/datasets/{dataset_id}/files", files={"file": (filename, content)}
    )


def test_create_dataset_starts_open_with_revision_one_and_null_spatial_ref(env):
    client, _ = env
    d = new_dataset(client)
    assert d["state"] == "open" and d["revision"] == 1
    assert d["spatial_reference"] is None and d["units"] is None


def test_same_name_and_period_gets_next_revision(env):
    client, _ = env
    new_dataset(client)
    assert new_dataset(client)["revision"] == 2
    assert new_dataset(client, label="2026")["revision"] == 1


def test_invalid_period_kind_is_rejected(env):
    client, _ = env
    r = client.post("/api/v1/datasets", json={"name": "x", "period_label": "y", "period_kind": "weekly"})
    assert r.status_code == 422


def test_upload_stores_original_bytes_and_returns_hash_and_key(env):
    client, data = env
    d = new_dataset(client)
    r = upload(client, d["id"], "wf_am1_3pt.obj")
    assert r.status_code == 201
    body = r.json()
    assert body["key"] == "wf_am1_3" and body["filename"] == "wf_am1_3pt.obj"
    assert body["sha256"] == hashlib.sha256(OBJ).hexdigest() and body["size_bytes"] == len(OBJ)
    stored = [p for p in Path(data).rglob("*") if p.is_file() and p.read_bytes() == OBJ]
    assert len(stored) == 1 and "wf_am1_3pt" not in stored[0].name


def test_client_path_is_only_metadata(env):
    client, data = env
    d = new_dataset(client)
    body = upload(client, d["id"], "..\\..\\evil/../a_3pt.obj").json()
    assert body["filename"] == "a_3pt.obj"
    assert not (data.parent / "evil").exists()


@pytest.mark.parametrize(
    "filename,content",
    [("notes.txt", OBJ), ("empty.obj", b""), ("junk.obj", b"\x00\x01binary\x02"), ("novertex.obj", b"f 1 2 3\n")],
)
def test_invalid_uploads_are_rejected_and_not_stored(env, filename, content):
    client, data = env
    d = new_dataset(client)
    assert upload(client, d["id"], filename, content).status_code == 422
    assert client.get(f"/api/v1/datasets/{d['id']}").json()["files"] == []
    assert not [p for p in Path(data).rglob("*.obj") if p.is_file()]


def test_oversized_upload_is_rejected_with_413(env):
    client, _ = env
    d = new_dataset(client)
    assert upload(client, d["id"], "big.obj", OBJ + b"#" * 2048).status_code == 413


def test_duplicate_filename_in_dataset_is_a_conflict(env):
    client, _ = env
    d = new_dataset(client)
    assert upload(client, d["id"], "a.obj").status_code == 201
    assert upload(client, d["id"], "A.OBJ").status_code == 409


def test_finalize_closes_and_blocks_further_uploads(env):
    client, _ = env
    d = new_dataset(client)
    upload(client, d["id"], "a.obj")
    r = client.post(f"/api/v1/datasets/{d['id']}/finalize")
    assert r.status_code == 200 and r.json()["state"] == "closed"
    assert upload(client, d["id"], "b.obj").status_code == 409
    assert client.post(f"/api/v1/datasets/{d['id']}/finalize").status_code == 409


def test_finalize_empty_dataset_is_rejected(env):
    client, _ = env
    d = new_dataset(client)
    assert client.post(f"/api/v1/datasets/{d['id']}/finalize").status_code == 422


def test_detail_reports_duplicate_key_incidents(env):
    client, _ = env
    d = new_dataset(client)
    upload(client, d["id"], "x_3pt.obj")
    upload(client, d["id"], "x_3.obj")
    detail = client.get(f"/api/v1/datasets/{d['id']}").json()
    assert [i["code"] for i in detail["incidents"]] == ["duplicate_key"]
    assert detail["counts"] == {"files": 2, "keys": 1}


def test_unknown_dataset_is_404(env):
    client, _ = env
    assert client.get("/api/v1/datasets/nope").status_code == 404
    assert upload(client, "nope", "a.obj").status_code == 404


def test_list_returns_datasets_with_file_counts(env):
    client, _ = env
    d = new_dataset(client)
    upload(client, d["id"], "a.obj")
    (item,) = client.get("/api/v1/datasets").json()
    assert item["id"] == d["id"] and item["file_count"] == 1


def closed(client, label, names):
    d = new_dataset(client, label=label)
    for n in names:
        upload(client, d["id"], n)
    client.post(f"/api/v1/datasets/{d['id']}/finalize")
    return d


def test_matches_pairs_and_reports_new_and_removed(env):
    client, _ = env
    prev = closed(client, "2025", ["a_3pt.obj", "old.obj"])
    curr = closed(client, "2026", ["a_3.obj", "new.obj"])
    r = client.get("/api/v1/matches", params={"previous": prev["id"], "current": curr["id"]})
    assert r.status_code == 200
    body = r.json()
    assert [(p["previous"]["filename"], p["current"]["filename"]) for p in body["pairs"]] == [("a_3pt.obj", "a_3.obj")]
    assert [e["key"] for e in body["only_previous"]] == ["old"]
    assert [e["key"] for e in body["only_current"]] == ["new"]
    assert body["incidents"] == []


def test_matches_requires_both_revisions_closed(env):
    client, _ = env
    prev = closed(client, "2025", ["a.obj"])
    open_ds = new_dataset(client, label="2026")
    upload(client, open_ds["id"], "a.obj")
    r = client.get("/api/v1/matches", params={"previous": prev["id"], "current": open_ds["id"]})
    assert r.status_code == 409


def test_matches_rejects_same_dataset_and_unknown_ids(env):
    client, _ = env
    prev = closed(client, "2025", ["a.obj"])
    assert client.get("/api/v1/matches", params={"previous": prev["id"], "current": prev["id"]}).status_code == 422
    assert client.get("/api/v1/matches", params={"previous": prev["id"], "current": "nope"}).status_code == 404
