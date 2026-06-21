from memento.opening.seed_types import SeedFact, SeedRoom, FORCED_FIRST


def test_seedfact_defaults_and_forced_first():
    f = SeedFact(
        key="blade", name="an iron blade", kind="item", salience=10, canon=False
    )
    assert f.uuid is None and f.labels == () and f.attrs == {} and f.on_surface is None
    assert FORCED_FIRST > 0


def test_seedroom_holds_facts_and_win_exit():
    f = SeedFact(
        key="body",
        name="a body",
        kind="character",
        salience=FORCED_FIRST,
        canon=True,
        uuid="507f1f77bcf86cd799439011",
        on_surface="die",
    )
    room = SeedRoom(
        location_id="loc1",
        name="the deep roads",
        description="dark",
        facts=(f,),
        exits=({"direction": "on", "target_uuid": "loc2"},),
        win_exit="on",
    )
    assert room.facts[0].on_surface == "die" and room.win_exit == "on"
