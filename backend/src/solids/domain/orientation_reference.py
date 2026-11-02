"""Reference table of orientations measured with the area's manual procedure.

The table is a fillable CSV. Parsing is all-or-nothing: any error means no row
is accepted, and every issue carries the physical line and column so the user
can fix the file. Rows marked as examples are never stored.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from typing import Collection

from .naming import normalize_key

REQUIRED_COLUMNS = ("archivo", "tipo_orientacion", "azimuth_grados", "dip_grados", "metodo")
OPTIONAL_COLUMNS = ("origen", "observaciones")
ORIENTATION_TYPES = ("planar", "axial", "no_interpretable")
MAX_ROWS = 5000


@dataclass(frozen=True)
class Issue:
    code: str
    line: int | None = None
    column: str | None = None
    value: str | None = None


@dataclass(frozen=True)
class ReferenceRow:
    line: int
    filename: str
    key: str
    orientation_type: str
    azimuth: float | None
    dip: float | None
    method: str
    observations: str


@dataclass(frozen=True)
class ParseReport:
    rows: tuple[ReferenceRow, ...]
    errors: tuple[Issue, ...]
    warnings: tuple[Issue, ...]
    ignored_examples: int


def _column(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_name.lower()).strip("_")


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")  # CSV saved by Excel as "ANSI"


def _delimiter(header: str) -> str:
    return max(";,\t", key=header.count)


def _number(text: str) -> float | None:
    try:
        value = float(text.strip().replace(",", "."))
    except ValueError:
        return None
    return value if value == value and abs(value) != float("inf") else None


def template_csv() -> bytes:
    """Downloadable template: instructions, header and clearly fictitious examples."""
    lines = [
        "# PLANTILLA DE ORIENTACIÓN DE REFERENCIA. Las líneas que empiezan con # se ignoran.",
        "# Una fila por sólido, con los valores medidos en Studio RM o Leapfrog. Borra las filas de ejemplo.",
        "# archivo: nombre del .obj (con o sin pt final). tipo_orientacion: planar, axial o no_interpretable.",
        "# azimuth_grados: de 0 a menos de 360. dip_grados: de 0 a 90. Puedes usar coma o punto decimal.",
        "# Si el tipo es no_interpretable deja azimuth y dip vacíos. origen: deja vacío o escribe medido.",
        ";".join((*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS)),
        "ejemplo_veta_a_3pt.obj;planar;45,5;60;Studio RM;ejemplo;Fila de ejemplo: bórrala",
        "ejemplo_veta_b_3.obj;planar;310;75;Leapfrog;ejemplo;Fila de ejemplo: bórrala",
        "ejemplo_cuerpo_c_3.obj;axial;120;25;Studio RM;ejemplo;Cuerpo globular: Trend/Plunge en Azimuth/Dip",
        "ejemplo_cuerpo_d_3.obj;no_interpretable;;;Studio RM;ejemplo;Sin dirección dominante",
    ]
    return ("﻿" + "\r\n".join(lines) + "\r\n").encode("utf-8")


def parse_orientation_reference(raw: bytes, known_keys: Collection[str] | None = None) -> ParseReport:
    errors: list[Issue] = []
    warnings: list[Issue] = []
    rows: list[ReferenceRow] = []
    ignored = 0

    numbered = [
        (number, line)
        for number, line in enumerate(_decode(raw).splitlines(), start=1)
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not numbered or "\x00" in raw.decode("latin-1")[:1024]:
        return ParseReport((), (Issue("empty_file"),), (), 0)

    header_line, header_text = numbered[0]
    delimiter = _delimiter(header_text)
    columns = [_column(c) for c in next(csv.reader([header_text], delimiter=delimiter))]
    for required in REQUIRED_COLUMNS:
        if required not in columns:
            errors.append(Issue("missing_column", header_line, required))
    for name in columns:
        if name and name not in REQUIRED_COLUMNS + OPTIONAL_COLUMNS:
            warnings.append(Issue("unknown_column", header_line, name))
    if errors:
        return ParseReport((), tuple(errors), tuple(warnings), 0)

    index = {name: columns.index(name) for name in REQUIRED_COLUMNS + OPTIONAL_COLUMNS if name in columns}
    seen: dict[str, int] = {}

    for number, text in numbered[1:]:
        cells = next(csv.reader([text], delimiter=delimiter))
        get = lambda name: cells[index[name]].strip() if name in index and index[name] < len(cells) else ""

        if get("origen").lower() in {"ejemplo", "example"}:
            ignored += 1
            continue
        row_errors: list[Issue] = []
        filename = get("archivo")
        if not filename.lower().endswith(".obj"):
            row_errors.append(Issue("not_obj", number, "archivo", filename))
        kind = _column(get("tipo_orientacion"))
        if kind not in ORIENTATION_TYPES:
            row_errors.append(Issue("bad_type", number, "tipo_orientacion", get("tipo_orientacion")))
        if not get("metodo"):
            row_errors.append(Issue("required", number, "metodo"))

        angles: dict[str, float | None] = {}
        for column, low, high, range_code in (
            ("azimuth_grados", 0.0, 360.0, "azimuth_range"),
            ("dip_grados", 0.0, 90.0, "dip_range"),
        ):
            text_value = get(column)
            if kind == "no_interpretable":
                if text_value:
                    row_errors.append(Issue("must_be_empty", number, column, text_value))
                angles[column] = None
            elif kind in ORIENTATION_TYPES:
                if not text_value:
                    row_errors.append(Issue("required", number, column))
                elif (value := _number(text_value)) is None:
                    row_errors.append(Issue("not_a_number", number, column, text_value))
                elif not (low <= value <= high):
                    row_errors.append(Issue(range_code, number, column, text_value))
                else:
                    angles[column] = 0.0 if (column == "azimuth_grados" and value == 360.0) else value

        key = normalize_key(filename)
        if filename.lower().endswith(".obj"):
            if key in seen:
                row_errors.append(Issue("duplicate_file", number, "archivo", filename))
            else:
                seen[key] = number
        if row_errors:
            errors.extend(row_errors)
            continue
        if known_keys is not None and key not in known_keys:
            warnings.append(Issue("not_in_dataset", number, "archivo", filename))
        rows.append(ReferenceRow(number, filename, key, kind, angles["azimuth_grados"], angles["dip_grados"],
                                 get("metodo"), get("observaciones")))

    if len(rows) > MAX_ROWS:
        errors.append(Issue("too_many_rows"))
    if not rows and not errors:
        errors.append(Issue("no_rows"))
    return ParseReport(tuple(rows) if not errors else (), tuple(errors), tuple(warnings), ignored)
