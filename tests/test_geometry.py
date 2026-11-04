"""Geometry perf regressions: the label growth and room cutting used to do a
page-sized pass per room (and, with an int64 `allowed`, _grow_along's boolean
mask became an integer index array and ballooned). These lock the behaviour
the optimised code must keep, on grids small enough to check by hand."""

import numpy as np

from conformscope import geometry


def test_grow_along_never_crosses_a_wall():
    labels = np.zeros((5, 9), np.int32)
    labels[2, 1] = 1
    labels[2, 7] = 2
    allowed = np.ones((5, 9), bool)
    allowed[:, 4] = False  # the wall

    grown = geometry._grow_along(labels, allowed, steps=10)

    assert grown[2, 3] == 1
    assert grown[2, 5] == 2
    assert (grown[:, 4] == 0).all()


def test_grow_along_accepts_an_int64_allowed_mask():
    # segment_rooms once handed _grow_along an int64 floor (bool & ~False):
    # as a mask that is fine, as fancy indexing it is a page-sized blow-up.
    labels = np.zeros((3, 5), np.int32)
    labels[1, 0] = 7
    allowed = np.ones((3, 5), np.int64)

    grown = geometry._grow_along(labels, allowed, steps=2)

    assert grown.dtype == np.int32
    assert grown[1, 2] == 7
    assert grown[1, 3] == 0  # only two steps of growth


def test_label_boxes_match_a_naive_scan():
    labels = np.zeros((6, 8), np.int32)
    labels[1:3, 2:5] = 3
    labels[4, 6] = 9
    labels[0, 0] = 9  # one label, two places: the box spans both

    boxes = geometry._label_boxes(labels)

    assert boxes[3] == (2, 1, 5, 3)
    assert boxes[9] == (0, 0, 7, 5)


def test_rooms_are_cut_over_their_own_boxes():
    labels = np.zeros((20, 30), np.int32)
    labels[2:10, 2:12] = 1
    labels[2:10, 18:28] = 2
    free = labels > 0
    solid = np.zeros_like(free)

    rooms = geometry._rooms(labels, free, solid, None, px_per_m=10.0)

    assert [r.number for r in rooms] == [1, 2]
    first, second = rooms
    assert first.bbox == (2, 2, 11, 9)
    assert second.bbox == (18, 2, 27, 9)
    assert first.area_m2 == 0.8
    # The crop rebuilds exactly the room's floor, wherever it sits.
    assert (first.mask == (labels == 1)).all()
    assert first.contains(2, 2) and not first.contains(18, 2)
    assert first.max_clearance_m > 0
