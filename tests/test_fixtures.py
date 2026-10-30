import json
from types import SimpleNamespace

import numpy as np
import pymupdf
import pytest

from conformscope.fixtures import assign_rooms, split_fixtures
from conformscope.labels import parse_rooms
from conformscope.plan import load_plan
from conformscope.rooms import measure_rooms
from test_labels import RECORDED
from test_rooms import SAMPLE, _fake_client


def _box(shape, x0, y0, x1, y1):
    mask = np.zeros(shape, bool)
    mask[y0:y1, x0:x1] = True
    return mask


SHAPE = (200, 300)


def test_each_detector_becomes_one_fixture_per_symbol():
    placards = _box(SHAPE, 10, 10, 40, 80) | _box(SHAPE, 200, 10, 260, 40)
    cells = _box(SHAPE, 100, 100, 130, 130)
    toilets = _box(SHAPE, 150, 150, 170, 180)

    fixtures = split_fixtures(placards, cells, toilets)

    assert sorted(f.kind for f in fixtures) == ["appliance", "placard", "placard", "toilet"]
    toilet = next(f for f in fixtures if f.kind == "toilet")
    assert toilet.origin == (150, 150) and toilet.crop.shape == (30, 20)


def test_a_toilet_the_cell_finder_also_took_is_only_a_toilet():
    toilets = _box(SHAPE, 150, 150, 170, 180)
    cells = _box(SHAPE, 148, 148, 172, 182)  # the same symbol, a little wider

    fixtures = split_fixtures(np.zeros(SHAPE, bool), cells, toilets)

    assert [f.kind for f in fixtures] == ["toilet"]


def test_a_speck_left_over_is_not_a_fixture():
    cells = _box(SHAPE, 100, 100, 102, 102)

    assert split_fixtures(np.zeros(SHAPE, bool), cells, np.zeros(SHAPE, bool)) == []


def test_an_appliance_in_a_bathroom_or_wc_is_a_washbasin():
    kitchen = _box(SHAPE, 0, 0, 150, 200)
    bathroom = _box(SHAPE, 150, 0, 300, 200)
    fixtures = split_fixtures(np.zeros(SHAPE, bool),
                              _box(SHAPE, 20, 20, 50, 50) | _box(SHAPE, 200, 20, 230, 50),
                              np.zeros(SHAPE, bool))

    assign_rooms(fixtures, [kitchen, bathroom], ["kitchen", "bathroom"])

    by_room = {f.room: f.kind for f in fixtures}
    assert by_room == {0: "appliance", 1: "washbasin"}


def test_a_placard_in_a_bathroom_stays_a_placard_and_one_outside_every_room_has_none():
    bathroom = _box(SHAPE, 150, 0, 300, 200)
    fixtures = split_fixtures(_box(SHAPE, 200, 20, 260, 50) | _box(SHAPE, 10, 10, 40, 40),
                              np.zeros(SHAPE, bool), np.zeros(SHAPE, bool))

    assign_rooms(fixtures, [bathroom], ["bathroom"])

    assert sorted((f.kind, f.room) for f in fixtures if f.room is not None) == [("placard", 0)]
    assert any(f.room is None for f in fixtures)


def test_a_fixture_belongs_to_the_room_holding_most_of_it():
    left = _box(SHAPE, 0, 0, 105, 200)
    right = _box(SHAPE, 105, 0, 300, 200)
    fixtures = split_fixtures(_box(SHAPE, 100, 50, 140, 80), np.zeros(SHAPE, bool),
                              np.zeros(SHAPE, bool))

    assign_rooms(fixtures, [left, right], ["bedroom", "bedroom"])

    assert fixtures[0].room == 1


@pytest.mark.skipif(not SAMPLE.exists(), reason="private sample plan not present")
def test_sample_plan_fixtures_are_found_and_placed_in_their_rooms():
    plan = load_plan(SAMPLE)
    reading = parse_rooms(RECORDED, plan.width, plan.height)
    client, _ = _fake_client(json.dumps({"rooms": []}))

    result = measure_rooms(client, SAMPLE, plan, reading)

    kinds = [f.kind for f in result.fixtures]
    assert kinds.count("placard") == 13
    assert kinds.count("toilet") == 7
    assert kinds.count("appliance") + kinds.count("washbasin") >= 10
    for fixture in result.fixtures:
        assert len(fixture.polygon_px) >= 3 and len(fixture.polygon_m) >= 3
        if fixture.room is not None:
            assert result.fixtures.index(fixture) in result.rooms[fixture.room].fixtures
    for fixture in result.fixtures:
        if fixture.kind == "washbasin":
            assert result.rooms[fixture.room].room_type in ("wc", "bathroom")


def test_removing_the_fixture_that_blocks_a_transfer_space_turns_it_green():
    from conformscope.fixtures import FixtureMask, remove_fixtures
    from conformscope.spaces import check_spaces

    shape = (120, 160)
    room = _box(shape, 10, 10, 80, 110)
    toilet = FixtureMask("toilet", (10, 50), np.ones((20, 28), bool), room=0)
    basin = FixtureMask("washbasin", (38, 10), np.ones((100, 42), bool), room=0)
    walls = np.zeros(shape, bool)
    assert not check_spaces([toilet, basin], [room], walls, 50)[0].fits

    kept = remove_fixtures([toilet, basin], [(60, 60)])

    assert kept == [toilet]
    assert check_spaces(kept, [room], walls, 50)[0].fits


def test_a_removal_that_lands_on_no_fixture_removes_nothing():
    from conformscope.fixtures import FixtureMask, remove_fixtures

    toilet = FixtureMask("toilet", (10, 50), np.ones((20, 28), bool))

    assert remove_fixtures([toilet], [(5, 5), (500, 500)]) == [toilet]


@pytest.mark.skipif(not SAMPLE.exists(), reason="private sample plan not present")
def test_sample_plan_a_removed_toilet_is_gone_until_the_corrections_are_cleared():
    plan = load_plan(SAMPLE)
    reading = parse_rooms(RECORDED, plan.width, plan.height)
    client, _ = _fake_client(json.dumps({"rooms": []}))
    before = measure_rooms(client, SAMPLE, plan, reading)
    toilet = next(f for f in before.fixtures if f.kind == "toilet")
    # The correction is anchored in PDF points; the polygon is in plan pixels.
    with pymupdf.open(SAMPLE) as doc:
        pt_per_px = doc[0].rect.width / plan.width
    xs, ys = zip(*toilet.polygon_px)
    point = [(min(xs) + max(xs)) / 2 * pt_per_px, (min(ys) + max(ys)) / 2 * pt_per_px]

    after = measure_rooms(client, SAMPLE, plan, reading,
                          corrections=[{"kind": "remove_fixture", "point": point}])
    cleared = measure_rooms(client, SAMPLE, plan, reading, corrections=[])

    count = lambda result: [f.kind for f in result.fixtures].count("toilet")
    assert (count(before), count(after), count(cleared)) == (7, 6, 7)
    assert "No toilet found in this WC" in " ".join(after.rooms[toilet.room].warnings) \
        or after.rooms[toilet.room].room_type != "wc"


# --- picture plans (issue #10) ---------------------------------------------------------

def test_muse_spark_fixture_boxes_land_in_plan_pixels():
    from conformscope.labels import parse_fixtures

    text = json.dumps({"fixtures": [{"kind": "toilet", "x1": 100, "y1": 200, "x2": 150, "y2": 300}]})

    (box,) = parse_fixtures(text, width=1000, height=500)

    assert (box.kind, box.x1, box.y1, box.x2, box.y2) == ("toilet", 100, 100, 150, 150)


def test_each_fixture_box_becomes_its_own_sam_box_object():
    from conformscope.labels import FixtureBox
    from conformscope.segment import box_prompt

    text = box_prompt([FixtureBox("toilet", 10, 10, 40, 30), FixtureBox("placard", 50, 10, 60, 30)], 100, 50)

    assert text == "<0f>0<|box;x1=10;y1=10;x2=40;y2=30;w=100;h=50|>,1<|box;x1=50;y1=10;x2=60;y2=30;w=100;h=50|>"


def _picture_client(fixtures, sam_output=None, sam_error=None):
    """Muse Spark answers by schema; SAM answers both the room and the fixture prompts."""
    from test_segment import SAMPLE as ROOM_MASK
    calls = []

    def chat_create(**kwargs):
        name = kwargs["response_format"]["json_schema"]["name"]
        calls.append(name)
        reply = {"Dimension": {"dimension": {"value_m": 1.0, "x1": 0, "y1": 500, "x2": 100, "y2": 500}},
                 "Fixtures": {"fixtures": fixtures}}[name]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(reply)))])

    def sam_create(**kwargs):
        prompt = kwargs["input"][0]["content"][0]["text"]
        calls.append("sam-box" if "box;" in prompt else "sam-point")
        if "box;" in prompt:
            if sam_error:
                raise sam_error
            return SimpleNamespace(output_text=sam_output or "")
        return SimpleNamespace(output_text=ROOM_MASK)

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
                             responses=SimpleNamespace(create=sam_create))
    return client, calls


def _picture():
    from conformscope.labels import RoomLabel, RoomReading
    from conformscope.plan import Plan
    # The recorded SAM room mask covers x 211-270, y 228-254 on a 320 x 334 picture.
    reading = RoomReading("1:100", [RoomLabel("WC", "wc", 240, 240, None)])
    return Plan(png=b"\x89PNG", width=320, height=334), reading


TOILET_BOX = {"kind": "toilet", "x1": 690, "y1": 690, "x2": 720, "y2": 740}  # inside that room


def test_a_picture_fixture_keeps_muse_spark_box_when_sam_fails():
    from conformscope.rooms import picture_rooms

    plan, reading = _picture()
    client, calls = _picture_client([TOILET_BOX], sam_error=RuntimeError("down"))

    result = picture_rooms(client, plan, reading)

    (fixture,) = result.fixtures
    assert (fixture.kind, fixture.outline_source, fixture.room) == ("toilet", "muse", 0)
    xs, ys = zip(*fixture.polygon_px)
    assert min(xs) == pytest.approx(221, abs=2) and max(xs) == pytest.approx(230, abs=2)
    assert any("SAM 3.1 could not outline the fixtures" in w for w in result.warnings)
    assert result.rooms[0].fixtures == [0]
    assert fixture.space["kind"] == "transfer"


def test_a_sam_mask_replaces_the_muse_spark_box():
    from conformscope.rooms import picture_rooms
    from test_segment import SAMPLE as RECORDED_MASK  # object 0, at x 211-270, y 228-254

    plan, reading = _picture()
    client, calls = _picture_client([TOILET_BOX], sam_output=RECORDED_MASK)

    result = picture_rooms(client, plan, reading)

    (fixture,) = result.fixtures
    assert fixture.outline_source == "sam"
    xs, _ = zip(*fixture.polygon_px)
    assert min(xs) >= 210 and max(xs) > 240  # SAM's outline, wider than the box
    assert calls.count("Fixtures") == 1 and calls.count("sam-box") == 1


def test_a_removed_picture_fixture_is_gone():
    from conformscope.rooms import picture_rooms

    plan, reading = _picture()
    client, _ = _picture_client([TOILET_BOX], sam_error=RuntimeError("down"))

    result = picture_rooms(client, plan, reading,
                           corrections=[{"kind": "remove_fixture", "point": [225, 240]}])

    assert result.fixtures == []
    assert any("No toilet found" in w for w in result.rooms[0].warnings)


def test_more_boxes_than_sam_takes_at_once_are_sent_in_batches():
    from conformscope.rooms import picture_rooms
    from test_segment import SAMPLE as RECORDED_MASK  # object 0 in each batch

    plan, reading = _picture()
    client, calls = _picture_client([TOILET_BOX] * 20, sam_output=RECORDED_MASK)

    result = picture_rooms(client, plan, reading)

    assert calls.count("sam-box") == 2
    sources = [f.outline_source for f in result.fixtures]
    assert sources[0] == "sam" and sources[16] == "sam" and sources.count("muse") == 18
