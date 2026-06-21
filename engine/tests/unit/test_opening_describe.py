from memento.opening.seed_types import SeedFact
from memento.opening.describe import (
    DescribeRequest,
    TemplateDescribeClient,
    FakeDescribeClient,
)


async def test_template_describer_mentions_focus_and_lists_candidates():
    focus = SeedFact(
        key="body",
        name="a dying adventurer",
        kind="character",
        salience=999,
        canon=True,
    )
    blade = SeedFact(
        key="blade", name="an iron blade", kind="item", salience=10, canon=False
    )
    req = DescribeRequest(
        room_name="the deep roads",
        room_description="Cold stone closes in.",
        focus=focus,
        surfaced=(),
        candidates=(blade,),
    )
    res = await TemplateDescribeClient().describe(req)
    assert "deep roads" in res.prose.lower()
    assert "dying adventurer" in res.prose.lower()
    assert res.candidates == ("an iron blade",)


async def test_fake_describer_returns_canned_for_focus_key():
    focus = SeedFact(
        key="body",
        name="a dying adventurer",
        kind="character",
        salience=999,
        canon=True,
    )
    req = DescribeRequest(
        room_name="r", room_description="d", focus=focus, surfaced=(), candidates=()
    )
    res = await FakeDescribeClient({"body": "Someone is dying here."}).describe(req)
    assert res.prose == "Someone is dying here."
