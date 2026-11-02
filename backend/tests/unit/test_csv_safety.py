import csv
import io

import pytest

from solids.exports.characterization_csv import characterization_csv
from solids.exports.comparison_csv import comparison_csv
from solids.exports.qc_csv import qc_csv
from solids.exports.review_csv import review_csv
from solids.exports.safe import text_cell


@pytest.mark.parametrize("danger", ["=1+1", "+cmd", "-cmd", "@SUM(A1)", "\tcmd", "\rcmd", "=HYPERLINK(\"http://x\",\"y\")"])
def test_text_starting_with_a_formula_character_is_neutralised(danger):
    assert text_cell(danger) == "'" + danger


@pytest.mark.parametrize("fine", ["normal", "Estudio RM", "a=b", "wf_am1_3.obj", "", "ñandú", "1.5 m"])
def test_ordinary_text_is_left_alone(fine):
    assert text_cell(fine) == fine


def rows_of(raw: bytes):
    text = raw.decode("utf-8-sig")
    header, *rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    return [dict(zip(header, r)) for r in rows]


EVIL = "=cmd|' /C calc'!A0"


def test_review_csv_neutralises_every_free_text_cell():
    review = {"key": EVIL, "reviewer": "+boss", "agrees": False, "comment": "@SUM(1)", "expected_state": "VARIABLE", "expected_body_type": None,
              "expected_azimuth": -5.5, "expected_dip": 3.0, "system_state": "VARIABLE", "system_subtype": None,
              "system_description": "-descripcion", "profile": "p", "updated_at": "2026-01-01T00:00:00+00:00"}
    (row,) = rows_of(review_csv("=prev", "-curr", [review]))
    for column, value in (("Cuerpo", EVIL), ("Revisor", "+boss"), ("Comentario", "@SUM(1)"), ("Descripcion_sistema", "-descripcion"),
                          ("Periodo_anterior", "=prev"), ("Periodo_actual", "-curr")):
        assert row[column] == "'" + value, column
    assert row["Azimuth_esperado"] == "-5.5"  # a number is not text: it must keep its sign


def test_qc_csv_neutralises_names_and_notes_but_not_numbers():
    result = {"status": "with_issues", "signed_volume_m3": -1000.0, "volume_m3": {"value": None, "reason": "inverted_orientation"},
              "problems": ["inverted_orientation"], "error": "=boom", "orientation": "inverted"}
    (row,) = rows_of(qc_csv("=2025", [{"filename": "=x.obj", "key": "-x", "result": result}]))
    assert (row["Archivo"], row["Clave"], row["Periodo"], row["Observaciones"]) == ("'=x.obj", "'-x", "'=2025", "'=boom")
    assert row["Volumen_firmado_m3"] == "-1000.0"


def test_characterization_csv_neutralises_names_and_reference_method():
    row = {"filename": "@a.obj", "key": "+a", "result": {"status": "ok", "body_type": "TABULAR", "eigenvalues": [3, 2, 1],
                                                          "orientation": {"type": "planar", "azimuth": 1.0, "dip": 2.0}, "error": "-err"},
           "volume": {"value": None, "reason": "qc_pendiente"},
           "reference": {"method": "=Studio", "azimuth": 1.0, "dip": 2.0, "comparison": {"delta_azimuth_deg": 0.1, "delta_dip_deg": 0.2}}}
    (out,) = rows_of(characterization_csv("-p", [row]))
    assert (out["Archivo"], out["Clave"], out["Periodo"], out["Ref_Metodo"], out["Observaciones"]) == ("'@a.obj", "'+a", "'-p", "'=Studio", "'-err")


def test_comparison_csv_neutralises_names_description_and_notes_but_not_negative_metrics():
    row = {"key": "=k", "previous_filename": "=a.obj", "current_filename": "-b.obj", "metrics": {"delta_volume_pct": -4.8, "iou_pct": 83.4},
           "volumes": {"previous_m3": 10.0, "current_m3": 9.0}, "state": "VARIABLE", "subtype": "VARIABLE", "description": "=RECORTE",
           "technical_status": "ok", "provisional": True, "profile": "p", "warnings": ["@w"], "incidents": [], "reasons": {}}
    (out,) = rows_of(comparison_csv("=2025", "+2026", [row]))
    assert (out["Cuerpo"], out["Mesh_anterior"], out["Mesh_actual"], out["Descripcion"]) == ("'=k", "'=a.obj", "'-b.obj", "'=RECORTE")
    assert (out["Periodo_anterior"], out["Periodo_actual"], out["Observaciones"]) == ("'=2025", "'+2026", "'@w")
    assert out["Delta_volumen_pct"] == "-4.8"
