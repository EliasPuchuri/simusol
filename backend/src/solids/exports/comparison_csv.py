"""reporte_parte2.csv: one row per pair or per solid present in only one period (provisional serialization)."""

from __future__ import annotations

import csv
import io

COLUMNS = (
    "Cuerpo", "Mesh_anterior", "Mesh_actual", "Periodo_anterior", "Periodo_actual",
    "Tipo_cuerpo_anterior", "Tipo_cuerpo_actual", "Tipo_orientacion_anterior", "Tipo_orientacion_actual",
    "V_anterior_m3", "V_actual_m3", "Azimuth_anterior", "Dip_anterior", "Azimuth_actual", "Dip_actual",
    "Delta_Azimuth", "Delta_Dip", "Interseccion_m3", "IoU_pct", "No_coincidencia_pct", "Delta_volumen_pct",
    "Delta_volumen_sim_pct", "Volumen_agregado_pct", "Volumen_removido_pct", "Agregado_m3", "Removido_m3",
    "Distancia_P95_m", "Delta_centroide_m", "Cambio_local_P95_deg", "Estado", "Subtipo", "Descripcion",
    "Estado_tecnico", "Volumen_provisional", "Perfil", "Observaciones",
)


def _b(value) -> str:
    return "" if value is None else str(value)


def comparison_csv(previous_label: str, current_label: str, rows: list[dict]) -> bytes:
    """UTF-8 with BOM, ';' separator, '.' decimals. Metrics that do not apply or failed stay empty: never 0."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for r in rows:
        m, v = r.get("metrics") or {}, r.get("volumes") or {}
        chars = r.get("characterization") or {}
        cp, cc = chars.get("previous") or {}, chars.get("current") or {}
        op, oc = cp.get("orientation") or {}, cc.get("orientation") or {}
        cmp_ = r.get("orientation_comparison") or {}
        notes = list(r.get("warnings", [])) + [i.get("code", "") + (f":{i['metric']}" if i.get("metric") else "") for i in r.get("incidents", [])]
        notes += [f"{k}={x}" for k, x in (r.get("reasons") or {}).items()]
        if r.get("error"):
            notes.append(r["error"])
        writer.writerow([
            r["key"], _b(r.get("previous_filename")), _b(r.get("current_filename")),
            previous_label if r.get("previous_filename") else "", current_label if r.get("current_filename") else "",
            _b(cp.get("body_type")), _b(cc.get("body_type")), _b(op.get("type")), _b(oc.get("type")),
            _b(v.get("previous_m3")), _b(v.get("current_m3")), _b(op.get("azimuth")), _b(op.get("dip")),
            _b(oc.get("azimuth")), _b(oc.get("dip")), _b(cmp_.get("delta_azimuth_deg")), _b(cmp_.get("delta_dip_deg")),
            _b(v.get("intersection_m3")), _b(m.get("iou_pct")), _b(m.get("no_coincidence_pct")), _b(m.get("delta_volume_pct")),
            _b(m.get("delta_volume_sym_pct")), _b(m.get("added_pct")), _b(m.get("removed_pct")),
            _b(v.get("added_m3")), _b(v.get("removed_m3")), _b(m.get("p95_m")), _b(m.get("centroid_m")),
            _b(m.get("local_change_deg") if r.get("local_applicable") else None),
            _b(r.get("state")), _b(r.get("subtype")), r.get("description", ""), r.get("technical_status", ""),
            "si" if r.get("provisional") else "", _b(r.get("profile")), "; ".join(n for n in notes if n),
        ])
    return ("﻿" + out.getvalue()).encode("utf-8")
