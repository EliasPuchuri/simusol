import pytest

from solids.domain.comparison_rules import PROFILE_ID, classify_pair

SAME_ORIENT = {"comparable": True, "reason": None, "delta_azimuth_deg": 0.0, "delta_dip_deg": 0.0, "angle_deg": 0.0}


def metrics(**over):
    """A practically identical pair; each test overrides what it wants to change."""
    base = {
        "iou_pct": 99.99, "delta_volume_pct": 0.0, "delta_volume_sym_pct": 0.0, "added_pct": 0.01, "removed_pct": 0.01,
        "no_coincidence_pct": 0.01, "p95_m": 0.02, "centroid_m": 0.01, "orientation": dict(SAME_ORIENT),
        "local_change_deg": None, "components_prev": None, "components_curr": None,
    }
    base.update(over)
    return base


def events(r):
    return [e["code"] for e in r["events"]]


def test_practically_identical_pair_has_no_change():
    r = classify_pair(metrics())
    assert r["state"] == "SIN CAMBIOS" and r["subtype"] == "IDENTICO" and r["incidents"] == []
    assert r["description"].startswith("SIN CAMBIO: coincidencia prácticamente total") and r["profile"] == PROFILE_ID


def test_small_difference_is_a_non_significant_change_inside_sin_cambios():
    r = classify_pair(metrics(iou_pct=93.0, delta_volume_sym_pct=2.0, delta_volume_pct=-2.0, added_pct=4.0, removed_pct=3.0, p95_m=0.8, centroid_m=0.4,
                              orientation={**SAME_ORIENT, "delta_azimuth_deg": 1.0, "delta_dip_deg": 0.5, "angle_deg": 1.0}))
    assert r["state"] == "SIN CAMBIOS" and r["subtype"] == "CAMBIO NO SIGNIFICATIVO"
    assert r["description"].startswith("CAMBIO NO SIGNIFICATIVO") and "93.0 %" in r["description"]


def test_a_real_translation_with_same_volume_and_orientation_is_not_sin_cambios():
    r = classify_pair(metrics(iou_pct=60.0, delta_volume_sym_pct=0.5, added_pct=40.0, removed_pct=40.0, p95_m=9.0, centroid_m=12.0, no_coincidence_pct=40.0))
    assert r["state"] == "VARIABLE" and "TRASLACION" in events(r)
    assert "TRASLACIÓN" in r["description"] and "12.0 m" in r["description"]


def test_a_real_clip_is_variable_even_if_the_net_change_looks_small():
    # RC-28: removed 8 %, added 1 %: net volume change inside the 7 % limit, IoU above 90 %
    r = classify_pair(metrics(iou_pct=92.0, delta_volume_sym_pct=6.5, delta_volume_pct=-6.9, added_pct=1.0, removed_pct=8.0, p95_m=1.0, centroid_m=0.5))
    assert r["state"] == "VARIABLE" and events(r) == ["RECORTE"]
    assert "RECORTE: se eliminó parte del sólido" in r["description"] and "8.0 %" in r["description"]


def test_a_real_extension_is_variable():
    r = classify_pair(metrics(iou_pct=91.0, delta_volume_sym_pct=6.0, delta_volume_pct=7.0, added_pct=9.0, removed_pct=1.0, p95_m=1.5, centroid_m=0.6))
    assert r["state"] == "VARIABLE" and "EXTENSION" in events(r) and "EXTENSIÓN: el sólido se prolongó" in r["description"]


def test_compensating_additions_and_removals_do_not_hide_a_geometric_change():
    r = classify_pair(metrics(iou_pct=85.0, delta_volume_sym_pct=0.2, added_pct=8.0, removed_pct=8.0, p95_m=3.1, centroid_m=0.4, no_coincidence_pct=15.0))
    assert r["state"] == "VARIABLE" and "CAMBIO_GEOMETRICO" in events(r) and "RECORTE" not in events(r)


def test_orientation_change_alone_makes_it_variable():
    r = classify_pair(metrics(orientation={**SAME_ORIENT, "delta_azimuth_deg": 5.2, "delta_dip_deg": 1.0, "angle_deg": 5.0}))
    assert r["state"] == "VARIABLE" and events(r) == ["CAMBIO_ORIENTACION"] and "5.2°" in r["description"]


def test_a_change_between_planar_and_axial_is_a_change_not_a_number():
    r = classify_pair(metrics(orientation={"comparable": False, "reason": "different_orientation_type"}))
    assert r["state"] == "VARIABLE" and "CAMBIO_ORIENTACION" in events(r)


def test_not_interpretable_orientation_is_not_applicable_and_does_not_block():
    r = classify_pair(metrics(orientation={"comparable": False, "reason": "not_interpretable"}))
    assert r["state"] == "SIN CAMBIOS"
    assert any(c["rule"] == "orientacion" and c["applicable"] is False for c in r["checks"])


def test_missing_indispensable_metrics_leave_the_state_unassigned_with_an_incident():
    for name in ("iou_pct", "p95_m", "centroid_m", "delta_volume_sym_pct", "added_pct", "removed_pct"):
        r = classify_pair(metrics(**{name: None}))
        assert r["state"] is None, name  # RC-29: a failure is never SIN CAMBIOS or VARIABLE
        assert r["incidents"][0]["code"] == "missing_metric" and r["incidents"][0]["metric"] == name
        assert "No se pudo clasificar" in r["description"]


def test_no_coincidence_is_reported_but_is_not_a_gate():
    assert classify_pair(metrics(no_coincidence_pct=None))["state"] == "SIN CAMBIOS"


@pytest.mark.parametrize("override,state", [
    ({"iou_pct": 90.0, "delta_volume_sym_pct": 1.0, "added_pct": 5.0, "removed_pct": 4.0}, "SIN CAMBIOS"),   # >= 90 passes
    ({"iou_pct": 89.99, "delta_volume_sym_pct": 1.0, "added_pct": 5.0, "removed_pct": 4.0}, "VARIABLE"),
    ({"iou_pct": 95.0, "p95_m": 2.5}, "SIN CAMBIOS"),                                                           # <= 2.5 passes
    ({"iou_pct": 95.0, "p95_m": 2.51}, "VARIABLE"),
    ({"iou_pct": 95.0, "orientation": {**SAME_ORIENT, "delta_azimuth_deg": 1.99, "delta_dip_deg": 1.99, "angle_deg": 1.99}}, "SIN CAMBIOS"),
    ({"iou_pct": 95.0, "orientation": {**SAME_ORIENT, "delta_azimuth_deg": 2.0, "delta_dip_deg": 0.0, "angle_deg": 2.0}}, "VARIABLE"),  # strictly < 2
    ({"iou_pct": 95.0, "delta_volume_sym_pct": 7.0}, "SIN CAMBIOS"),
    ({"iou_pct": 95.0, "delta_volume_sym_pct": 7.01}, "VARIABLE"),
])
def test_threshold_boundaries(override, state):
    base = {"iou_pct": 95.0, "delta_volume_sym_pct": 1.0, "added_pct": 3.0, "removed_pct": 2.0, "p95_m": 1.0, "centroid_m": 1.0}
    assert classify_pair(metrics(**{**base, **override}))["state"] == state


def test_local_curvature_change_and_fragmentation_are_events():
    base = dict(iou_pct=95.0, delta_volume_sym_pct=1.0, added_pct=3.0, removed_pct=2.0, p95_m=1.0, centroid_m=1.0)
    assert classify_pair(metrics(**base, local_change_deg=4.9))["state"] == "SIN CAMBIOS"
    curved = classify_pair(metrics(**base, local_change_deg=8.1))
    assert curved["state"] == "VARIABLE" and events(curved) == ["CAMBIO_CURVATURA"] and "8.1°" in curved["description"]
    split = classify_pair(metrics(**base, components_prev=1, components_curr=3))
    assert split["state"] == "VARIABLE" and "FRAGMENTACION_UNION" in events(split) and "1 → 3" in split["description"]
    assert classify_pair(metrics(**base, components_prev=1, components_curr=None))["state"] == "SIN CAMBIOS"  # unknown, not a change


def test_abrupt_change_is_flagged():
    r = classify_pair(metrics(iou_pct=50.0, delta_volume_sym_pct=10.0, added_pct=45.0, removed_pct=30.0, no_coincidence_pct=40.0, p95_m=14.0, centroid_m=3.0))
    assert r["state"] == "VARIABLE" and "CAMBIO_BRUSCO" in events(r) and "CAMBIO BRUSCO" in r["description"]


def test_every_decision_keeps_observed_value_threshold_and_result():
    r = classify_pair(metrics(iou_pct=93.0, delta_volume_sym_pct=2.0, added_pct=4.0, removed_pct=3.0, p95_m=0.8, centroid_m=0.4))
    iou = next(c for c in r["checks"] if c["rule"] == "iou" and c["group"] == "no_significativo")
    assert iou == {"rule": "iou", "group": "no_significativo", "observed": 93.0, "op": ">=", "threshold": 90.0, "passed": True, "applicable": True}
    assert {c["group"] for c in r["checks"]} == {"identico", "no_significativo"}


def test_description_and_state_always_agree():
    for m in (metrics(), metrics(iou_pct=93.0, delta_volume_sym_pct=2.0, added_pct=4.0, removed_pct=3.0, p95_m=0.8),
              metrics(iou_pct=60.0, p95_m=9.0, centroid_m=12.0, added_pct=40.0, removed_pct=40.0)):
        r = classify_pair(m)
        assert (r["state"] == "SIN CAMBIOS") == (r["description"].startswith(("SIN CAMBIO", "CAMBIO NO SIGNIFICATIVO")))
