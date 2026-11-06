from solids.domain.spatial import assess

BOX = ((367_000.0, 8_826_000.0, 2_500.0), (368_500.0, 8_829_000.0, 4_200.0))
OTHER_PLACE = ((100.0, 200.0, 0.0), (900.0, 700.0, 50.0))
side = lambda ref=None, units=None, extent=BOX: {"spatial_reference": ref, "units": units, "extent": extent}


def test_same_declared_system_and_overlapping_extents_are_compatible():
    r = assess(side("UTM 18S WGS84", "m"), side("utm  18s wgs84", "M"))
    assert r["status"] == "compatible" and r["issues"] == [] and r["extent_checked"] is True


def test_different_declared_reference_is_a_mismatch_even_if_the_extents_agree():
    r = assess(side("UTM 18S", "m"), side("UTM 19S", "m"))
    assert r["status"] == "mismatch" and r["issues"] == ["spatial_reference_mismatch"]


def test_different_declared_units_are_a_mismatch():
    r = assess(side(units="m"), side(units="ft"))
    assert r["status"] == "mismatch" and "units_mismatch" in r["issues"]


def test_extents_that_do_not_overlap_in_east_north_point_to_another_system_or_a_wrong_folder():
    r = assess(side("UTM 18S", "m"), side("UTM 18S", "m", OTHER_PLACE))
    assert r["status"] == "extent_disjoint" and r["issues"] == ["extent_disjoint"]


def test_elevation_alone_never_makes_the_periods_incompatible():
    lower = ((367_000.0, 8_826_000.0, -50.0), (368_500.0, 8_829_000.0, 10.0))
    assert assess(side("UTM", "m"), side("UTM", "m", lower))["status"] == "compatible"


def test_a_missing_declaration_is_reported_as_undeclared_not_assumed_compatible():
    r = assess(side(), side())
    assert r["status"] == "undeclared" and "spatial_reference_undeclared" in r["issues"] and "units_undeclared" in r["issues"]


def test_one_side_declared_is_still_undeclared():
    assert assess(side("UTM 18S", "m"), side(None, "m"))["status"] == "undeclared"


def test_without_extents_the_check_is_skipped_and_said_so():
    r = assess(side("UTM", "m", None), side("UTM", "m"))
    assert r["extent_checked"] is False and r["status"] == "compatible"


def test_mismatch_outranks_the_disjoint_extents_and_the_undeclared_notice():
    r = assess(side("A", None, BOX), side("B", None, OTHER_PLACE))
    assert r["status"] == "mismatch" and set(r["issues"]) >= {"spatial_reference_mismatch", "extent_disjoint"}
