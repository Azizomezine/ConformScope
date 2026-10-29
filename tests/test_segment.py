from types import SimpleNamespace

from conformscope.labels import RoomLabel
from conformscope.plan import Plan
from conformscope.segment import parse_segmentation, point_prompt, segment

# One record exactly as the SAM 3.1 API emits it (from the meta-sam-parser README).
SAMPLE = (
    "<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|>"
    "<|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>\n"
)


def test_masks_are_decoded_where_they_sit_on_the_plan():
    (mask,) = parse_segmentation(SAMPLE)

    assert mask.object_id == "0"
    assert (mask.left, mask.top) == (211, 228)
    assert mask.bits.shape == (27, 60)
    assert 0 < mask.bits.sum() < mask.bits.size


def test_empty_output_means_nothing_found():
    assert parse_segmentation("") == []


def test_each_label_becomes_its_own_point_object():
    labels = [RoomLabel("Séjour", "living", 10, 20), RoomLabel("WC", "wc", 40, 20)]

    text = point_prompt(labels, width=100, height=50)

    assert text == "<0f>0<|point;x=10;y=20;w=100;h=50|>,1<|point;x=40;y=20;w=100;h=50|>"


def test_segment_sends_prompt_and_image_to_sam():
    sent = {}

    def create(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(output_text=SAMPLE)

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    plan = Plan(png=b"\x89PNG", width=320, height=334)

    raw, masks = segment(client, plan, "room")

    assert sent["model"] == "sam-3.1"
    content = sent["input"][0]["content"]
    assert content[0] == {"type": "input_text", "text": "room"}
    assert content[1]["type"] == "input_image"
    assert raw == SAMPLE
    assert len(masks) == 1
