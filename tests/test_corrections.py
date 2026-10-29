import json
from dataclasses import asdict

import numpy as np
import pytest

from conformscope import geometry
from conformscope.corrections import (
    DRAWN_WALL_OVERSHOOT_M,
    DrawnWall,
    Merge,
    apply_corrections,
    apply_drawn_wall,
    apply_merge,
    corrections_from_json,
    corrections_to_data,
    corrections_to_json,
    dump_corrections,
    extended_endpoints_px,
    load_corrections,
    merge_measured_rooms,
    outline_source_of,
    replay_corrections,
    room_from_mask,
    split_mask_by_wall,
)
from conformscope.rooms import MeasuredRoom

PX_PER_M = 10.0  # with pt_to_px=1.0, one PDF point is one grid pixel in these tests


def _adjacent_masks():
    """Two side-by-side synthetic rooms: 4 m² and 2 m² at 10 px/m."""
    target = np.zeros((60, 80), bool)
    target[10:30, 10:30] = True  # 20 x 20 px
    region = np.zeros((60, 80), bool)
    region[10:30, 30:40] = True  # 10 x 20 px, sharing the target's right edge
    return target, region


def _merge():
    # PDF points (x, y): inside the region to merge, and inside its target.
    return Merge(point=(35.0, 20.0), target_point=(20.0, 20.0))


def test_merge_unions_the_masks_and_sums_the_areas():
    target, region = _adjacent_masks()

    result = apply_merge([target, region], _merge(), PX_PER_M, pt_to_px=1.0)

    assert result.mask.sum() == target.sum() + region.sum()
    assert result.area_m2 == pytest.approx(6.0, rel=0.03)  # 4 m² + 2 m²
    assert len(result.polygon_m) >= 3 and len(result.polygon_px) >= 3
    xs, ys = zip(*result.polygon_m)
    assert min(xs) == pytest.approx(1.0, abs=0.15) and max(xs) == pytest.approx(4.0, abs=0.15)
    assert result.circle_m == pytest.approx(2.0, abs=0.15)  # the 2 m-tall union's height
    assert result.circle_px is not None
    assert result.outline_source == "merged"
    assert (result.target_index, result.merged_index) == (0, 1)
    # Pure: the inputs are untouched.
    assert target.sum() == 400 and region.sum() == 200


def test_merge_finds_its_rooms_by_point_not_by_index():
    target, region = _adjacent_masks()

    forward = apply_merge([target, region], _merge(), PX_PER_M, pt_to_px=1.0)
    shuffled = apply_merge([region, target], _merge(), PX_PER_M, pt_to_px=1.0)

    assert np.array_equal(forward.mask, shuffled.mask)
    assert shuffled.area_m2 == forward.area_m2
    assert (shuffled.target_index, shuffled.merged_index) == (1, 0)


def test_merge_with_a_point_in_no_room_raises():
    target, region = _adjacent_masks()

    with pytest.raises(ValueError, match="target"):
        apply_merge([target, region], Merge(point=(35.0, 20.0), target_point=(70.0, 50.0)),
                    PX_PER_M, pt_to_px=1.0)


def test_a_merged_room_is_rebuilt_with_merged_provenance():
    target, region = _adjacent_masks()
    base = MeasuredRoom(name="Séjour", room_type="living", type_source="text",
                        area_m2=4.0, written_area_m2=4.0, polygon_px=[], polygon_m=[],
                        circle_m=2.0, circle_px=(20.0, 20.0))

    room = merge_measured_rooms(base, base, target, region, PX_PER_M, to_plan=1.0)

    assert room.name == "Séjour" and room.type_source == "text"
    assert room.area_m2 == pytest.approx(6.0, rel=0.03)
    assert len(room.polygon_m) >= 3 and room.circle_m > 0
    assert room.outline_source == "merged"
    assert asdict(room)["outline_source"] == "merged"  # survives api-style serialisation
    assert outline_source_of(room) == "merged"
    assert outline_source_of(base) == "auto"  # an untouched room


def test_replay_drops_the_merged_region_and_marks_the_target():
    target, region = _adjacent_masks()
    other = np.zeros((60, 80), bool)
    other[40:50, 10:20] = True

    replay = apply_corrections([target, region, other], [_merge()],
                               PX_PER_M, pt_to_px=1.0)

    assert len(replay.masks) == 2
    assert replay.outline_sources == ["merged", "auto"]
    assert np.array_equal(replay.masks[0], target | region)
    assert np.array_equal(replay.masks[1], other)


def test_drawn_wall_overshoots_both_ends_by_the_constant():
    assert DRAWN_WALL_OVERSHOOT_M == 0.15
    wall = DrawnWall(start=(60.0, 50.0), end=(140.0, 50.0))

    (x1, y1), (x2, y2) = extended_endpoints_px(wall, px_per_m=50.0, pt_to_px=1.0)

    assert (x1, y1) == pytest.approx((60.0 - 0.15 * 50.0, 50.0))
    assert (x2, y2) == pytest.approx((140.0 + 0.15 * 50.0, 50.0))


def test_drawn_wall_rasterisation_covers_just_past_each_end_but_not_well_past():
    barrier = np.zeros((100, 200), bool)
    wall = DrawnWall(start=(60.0, 50.0), end=(140.0, 50.0))

    result = apply_drawn_wall(barrier, wall, px_per_m=50.0, pt_to_px=1.0)

    # The drawn segment, and a point just beyond each end (inside the overshoot).
    for x in (60, 100, 140, 55, 145):
        assert result[50, x], x
    # Well past the overshoot (7.5 px at 50 px/m) the wall is not there.
    for x in (30, 170):
        assert not result[50, x], x
    assert not barrier.any()  # pure: the input mask is untouched


def test_a_degenerate_drawn_wall_raises():
    with pytest.raises(ValueError, match="distinct"):
        apply_drawn_wall(np.zeros((20, 20), bool),
                         DrawnWall(start=(5.0, 5.0), end=(5.0, 5.0)),
                         px_per_m=50.0, pt_to_px=1.0)


def _room_and_wall():
    """One synthetic room (wall ring) and an empty barrier, at 20 px/m."""
    wall = np.zeros((120, 200), bool)
    wall[:4, :] = wall[-4:, :] = True
    wall[:, :4] = wall[:, -4:] = True
    return wall, np.zeros((120, 200), bool)


def test_a_drawn_wall_splits_the_room_on_recut():
    wall, barrier = _room_and_wall()
    drawn = DrawnWall(start=(100.0, 10.0), end=(100.0, 110.0))
    empty = np.zeros_like(wall)

    _, _, before = geometry.segment_rooms(wall, barrier, empty, px_per_m=20.0)
    assert len(before) == 1

    split_barrier = apply_drawn_wall(barrier, drawn, px_per_m=20.0, pt_to_px=1.0)
    _, _, after = geometry.segment_rooms(wall, split_barrier, empty, px_per_m=20.0)

    assert len(after) == 2
    areas = sorted(room.area_m2 for room in after)
    assert areas[0] == pytest.approx(areas[1], rel=0.1)
    assert sum(areas) == pytest.approx(before[0].area_m2, rel=0.05)


def test_split_mask_by_wall_cuts_one_mask_in_two():
    mask = np.zeros((40, 80), bool)
    mask[5:35, 5:75] = True
    wall = apply_drawn_wall(np.zeros((40, 80), bool),
                            DrawnWall(start=(40.0, 5.0), end=(40.0, 35.0)),
                            px_per_m=20.0, pt_to_px=1.0)

    pieces = split_mask_by_wall(mask, wall)

    assert len(pieces) == 2
    assert pieces[0].sum() == pytest.approx(pieces[1].sum(), rel=0.05)


def test_corrections_serialise_to_and_from_json_unchanged():
    corrections = [_merge(), DrawnWall(start=(60.0, 50.0), end=(140.0, 50.0))]

    data = corrections_to_data(corrections)

    assert data == [
        {"kind": "merge", "point": [35.0, 20.0], "target_point": [20.0, 20.0]},
        {"kind": "wall", "start": [60.0, 50.0], "end": [140.0, 50.0]},
    ]
    assert corrections_from_json(json.dumps(data)) == corrections
    assert corrections_from_json(corrections_to_json(corrections)) == corrections


def test_corrections_round_trip_through_a_plan_folder(tmp_path):
    corrections = [_merge(), DrawnWall(start=(1.5, 2.5), end=(3.5, 4.5))]

    path = dump_corrections(tmp_path, corrections)

    assert path == tmp_path / "corrections.json"
    assert load_corrections(tmp_path) == corrections
    assert load_corrections(tmp_path / "missing") == []


def test_replay_is_deterministic_after_a_json_reload():
    target, region = _adjacent_masks()
    corrections = [_merge()]

    first = replay_corrections([target, region], corrections, PX_PER_M, pt_to_px=1.0)
    reloaded = corrections_from_json(corrections_to_json(corrections))
    second = replay_corrections([target, region], reloaded, PX_PER_M, pt_to_px=1.0)
    again = replay_corrections([target, region], corrections, PX_PER_M, pt_to_px=1.0)

    for a, b in zip(first.masks, second.masks):
        assert np.array_equal(a, b)
    assert first.outline_sources == second.outline_sources == ["merged"]
    (r1,), (r2,) = first.results, second.results
    assert (r1.area_m2, r1.polygon_px, r1.polygon_m, r1.circle_m, r1.circle_px) == \
           (r2.area_m2, r2.polygon_px, r2.polygon_m, r2.circle_m, r2.circle_px)
    assert np.array_equal(first.masks[0], again.masks[0])


def test_a_room_built_from_a_corrected_mask_carries_wall_provenance():
    mask = np.zeros((60, 80), bool)
    mask[10:30, 10:30] = True

    room = room_from_mask(mask, PX_PER_M, outline_source="wall", name="WC",
                          room_type="wc", type_source="text")

    assert room.outline_source == "wall"
    assert room.area_m2 == pytest.approx(4.0, rel=0.03)
    assert room.circle_m > 0 and len(room.polygon_m) >= 3
