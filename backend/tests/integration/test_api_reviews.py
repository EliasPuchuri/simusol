import time

import pytest
from fastapi.testclient import TestClient

from solids.api.app import create_app
from support.meshes import cube, obj_bytes

QC, CHAR, CMP = "support.qc_fakes:analyze", "support.qc_fakes:characterize", "support.qc_fakes:compare"
U = (367_800.0, 8_827_600.0, 3_300.0)


@pytest.fixture
def env(tmp_path):
    app = create_app(tmp_path / "data", qc_target=QC, char_target=CHAR, compare_target=CMP, compare_timeout=20.0)
    with TestClient(app) as client:
        yield client, tmp_path


def period(client, label, files, close=True):
    d = client.post("/api/v1/datasets", json={"name": "M", "period_label": label, "period_kind": "annual"}).json()
    for name, content in files.items():
        assert client.post(f"/api/v1/datasets/{d['id']}/files", files={"file": (name, content)}).status_code == 201
    if close:
        client.post(f"/api/v1/datasets/{d['id']}/finalize")
    return d["id"]


def pair(client):
    prev = period(client, "2025", {"a_3pt.obj": obj_bytes(cube(U)), "old_3pt.obj": obj_bytes(cube(U, 7))})
    curr = period(client, "2026", {"a_3.obj": obj_bytes(cube((U[0] + 8, U[1], U[2]))), "new_3.obj": obj_bytes(cube(U, 9))})
    client.post("/api/v1/comparisons", json={"previous": prev, "current": curr})
    for _ in range(100):
        b = client.get("/api/v1/comparisons", params={"previous": prev, "current": curr}).json()
        if b["run"] and b["run"]["state"] in ("completed", "completed_with_issues"):
            break
        time.sleep(0.2)
    return prev, curr


def put(client, prev, curr, key="a_3", **over):
    body = {"previous": prev, "current": curr, "key": key, "reviewer": "Ingeniera", "agrees": True, **over}
    return client.put("/api/v1/comparisons/reviews", json=body)


def listing(client, prev, curr, **extra):
    return client.get("/api/v1/comparisons/reviews", params={"previous": prev, "current": curr, **extra}).json()["reviews"]


def test_an_agreement_is_stored_with_what_the_system_showed_at_that_moment(env):
    client, _ = env
    prev, curr = pair(client)
    r = put(client, prev, curr, comment="Correcto")
    assert r.status_code == 200
    (review,) = listing(client, prev, curr)
    assert review["agrees"] is True and review["reviewer"] == "Ingeniera" and review["comment"] == "Correcto"
    assert review["system_state"] == "VARIABLE" and "TRASLACIÓN" in review["system_description"]
    assert review["profile"] == "pilot-v1-provisional" and review["created_at"]


def test_a_disagreement_carries_the_expected_state_type_and_orientation(env):
    client, _ = env
    prev, curr = pair(client)
    r = put(client, prev, curr, agrees=False, expected_state="SIN CAMBIOS", expected_body_type="TABULAR CURVO",
            expected_azimuth=120.5, expected_dip=30, comment="Es el mismo cuerpo, solo se movió el modelo")
    assert r.status_code == 200
    (review,) = listing(client, prev, curr)
    assert (review["agrees"], review["expected_state"], review["expected_body_type"]) == (False, "SIN CAMBIOS", "TABULAR CURVO")
    assert (review["expected_azimuth"], review["expected_dip"]) == (120.5, 30.0)


@pytest.mark.parametrize("over", [
    {"agrees": False},                                                 # says nothing about what was expected
    {"agrees": False, "expected_state": "QUIZAS"},                     # not one of the four states
    {"agrees": False, "expected_body_type": "REDONDO"},
    {"agrees": False, "expected_azimuth": 400.0},
    {"agrees": False, "expected_dip": 95.0},
    {"comment": "x" * 2001},
    {"reviewer": ""},
])
def test_invalid_reviews_are_rejected(env, over):
    client, _ = env
    prev, curr = pair(client)
    assert put(client, prev, curr, **over).status_code == 422


def test_the_solid_must_exist_and_both_periods_must_be_closed(env):
    client, _ = env
    prev, curr = pair(client)
    assert put(client, prev, curr, key="nope").status_code == 404
    still_open = period(client, "2027", {"a.obj": obj_bytes(cube(U))}, close=False)
    assert put(client, prev, still_open).status_code == 409
    assert put(client, prev, prev).status_code == 422


def test_new_and_removed_solids_can_be_reviewed_too(env):
    client, _ = env
    prev, curr = pair(client)
    assert put(client, prev, curr, key="new_3", agrees=False, expected_state="VARIABLE", comment="Es el mismo, lo renombraron").status_code == 200
    assert {r["key"] for r in listing(client, prev, curr)} == {"new_3"}


def test_the_same_reviewer_replaces_their_opinion_and_others_are_kept_apart(env):
    client, _ = env
    prev, curr = pair(client)
    put(client, prev, curr, comment="primera")
    put(client, prev, curr, comment="segunda")
    put(client, prev, curr, reviewer="Otra persona", comment="otra opinión")
    both = listing(client, prev, curr)
    assert sorted((r["reviewer"], r["comment"]) for r in both) == [("Ingeniera", "segunda"), ("Otra persona", "otra opinión")]
    assert [r["comment"] for r in listing(client, prev, curr, reviewer="Ingeniera")] == ["segunda"]


def test_a_general_observation_about_the_whole_comparison_is_allowed(env):
    client, _ = env
    prev, curr = pair(client)
    assert put(client, prev, curr, key="*", comment="Los umbrales de curvatura parecen bajos").status_code == 200
    assert listing(client, prev, curr)[0]["key"] == "*"


def test_csv_of_reviews_has_context_and_is_excel_friendly(env):
    client, _ = env
    prev, curr = pair(client)
    put(client, prev, curr, agrees=False, expected_state="SIN CAMBIOS", comment="Mismo cuerpo; ñandú")
    r = client.get("/api/v1/comparisons/reviews.csv", params={"previous": prev, "current": curr})
    assert r.status_code == 200 and "revisiones_area.csv" in r.headers["content-disposition"] and r.content.startswith(b"\xef\xbb\xbf")
    import csv, io
    header, row = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
    rec = dict(zip(header, row))
    assert (rec["Cuerpo"], rec["Periodo_anterior"], rec["Periodo_actual"], rec["Revisor"]) == ("a_3", "2025", "2026", "Ingeniera")
    assert (rec["Estado_sistema"], rec["De_acuerdo"], rec["Estado_esperado"]) == ("VARIABLE", "no", "SIN CAMBIOS")
    assert "ñandú" in rec["Comentario"] and rec["Perfil"] == "pilot-v1-provisional"


def test_archiving_hides_a_period_but_keeps_everything_and_can_be_undone(env):
    client, tmp_path = env
    prev, curr = pair(client)
    files_before = sorted(p.name for p in (tmp_path / "data" / "originals").glob("*.obj"))
    assert client.post(f"/api/v1/datasets/{prev}/archive").status_code == 200
    assert prev not in [d["id"] for d in client.get("/api/v1/datasets").json()]
    assert prev in [d["id"] for d in client.get("/api/v1/datasets", params={"include_archived": "true"}).json()]
    assert client.get(f"/api/v1/datasets/{prev}").json()["archived"] is True            # still readable
    assert sorted(p.name for p in (tmp_path / "data" / "originals").glob("*.obj")) == files_before  # nothing deleted
    assert client.post(f"/api/v1/datasets/{prev}/files", files={"file": ("x.obj", obj_bytes(cube(U)))}).status_code == 409
    assert client.post(f"/api/v1/datasets/{prev}/restore").status_code == 200
    assert prev in [d["id"] for d in client.get("/api/v1/datasets").json()]
    assert client.post("/api/v1/datasets/nope/archive").status_code == 404
