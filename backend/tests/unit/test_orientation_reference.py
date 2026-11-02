from solids.domain.orientation_reference import REQUIRED_COLUMNS, parse_orientation_reference, template_csv

HEAD = "archivo;tipo_orientacion;azimuth_grados;dip_grados;metodo;origen;observaciones"


def parse(body: str, known=None, encoding="utf-8"):
    return parse_orientation_reference(body.encode(encoding), known)


def codes(issues):
    return [i.code for i in issues]


def test_template_has_bom_required_columns_and_only_example_rows():
    raw = template_csv()
    assert raw.startswith(b"\xef\xbb\xbf")
    report = parse_orientation_reference(raw)
    assert report.ignored_examples >= 3
    assert report.rows == ()
    assert codes(report.errors) == ["no_rows"]  # an untouched template saves nothing
    text = raw.decode("utf-8-sig")
    assert all(col in text for col in REQUIRED_COLUMNS)
    assert any(k in text for k in ("planar", "axial", "no_interpretable"))


def test_valid_rows_with_decimal_comma_and_point():
    report = parse(f"{HEAD}\nwf_a_3pt.obj;planar;45,5;60;Studio RM;medido;ok\nwf_b_3.obj;axial;225.25;10;Leapfrog;;\n")
    assert report.errors == ()
    a, b = report.rows
    assert (a.key, a.orientation_type, a.azimuth, a.dip, a.method) == ("wf_a_3", "planar", 45.5, 60.0, "Studio RM")
    assert (b.azimuth, b.dip, b.observations) == (225.25, 10.0, "")


def test_azimuth_360_is_normalized_to_zero_and_type_is_case_insensitive():
    (row,) = parse(f"{HEAD}\na.obj;Planar;360;0;Studio RM;;\n").rows
    assert row.azimuth == 0.0 and row.orientation_type == "planar"


def test_non_interpretable_requires_empty_angles():
    ok = parse(f"{HEAD}\na.obj;no interpretable;;;Studio RM;;sin dirección dominante\n")
    assert ok.errors == () and ok.rows[0].azimuth is None and ok.rows[0].dip is None
    bad = parse(f"{HEAD}\na.obj;no_interpretable;10;20;Studio RM;;\n")
    assert codes(bad.errors) == ["must_be_empty", "must_be_empty"]


def test_each_row_error_carries_physical_line_and_column():
    report = parse(f"# comentario\n{HEAD}\na.obj;planar;400;60;Studio RM;;\nb.obj;planar;10;95;Studio RM;;\nc.obj;oblicuo;10;20;Studio RM;;\nd.obj;planar;abc;20;Studio RM;;\ne.obj;planar;;20;Studio RM;;\nf.txt;planar;1;2;Studio RM;;\ng.obj;planar;1;2;;;\n")
    found = [(i.code, i.line, i.column) for i in report.errors]
    assert found == [
        ("azimuth_range", 3, "azimuth_grados"),
        ("dip_range", 4, "dip_grados"),
        ("bad_type", 5, "tipo_orientacion"),
        ("not_a_number", 6, "azimuth_grados"),
        ("required", 7, "azimuth_grados"),
        ("not_obj", 8, "archivo"),
        ("required", 9, "metodo"),
    ]


def test_missing_required_column_is_reported_once_and_stops_row_checks():
    report = parse("archivo;tipo_orientacion;azimuth_grados;metodo\na.obj;planar;1;Studio RM\n")
    assert codes(report.errors) == ["missing_column"] and report.errors[0].column == "dip_grados"


def test_same_solid_twice_is_an_error_even_with_and_without_pt():
    report = parse(f"{HEAD}\nx_3pt.obj;planar;1;2;Studio RM;;\nx_3.obj;planar;1;2;Studio RM;;\n")
    assert codes(report.errors) == ["duplicate_file"] and report.errors[0].line == 3


def test_example_rows_are_ignored_and_counted():
    report = parse(f"{HEAD}\nejemplo.obj;planar;1;2;Studio RM;ejemplo;\nreal.obj;planar;1;2;Studio RM;medido;\n")
    assert (len(report.rows), report.ignored_examples, report.errors) == (1, 1, ())


def test_warnings_for_unknown_columns_and_files_outside_the_period():
    report = parse(f"{HEAD};color\nzzz.obj;planar;1;2;Studio RM;;;rojo\n", known={"a"})
    assert codes(report.warnings) == ["unknown_column", "not_in_dataset"]
    assert len(report.rows) == 1


def test_header_aliases_ignore_case_spaces_and_accents():
    report = parse("Archivo;Tipo orientación;Azimuth (grados);Dip grados;Método\na.obj;planar;1;2;Studio RM\n")
    assert report.errors == () and len(report.rows) == 1


def test_comma_delimiter_and_windows_encoding_are_accepted():
    body = "archivo,tipo_orientacion,azimuth_grados,dip_grados,metodo,origen,observaciones\na.obj,planar,10,20,Studio RM,,Observación\n"
    report = parse(body, encoding="cp1252")
    assert report.errors == () and report.rows[0].observations == "Observación"


def test_empty_file_and_binary_noise_are_rejected():
    assert codes(parse("").errors) == ["empty_file"]
    assert codes(parse_orientation_reference(b"\x00\x01\x02").errors)[0] in {"empty_file", "missing_column"}
