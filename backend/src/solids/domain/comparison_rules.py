"""Explainable classification of one pair of solids (Part 2).

Pure rules: metrics in, decision out. Every threshold test is kept in ``checks``
with the observed value, the threshold and the result, so a classification can be
explained (RC-12). Missing indispensable metrics never become a geological state:
the state stays ``None`` and an incident explains why (RF-67).
Thresholds are the provisional working values of the pilot (requirements §6.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

PROFILE_ID = "pilot-v1-provisional"
REQUIRED = ("iou_pct", "delta_volume_sym_pct", "added_pct", "removed_pct", "p95_m", "centroid_m")


@dataclass(frozen=True)
class Profile:
    id: str = PROFILE_ID
    # practically identical
    id_iou_min: float = 99.90
    id_dv_max: float = 0.10
    id_p95_max: float = 0.10
    id_centroid_max: float = 0.10
    id_orientation_max: float = 0.20
    # non-significant change
    ns_iou_min: float = 90.0
    ns_dv_max: float = 7.0
    ns_added_max: float = 10.0
    ns_removed_max: float = 10.0
    ns_p95_max: float = 2.5
    ns_centroid_max: float = 2.5
    ns_azimuth_lt: float = 2.0
    ns_dip_lt: float = 2.0
    ns_local_max: float = 5.0
    # events
    clip_min_pct: float = 5.0
    clip_gap_pts: float = 4.0
    abrupt_iou_max: float = 70.0
    abrupt_nocoinc_min: float = 30.0
    abrupt_dv_min: float = 30.0


def _check(rule: str, group: str, observed, op: str, threshold, applicable: bool = True) -> dict[str, Any]:
    if not applicable:
        passed = True
    elif op == ">=":
        passed = observed >= threshold
    elif op == "<=":
        passed = observed <= threshold
    elif op == "<":
        passed = observed < threshold
    else:
        raise ValueError(op)
    return {"rule": rule, "group": group, "observed": observed, "op": op, "threshold": threshold,
            "passed": bool(passed), "applicable": applicable}


def _orientation_checks(group: str, orientation: Mapping[str, Any], p: Profile) -> list[dict[str, Any]]:
    if orientation.get("comparable"):
        if group == "identico":
            angle = orientation.get("angle_deg")
            return [_check("orientacion", group, angle, "<=", p.id_orientation_max, angle is not None)]
        out = []
        for rule, key, limit in (("delta_azimuth", "delta_azimuth_deg", p.ns_azimuth_lt), ("delta_dip", "delta_dip_deg", p.ns_dip_lt)):
            value = orientation.get(key)
            out.append(_check(rule, group, value, "<", limit, value is not None))
        return out
    if orientation.get("reason") == "different_orientation_type":
        return [{"rule": "orientacion", "group": group, "observed": "tipos distintos", "op": "==", "threshold": "mismo tipo",
                 "passed": False, "applicable": True}]
    return [_check("orientacion", group, None, "<=", None, applicable=False)]  # not interpretable: not applicable


def classify_pair(m: Mapping[str, Any], profile: Profile = Profile()) -> dict[str, Any]:
    p = profile
    missing = [name for name in REQUIRED if m.get(name) is None]
    if missing:
        return {
            "state": None, "subtype": None, "events": [], "checks": [], "profile": p.id,
            "incidents": [{"code": "missing_metric", "metric": name} for name in missing],
            "description": f"No se pudo clasificar: faltan métricas indispensables ({', '.join(missing)}).",
        }

    iou, dv, added, removed = m["iou_pct"], m["delta_volume_sym_pct"], m["added_pct"], m["removed_pct"]
    p95, centroid = m["p95_m"], m["centroid_m"]
    nocoinc = m.get("no_coincidence_pct")
    orientation = m.get("orientation") or {"comparable": False, "reason": "not_interpretable"}
    local = m.get("local_change_deg")

    checks = [
        _check("iou", "identico", iou, ">=", p.id_iou_min), _check("delta_volumen", "identico", dv, "<=", p.id_dv_max),
        _check("p95", "identico", p95, "<=", p.id_p95_max), _check("centroide", "identico", centroid, "<=", p.id_centroid_max),
        *_orientation_checks("identico", orientation, p),
        _check("iou", "no_significativo", iou, ">=", p.ns_iou_min), _check("delta_volumen", "no_significativo", dv, "<=", p.ns_dv_max),
        _check("agregado", "no_significativo", added, "<=", p.ns_added_max), _check("removido", "no_significativo", removed, "<=", p.ns_removed_max),
        _check("p95", "no_significativo", p95, "<=", p.ns_p95_max), _check("centroide", "no_significativo", centroid, "<=", p.ns_centroid_max),
        *_orientation_checks("no_significativo", orientation, p),
        _check("cambio_local", "no_significativo", local, "<=", p.ns_local_max, local is not None),
    ]

    events: list[dict[str, str]] = []

    def add(code: str, text: str) -> None:
        events.append({"code": code, "text": text})

    if removed >= p.clip_min_pct and removed - added > p.clip_gap_pts:
        add("RECORTE", f"RECORTE: se eliminó parte del sólido (volumen removido {removed:.1f} % del anterior; agregado {added:.1f} % del actual).")
    if added >= p.clip_min_pct and added - removed > p.clip_gap_pts:
        add("EXTENSION", f"EXTENSIÓN: el sólido se prolongó (volumen agregado {added:.1f} % del actual; removido {removed:.1f} % del anterior).")
    if centroid > p.ns_centroid_max and dv <= p.ns_dv_max and iou < p.ns_iou_min:
        add("TRASLACION", f"TRASLACIÓN: el centro se desplazó {centroid:.1f} m con volumen casi igual (IoU {iou:.1f} %).")
    if iou < p.abrupt_iou_max and ((nocoinc or 0) >= p.abrupt_nocoinc_min or dv >= p.abrupt_dv_min):
        extra = f" y no coincidencia {nocoinc:.1f} %" if nocoinc is not None else ""
        add("CAMBIO_BRUSCO", f"CAMBIO BRUSCO: IoU {iou:.1f} %{extra}.")
    if orientation.get("comparable"):
        daz, ddip = orientation.get("delta_azimuth_deg"), orientation.get("delta_dip_deg")
        if (daz is not None and daz >= p.ns_azimuth_lt) or (ddip is not None and ddip >= p.ns_dip_lt):
            parts = []
            if daz is not None:
                parts.append(f"Δazimuth {daz:.1f}°")
            if ddip is not None:
                parts.append(f"Δdip {ddip:.1f}°")
            add("CAMBIO_ORIENTACION", f"CAMBIO DE ORIENTACIÓN: {', '.join(parts)}.")
    elif orientation.get("reason") == "different_orientation_type":
        add("CAMBIO_ORIENTACION", "CAMBIO DE ORIENTACIÓN: cambió el tipo de orientación (planar/axial).")
    if local is not None and local > p.ns_local_max:
        add("CAMBIO_CURVATURA", f"CAMBIO DE CURVATURA: cambio local de {local:.1f}°.")
    prev_c, curr_c = m.get("components_prev"), m.get("components_curr")
    if prev_c is not None and curr_c is not None and int(prev_c) != int(curr_c):
        add("FRAGMENTACION_UNION", f"FRAGMENTACIÓN / UNIÓN: {int(prev_c)} → {int(curr_c)} partes.")
    explained = {e["code"] for e in events} & {"RECORTE", "EXTENSION", "TRASLACION", "CAMBIO_BRUSCO"}
    if (iou < p.ns_iou_min or p95 > p.ns_p95_max) and not explained:
        add("CAMBIO_GEOMETRICO", f"CAMBIO GEOMÉTRICO: IoU {iou:.1f} %, distancia P95 {p95:.1f} m.")

    blockers = {e["code"] for e in events} & {"RECORTE", "EXTENSION", "FRAGMENTACION_UNION"}  # RF-69: never hidden as non-significant
    identical = all(c["passed"] for c in checks if c["group"] == "identico")
    non_significant = all(c["passed"] for c in checks if c["group"] == "no_significativo")

    if not blockers and identical:
        state, subtype = "SIN CAMBIOS", "IDENTICO"
        description = f"SIN CAMBIO: coincidencia prácticamente total (IoU {iou:.2f} %)."
    elif not blockers and non_significant:
        state, subtype = "SIN CAMBIOS", "CAMBIO NO SIGNIFICATIVO"
        change = m.get("delta_volume_pct")
        volume = f"{change:+.1f} %" if change is not None else f"{dv:.1f} %"
        description = (f"CAMBIO NO SIGNIFICATIVO: IoU {iou:.1f} %, variación de volumen {volume}, "
                       f"distancia P95 {p95:.1f} m, desplazamiento del centro {centroid:.1f} m.")
    else:
        state, subtype = "VARIABLE", "VARIABLE"
        if not events:  # a threshold failed without a named event
            failed = [f"{c['rule']} {c['observed']}" for c in checks if c["group"] == "no_significativo" and not c["passed"]]
            add("CAMBIO_GEOMETRICO", f"CAMBIO GEOMÉTRICO: fuera de tolerancia en {', '.join(failed)}.")
        description = " ".join(e["text"] for e in events)

    return {"state": state, "subtype": subtype, "events": events, "checks": checks, "incidents": [],
            "profile": p.id, "description": description}
