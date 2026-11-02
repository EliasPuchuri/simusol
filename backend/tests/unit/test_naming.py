import pytest

from solids.domain.naming import normalize_key


@pytest.mark.parametrize(
    "filename,key",
    [
        ("wf_am1_3pt.obj", "wf_am1_3"),
        ("wf_am1_3.obj", "wf_am1_3"),
        ("WF_AM1_3PT.OBJ", "wf_am1_3"),
        ("  wf_am1_3pt.obj ", "wf_am1_3"),
        ("wf_ptx_3.obj", "wf_ptx_3"),  # internal "pt" is kept
        ("wf_pt_3pt.obj", "wf_pt_3"),
    ],
)
def test_normalize_key(filename, key):
    assert normalize_key(filename) == key


def test_only_one_terminal_pt_is_removed():
    assert normalize_key("wf_x_ptpt.obj") == "wf_x_pt"


def test_name_made_only_of_suffix_is_kept():
    assert normalize_key("pt.obj") == "pt"
