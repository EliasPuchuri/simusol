"""revisiones_area.csv: the area's opinions, with the context the system showed when each was given."""

from __future__ import annotations

import csv
import io

from .safe import text_cell

COLUMNS = (
    "Periodo_anterior", "Periodo_actual", "Cuerpo", "Estado_sistema", "Subtipo_sistema", "Descripcion_sistema",
    "De_acuerdo", "Estado_esperado", "Tipo_cuerpo_esperado", "Azimuth_esperado", "Dip_esperado", "Comentario",
    "Revisor", "Fecha", "Perfil",
)


def _b(value) -> str:
    return "" if value is None else str(value)


def review_csv(previous_label: str, current_label: str, reviews: list[dict]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for r in reviews:
        writer.writerow([
            text_cell(previous_label), text_cell(current_label), "(observación general)" if r["key"] == "*" else text_cell(r["key"]),
            _b(r["system_state"]), _b(r["system_subtype"]), text_cell(_b(r["system_description"])),
            "si" if r["agrees"] else "no", _b(r["expected_state"]), _b(r["expected_body_type"]),
            _b(r["expected_azimuth"]), _b(r["expected_dip"]), text_cell(r["comment"]), text_cell(r["reviewer"]), r["updated_at"], _b(r["profile"]),
        ])
    return ("﻿" + out.getvalue()).encode("utf-8")
