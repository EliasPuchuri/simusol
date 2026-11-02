"""reporte_parte0.csv: one row per solid of one period. Serialization is provisional (see plan P00.5)."""

from __future__ import annotations

import csv
import io

from .safe import text_cell

COLUMNS = (
    "Periodo", "Archivo", "Clave", "Estado_tecnico", "Volumen_firmado_m3", "Volumen_m3", "Volumen_motivo",
    "Cerrado", "Bordes_abiertos", "Aristas_no_manifold", "Winding_consistente", "Orientacion",
    "Vertices_duplicados", "Caras_duplicadas", "Caras_degeneradas", "Componentes", "Autointersecciones",
    "Problemas", "Superposicion_con_otros_cuerpos", "Observaciones",
)


def _yes_no(value) -> str:
    return "" if value is None else ("si" if value else "no")


def _blank(value) -> str:
    return "" if value is None else str(value)


def qc_csv(period_label: str, rows: list[dict]) -> bytes:
    """UTF-8 with BOM, ';' separator, '.' decimals. Unavailable values stay empty: never 0."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for row in rows:
        result = row.get("result") or {}
        volume = result.get("volume_m3") or {}
        components = result.get("components") or {}
        self_int = result.get("self_intersections") or {}
        writer.writerow([
            text_cell(period_label), text_cell(row["filename"]), text_cell(row["key"]), result.get("status", "pending"),
            _blank(result.get("signed_volume_m3")), _blank(volume.get("value")), _blank(volume.get("reason")),
            _yes_no(result.get("watertight")), _blank(result.get("open_edges")), _blank(result.get("non_manifold_edges")),
            _yes_no(result.get("winding_consistent")), result.get("orientation", ""),
            _blank(result.get("duplicate_vertices")), _blank(result.get("duplicate_faces")),
            _blank(result.get("degenerate_faces")),
            _blank(None if components.get("value") is None else int(components["value"])),
            _blank(None if self_int.get("value") is None else int(self_int["value"])),
            "; ".join(result.get("problems", [])), "no_evaluada", text_cell(_blank(result.get("error"))),
        ])
    return ("﻿" + out.getvalue()).encode("utf-8")
