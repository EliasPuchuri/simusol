"""reporte_parte1.csv: one row per solid of one period. Serialization is provisional (plan P00.5)."""

from __future__ import annotations

import csv
import io

COLUMNS = (
    "Periodo", "Archivo", "Clave", "Estado_tecnico", "Tipo_cuerpo", "Lambda1", "Lambda2", "Lambda3",
    "Tipo_orientacion", "Azimuth", "Dip", "Volumen_m3", "Volumen_motivo", "Observaciones",
    "Ref_Metodo", "Ref_Azimuth", "Ref_Dip", "Delta_Azimuth", "Delta_Dip",
)


def _blank(value) -> str:
    return "" if value is None else str(value)


def characterization_csv(period_label: str, rows: list[dict]) -> bytes:
    """UTF-8 with BOM, ';' separator, '.' decimals. Missing values stay empty: never 0."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for row in rows:
        r = row.get("result") or {}
        orientation = r.get("orientation") or {}
        volume = row.get("volume") or {}
        reference = row.get("reference") or {}
        comparison = reference.get("comparison") or {}
        eigenvalues = r.get("eigenvalues") or [None, None, None]
        notes = [x for x in (orientation.get("reason"), orientation.get("note"), r.get("error")) if x]
        writer.writerow([
            period_label, row["filename"], row["key"], r.get("status", "pending"), _blank(r.get("body_type")),
            *[_blank(v) for v in eigenvalues], _blank(orientation.get("type")),
            _blank(orientation.get("azimuth")), _blank(orientation.get("dip")),
            _blank(volume.get("value")), _blank(volume.get("reason")), "; ".join(notes),
            _blank(reference.get("method")), _blank(reference.get("azimuth")), _blank(reference.get("dip")),
            _blank(comparison.get("delta_azimuth_deg")), _blank(comparison.get("delta_dip_deg")),
        ])
    return ("﻿" + out.getvalue()).encode("utf-8")
