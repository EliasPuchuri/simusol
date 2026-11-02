import pytest

from solids.domain.inventory import Inventory, InventoryEntry
from solids.domain.matching import match_inventories


def entry(name, key, sha="0" * 64):
    return InventoryEntry(filename=name, key=key, sha256=sha, size_bytes=1)


def inv(*entries, closed=True):
    return Inventory.from_entries(entries, closed=closed)


def test_pairs_by_normalized_key_keeping_original_names():
    prev = inv(entry("wf_am1_3pt.obj", "wf_am1_3"))
    curr = inv(entry("wf_am1_3.obj", "wf_am1_3"))
    result = match_inventories(prev, curr)
    assert [(p.previous.filename, p.current.filename) for p in result.pairs] == [
        ("wf_am1_3pt.obj", "wf_am1_3.obj")
    ]
    assert not result.only_previous and not result.only_current


def test_present_in_one_period_only():
    prev = inv(entry("a.obj", "a"), entry("old.obj", "old"))
    curr = inv(entry("a.obj", "a"), entry("new.obj", "new"))
    result = match_inventories(prev, curr)
    assert [e.key for e in result.only_previous] == ["old"]
    assert [e.key for e in result.only_current] == ["new"]


def test_collision_is_reported_and_no_winner_is_chosen():
    prev = inv(entry("x_3pt.obj", "x_3"), entry("x_3.obj", "x_3"))
    curr = inv(entry("x_3.obj", "x_3"))
    result = match_inventories(prev, curr)
    assert result.pairs == ()
    assert not result.only_previous and not result.only_current
    codes = [i.code for i in result.incidents]
    assert codes == ["duplicate_key"]
    assert set(result.incidents[0].detail["filenames"]) == {"x_3pt.obj", "x_3.obj"}


@pytest.mark.parametrize("which", ["previous", "current"])
def test_open_inventory_cannot_be_compared(which):
    open_inv = inv(entry("a.obj", "a"), closed=False)
    closed_inv = inv(entry("a.obj", "a"))
    args = (open_inv, closed_inv) if which == "previous" else (closed_inv, open_inv)
    with pytest.raises(ValueError, match="closed"):
        match_inventories(*args)


def test_results_are_sorted_by_key():
    prev = inv(entry("b.obj", "b"), entry("a.obj", "a"))
    curr = inv(entry("b.obj", "b"), entry("a.obj", "a"))
    assert [p.key for p in match_inventories(prev, curr).pairs] == ["a", "b"]
