import json
import math

import pytest

from solids.domain.metrics import Metric, Validity


def test_valid_metric_keeps_value():
    m = Metric.valid(12.5)
    assert m.value == 12.5 and m.validity is Validity.VALID and m.reason is None


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_valid_metric_rejects_non_finite(bad):
    with pytest.raises(ValueError):
        Metric.valid(bad)


@pytest.mark.parametrize(
    "factory,validity",
    [
        (Metric.not_applicable, Validity.NOT_APPLICABLE),
        (Metric.unavailable, Validity.UNAVAILABLE),
        (Metric.failed, Validity.FAILED),
    ],
)
def test_non_valid_metric_has_null_value_and_reason(factory, validity):
    m = factory("sin volumen valido")
    assert m.value is None and m.validity is validity and m.reason == "sin volumen valido"


def test_failure_is_never_zero():
    assert Metric.failed("boolean error").value is None


def test_non_valid_metric_requires_reason():
    with pytest.raises(ValueError):
        Metric.failed("")


def test_to_dict_is_strict_json():
    for m in (Metric.valid(0.0), Metric.failed("x")):
        text = json.dumps(m.to_dict(), allow_nan=False)
        assert json.loads(text)["validity"] == m.validity.value
