import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from conformscope.labels import Dimension, RoomLabel, parse_rooms
from conformscope.plan import load_plan
from conformscope.rooms import (
    PT_PER_M_AT_1_TO_1,
    measure_rooms,
    outline,
    picture_px_per_m,
    resolve_type,
    scale_pt_per_m,
    type_from_name,
    written_areas,
)
from test_labels import RECORDED

SAMPLE = Path(__file__).parents[1] / "samples" / "private" / "Plan_Logement_Niveau_02.pdf"
# The areas written on that plan, read off its text layer.
WRITTEN = [15.31, 10.09, 16.70, 15.55, 16.14, 13.44, 17.44, 19.72]


@pytest.mark.parametrize("text, expected", [
    ("1:100", PT_PER_M_AT_1_TO_1 / 100),
    ("1/50", PT_PER_M_AT_1_TO_1 / 50),
    ("Scale 1.100", PT_PER_M_AT_1_TO_1 / 100),
    ("1 : 200", PT_PER_M_AT_1_TO_1 / 200),
    (None, None),
    ("not to scale", None),
])
def test_written_scale_becomes_points_per_metre(text, expected):
    assert scale_pt_per_m(text) == expected


def test_one_to_hundred_is_28_35_points_per_metre():
    assert scale_pt_per_m("1:100") == pytest.approx(28.35, abs=0.01)


def test_a_rectangle_mask_becomes_its_polygon_in_pixels_and_metres():
    mask = np.zeros((40, 120), bool)
    mask[10:30, 20:120] = True  # 100 x 20 px

    polygon_px, polygon_m, area_m2 = outline(mask, origin=(5, 7), px_per_m=50, to_plan=2.0)

    assert area_m2 == pytest.approx(0.8, rel=0.03)  # 2 m x 0.4 m
    xs, ys = zip(*polygon_m)
    assert min(xs) == pytest.approx(0.5, abs=0.03) and max(xs) == pytest.approx(2.5, abs=0.03)
    assert min(ys) == pytest.approx(0.34, abs=0.03) and max(ys) == pytest.approx(0.74, abs=0.03)
    pxs, _ = zip(*polygon_px)
    assert min(pxs) == pytest.approx(50, abs=2) and max(pxs) == pytest.approx(250, abs=2)


@pytest.mark.parametrize("name, expected", [
    ("Chambre 2", "bedroom"),
    ("Bedroom", "bedroom"),
    ("Séjour / Cuisine", "living"),
    ("Cuisine", "kitchen"),
    ("SDB", "bathroom"),
    ("Salle d'eau", "bathroom"),
    ("WC", "wc"),
    ("Dégagement", "corridor"),
    ("Entrée", "entrance"),
    ("PL", "storage"),
    ("Cellier", "storage"),
    ("RWDP", None),
    ("", None),
])
def test_type_from_the_name_written_in_the_room(name, expected):
    assert type_from_name(name) == expected


def test_a_written_name_beats_the_toilet_and_muse_spark():
    assert resolve_type("bathroom", has_toilet=True, muse_type="wc") == ("bathroom", "text", [])


def test_a_toilet_types_an_unnamed_room_as_a_wc():
    assert resolve_type(None, has_toilet=True, muse_type="wc") == ("wc", "fixture", [])


def test_a_toilet_agrees_with_muse_spark_calling_it_a_bathroom():
    assert resolve_type(None, has_toilet=True, muse_type="bathroom") == ("bathroom", "fixture", [])


def test_the_toilet_wins_over_muse_spark_with_a_warning():
    room_type, source, warnings = resolve_type(None, has_toilet=True, muse_type="bedroom")

    assert (room_type, source) == ("wc", "fixture")
    assert warnings == ["A toilet is drawn here, but Muse Spark read it as bedroom"]


def test_muse_spark_types_what_nothing_else_can():
    assert resolve_type(None, has_toilet=False, muse_type="corridor") == ("corridor", "muse", [])


def test_a_room_nothing_can_type_stays_other():
    assert resolve_type(None, has_toilet=False, muse_type=None) == ("other", "none", [])


def _label(area_m2, x=0, y=0):
    return RoomLabel("Room", "bedroom", x, y, area_m2)


def test_picture_scale_prefers_a_written_dimension():
    dimension = Dimension(value_m=3.4, x1=100, y1=50, x2=440, y2=50)

    assert picture_px_per_m(dimension, [], []) == (100.0, "cote")


def test_picture_scale_falls_back_to_the_median_of_the_written_areas():
    # 10 m² at 50 px/m is 25 000 px; the odd one out does not move the median.
    labels = [_label(10.0), _label(12.0), _label(20.0)]
    mask_px = [25_000, 30_000, 20_000]

    px_per_m, source = picture_px_per_m(None, labels, mask_px)

    assert source == "from_areas"
    assert px_per_m == pytest.approx(50.0)


def test_picture_scale_needs_two_written_areas():
    assert picture_px_per_m(None, [_label(10.0), _label(None)], [25_000, 9_000]) == (None, None)


def _fake_client(types_reply):
    """Muse Spark answers the room-typing call; nothing else should be asked."""
    calls = []

    def chat_create(**kwargs):
        calls.append(kwargs["response_format"]["json_schema"]["name"])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=types_reply))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)))
    return client, calls


@pytest.mark.skipif(not SAMPLE.exists(), reason="private sample plan not present")
def test_sample_plan_bedrooms_are_measured_close_to_their_written_areas():
    plan = load_plan(SAMPLE)
    reading = parse_rooms(RECORDED, plan.width, plan.height)
    client, calls = _fake_client(json.dumps({"rooms": []}))

    result = measure_rooms(client, SAMPLE, plan, reading)

    assert result.scale_source == "measured"
    assert any("1:100" in w for w in result.warnings)  # the dimension lines disagree with 1:100
    assert calls == ["RoomTypes"]
    bedrooms = [r for r in result.rooms if r.type_source == "text"]
    assert [r.written_area_m2 for r in bedrooms] == WRITTEN
    errors = [abs(r.area_m2 - r.written_area_m2) / r.written_area_m2 for r in bedrooms]
    # Six of the eight within 5 %; the 10.09 and 15.31 rooms open onto the landing through
    # gaps no door arc closes, and come out short.
    assert sum(e <= 0.05 for e in errors) >= 6
    unnamed = [r for r in result.rooms if r.type_source != "text"]
    assert len(unnamed) >= 10
    assert any(r.room_type == "wc" and r.type_source == "fixture" for r in unnamed)
    for room in result.rooms:
        assert len(room.polygon_m) >= 3
        assert room.circle_m > 0


def _picture_client(dimension):
    from test_segment import SAMPLE as SAM_OUTPUT

    def chat_create(**kwargs):
        content = json.dumps({"dimension": dimension})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
        responses=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(output_text=SAM_OUTPUT)),
    )


def _picture_plan():
    from conformscope.plan import Plan
    return Plan(png=b"\x89PNG", width=320, height=334)


def test_a_picture_room_is_the_sam_mask_scaled_by_a_written_dimension():
    from conformscope.labels import RoomReading
    from conformscope.rooms import picture_rooms

    # 1 m written along 100 of 1000 across a 320 px picture: 32 px per metre.
    dimension = {"value_m": 1.0, "x1": 0, "y1": 500, "x2": 100, "y2": 500}
    reading = RoomReading("1:100", [RoomLabel("Chambre", "bedroom", 160, 160, 12.0)])

    result = picture_rooms(_picture_client(dimension), _picture_plan(), reading)

    assert (result.kind, result.scale_source) == ("picture", "cote")
    assert result.px_per_m == pytest.approx(32.0)
    (room,) = result.rooms
    assert room.name == "Chambre" and room.room_type == "bedroom"
    assert room.area_m2 > 0 and room.written_area_m2 == 12.0
    assert len(room.polygon_m) >= 3


def test_a_picture_with_nothing_to_scale_by_keeps_its_outline_without_metres():
    from conformscope.labels import RoomReading
    from conformscope.rooms import picture_rooms

    reading = RoomReading(None, [RoomLabel("Chambre", "bedroom", 160, 160, None)])

    result = picture_rooms(_picture_client(None), _picture_plan(), reading)

    (room,) = result.rooms
    assert room.area_m2 is None and room.polygon_m == [] and room.polygon_px
    assert any("by hand" in w for w in result.warnings)


def _word(text, x0, y0=100.0):
    return (x0, y0, x0 + 8, y0 + 4, text, 0, 0, 0)


def test_written_areas_are_a_number_followed_by_square_metres():
    words = [_word("Bedroom", 10), _word("16.14", 10, 104), _word("m�", 19, 104),
             _word("12,5", 50), _word("m²", 59), _word("9.8m2", 90)]

    assert [(a, round(x), round(y)) for a, x, y in written_areas(words)] == [
        (16.14, 14, 106), (12.5, 54, 102), (9.8, 94, 102)]


def test_a_dimension_in_metres_is_not_an_area():
    assert written_areas([_word("0.91", 10), _word("m", 19), _word("3.40", 40)]) == []


@pytest.mark.skipif(not SAMPLE.exists(), reason="private sample plan not present")
def test_the_text_layer_beats_an_area_muse_spark_misread():
    plan = load_plan(SAMPLE)
    reading = parse_rooms(RECORDED, plan.width, plan.height)
    # Live Muse Spark read 15.31 as 10.35, 10.09 as 12.0 and 15.55 as 10.55.
    misread = {15.31: 10.35, 10.09: 12.0, 15.55: 10.55}
    reading.rooms[:] = [replace(r, area_m2=misread.get(r.area_m2, r.area_m2)) for r in reading.rooms]
    client, _ = _fake_client(json.dumps({"rooms": []}))

    result = measure_rooms(client, SAMPLE, plan, reading)

    assert [r.written_area_m2 for r in result.rooms if r.type_source == "text"] == WRITTEN
