from solids.domain.overlaps import candidate_pairs

box = lambda lo, hi: (lo, hi)


def test_every_unordered_pair_is_listed_once_and_the_separated_ones_are_discarded():
    boxes = {
        "a": box((0, 0, 0), (10, 10, 10)),
        "b": box((5, 5, 5), (15, 15, 15)),      # overlaps a
        "c": box((100, 0, 0), (110, 10, 10)),   # far from both
    }
    candidates, discarded = candidate_pairs(boxes)
    assert candidates == [("a", "b")]
    assert discarded == [("a", "c"), ("b", "c")]


def test_boxes_that_only_touch_stay_candidates_because_the_test_must_be_conservative():
    boxes = {"a": box((0, 0, 0), (10, 10, 10)), "b": box((10, 0, 0), (20, 10, 10))}
    assert candidate_pairs(boxes)[0] == [("a", "b")]


def test_separation_on_a_single_axis_is_enough_to_discard():
    boxes = {"a": box((0, 0, 0), (10, 10, 10)), "b": box((0, 0, 10.5), (10, 10, 20))}
    assert candidate_pairs(boxes) == ([], [("a", "b")])


def test_the_tolerance_widens_the_boxes_so_a_near_miss_is_still_checked():
    boxes = {"a": box((0, 0, 0), (10, 10, 10)), "b": box((10.4, 0, 0), (20, 10, 10))}
    assert candidate_pairs(boxes)[0] == []
    assert candidate_pairs(boxes, tolerance=0.5)[0] == [("a", "b")]


def test_pairs_come_out_in_a_stable_order_whatever_the_input_order():
    boxes = {k: box((0, 0, 0), (1, 1, 1)) for k in ("z", "m", "a")}
    assert candidate_pairs(boxes)[0] == [("a", "m"), ("a", "z"), ("m", "z")]
    assert candidate_pairs(dict(reversed(boxes.items())))[0] == candidate_pairs(boxes)[0]


def test_fewer_than_two_solids_have_no_pairs():
    assert candidate_pairs({}) == ([], [])
    assert candidate_pairs({"a": box((0, 0, 0), (1, 1, 1))}) == ([], [])
