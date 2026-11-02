from pathlib import Path

import pytest

from solids.domain.inventory import Inventory
from solids.domain.matching import match_inventories
from solids.infrastructure.files import scan_obj_folder

ROOT = Path(__file__).resolve().parents[3] / "docs" / "Pruebas"
PREV, CURR = ROOT / "2025-Prueba", ROOT / "2026-Prueba"

pytestmark = pytest.mark.skipif(not PREV.is_dir() or not CURR.is_dir(), reason="pilot samples not present")


def test_pilot_inventory_matches_documented_counts():
    prev = Inventory.from_entries(scan_obj_folder(PREV), closed=True)
    curr = Inventory.from_entries(scan_obj_folder(CURR), closed=True)
    assert (len(prev.entries), len(curr.entries)) == (28, 32)

    result = match_inventories(prev, curr)

    assert len(result.pairs) == 26
    assert sorted(e.key for e in result.only_current) == [
        "wf_am2_3", "wf_am4_3", "wf_exito25_3", "wf_exito3_3", "wf_exitoe_3", "wf_exitof_3",
    ]
    assert sorted(e.key for e in result.only_previous) == ["wf_amsk1_3", "wf_exito_3"]
    assert result.incidents == ()


def test_pilot_through_the_api(tmp_path):
    from fastapi.testclient import TestClient

    from solids.api.app import create_app

    client = TestClient(create_app(tmp_path / "data"))
    ids = {}
    for label, folder in (("2025", PREV), ("2026", CURR)):
        ds = client.post(
            "/api/v1/datasets", json={"name": "Piloto", "period_label": label, "period_kind": "annual", "is_demo": True}
        ).json()
        for path in sorted(folder.glob("*.obj")):
            with path.open("rb") as handle:
                assert client.post(f"/api/v1/datasets/{ds['id']}/files", files={"file": (path.name, handle)}).status_code == 201
        assert client.post(f"/api/v1/datasets/{ds['id']}/finalize").status_code == 200
        ids[label] = ds["id"]

    body = client.get("/api/v1/matches", params={"previous": ids["2025"], "current": ids["2026"]}).json()
    assert (len(body["pairs"]), len(body["only_current"]), len(body["only_previous"])) == (26, 6, 2)
