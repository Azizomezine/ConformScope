"""Turning circle check (issue #4): rasterised polygon, distance transform.

The approach under test is rasterisation at 200 px/m inside the polygon's
bounding box plus ``geometry._fit_circle`` (see conformscope.turning), not a
polylabel-style search.
"""

import pytest

from conformscope.turning import TurningCheck, check_turning

TOL = 0.05  # grid quantisation at 200 px/m


def test_a_2x2_square_holds_the_turning_circle():
    result = check_turning([(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)])

    assert result.conforme is True
    assert result.max_diameter_m == pytest.approx(2.0, abs=TOL)
    assert result.center_m is not None
    assert result.center_m == pytest.approx((1.0, 1.0), abs=TOL)
    assert result.verdict == "Conforme PMR"


def test_a_1_4_wide_corridor_does_not_hold_it():
    result = check_turning([(0.0, 0.0), (3.0, 0.0), (3.0, 1.4), (0.0, 1.4)])

    assert result.conforme is False
    assert result.max_diameter_m == pytest.approx(1.4, abs=TOL)
    assert result.max_diameter_m < 1.50
    assert result.center_m is not None
    cx, cy = result.center_m
    assert 0.0 < cx < 3.0
    assert 0.0 < cy < 1.4
    assert result.verdict == f"Non conforme PMR (max Ø{result.max_diameter_m:.2f} m)"


def test_an_l_shaped_room_finds_the_fat_lobe_not_the_arm():
    # 2.4 x 2.4 lobe with a 1.2 m wide arm running off its lower right.
    polygon = [(0.0, 0.0), (2.4, 0.0), (2.4, 1.2), (3.6, 1.2), (3.6, 2.4), (0.0, 2.4)]

    result = check_turning(polygon)

    assert result.conforme is True
    assert result.max_diameter_m > 1.8
    assert result.max_diameter_m == pytest.approx(2.4, abs=TOL)
    assert result.center_m is not None
    cx, cy = result.center_m
    assert 0.0 < cx < 2.4
    assert 0.0 < cy < 2.4


def test_a_repeated_first_point_behaves_like_the_open_outline():
    open_outline = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
    closed_outline = open_outline + [open_outline[0]]

    assert check_turning(closed_outline) == check_turning(open_outline)


def test_a_smaller_minimum_diameter_can_pass_the_corridor():
    result = check_turning(
        [(0.0, 0.0), (3.0, 0.0), (3.0, 1.4), (0.0, 1.4)], min_diameter_m=1.20)

    assert result.conforme is True


@pytest.mark.parametrize("polygon", [
    [],
    [(0.0, 0.0)],
    [(0.0, 0.0), (1.0, 0.0)],
    [(0.0, 0.0), (0.0, 0.0), (0.0, 0.0)],
    [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)],  # collinear: zero area
    [(1.0, 1.0), (1.0, 1.0), (1.0, 1.0), (1.0, 1.0)],
])
def test_degenerate_polygons_hold_no_circle_and_do_not_crash(polygon):
    assert check_turning(polygon) == TurningCheck(
        conforme=False, max_diameter_m=0.0, center_m=None)
