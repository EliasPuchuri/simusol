import pytest

from solids.domain.orientation_compare import compare_orientation


def o(kind, az=None, dip=None):
    return {"type": kind, "azimuth": az, "dip": dip}


def test_planar_azimuth_difference_is_circular():
    r = compare_orientation(o("planar", 359.0, 40.0), o("planar", 1.0, 42.5))
    assert r["comparable"] is True
    assert r["delta_azimuth_deg"] == pytest.approx(2.0) and r["delta_dip_deg"] == pytest.approx(2.5)


def test_axial_azimuth_is_equivalent_every_180_degrees():
    # an axis reversed by the PCA sign must not look like a 180 degree turn (RC-25)
    r = compare_orientation(o("axial", 45.0, 20.0), o("axial", 225.0, 21.0))
    assert r["delta_azimuth_deg"] == pytest.approx(0.0) and r["delta_dip_deg"] == pytest.approx(1.0)


def test_planar_does_not_use_the_180_degree_equivalence():
    assert compare_orientation(o("planar", 45.0, 60.0), o("planar", 225.0, 60.0))["delta_azimuth_deg"] == pytest.approx(180.0)


def test_different_orientation_types_are_not_compared():
    r = compare_orientation(o("planar", 10.0, 30.0), o("axial", 10.0, 30.0))
    assert r == {"comparable": False, "reason": "different_orientation_type"}


def test_not_interpretable_on_either_side_is_not_compared():
    assert compare_orientation(o("no_interpretable"), o("planar", 1.0, 2.0))["reason"] == "not_interpretable"
    assert compare_orientation(o("planar", 1.0, 2.0), o("no_interpretable"))["reason"] == "not_interpretable"


def test_a_missing_azimuth_still_compares_the_dip():
    r = compare_orientation(o("planar", None, 0.0), o("planar", None, 1.5))
    assert r["comparable"] is True and r["delta_azimuth_deg"] is None and r["delta_dip_deg"] == pytest.approx(1.5)
