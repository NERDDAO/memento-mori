from __future__ import annotations


from memento.state.in_memory import InMemoryStateRepository
from memento.opening.seed_types import SeedFact, SeedRoom, FORCED_FIRST
from memento.opening.director import SceneDirector
from memento.opening.loader import load_seed_room

BODY = "507f1f77bcf86cd799439011"
LOC = "507f1f77bcf86cd799439099"
BLADE = "507f1f77bcf86cd7994390bb"
PLAYER = "507f1f77bcf86cd7994390aa"


def _seed() -> SeedRoom:
    body = SeedFact(
        key="body",
        name="a dying adventurer",
        kind="character",
        salience=FORCED_FIRST,
        canon=True,
        uuid=BODY,
        labels=("Character",),
        on_surface="die",
    )
    blade = SeedFact(
        key="blade",
        name="an iron blade",
        kind="item",
        salience=10,
        canon=False,
        uuid=BLADE,
        labels=("Item", "Weapon"),
        attrs={"power": 4},
    )
    return SeedRoom(
        location_id=LOC,
        name="the deep roads",
        description="dark tunnels",
        facts=(body, blade),
        exits=({"direction": "on", "target_uuid": "loc2"},),
        win_exit="on",
    )


async def test_load_seed_room():
    repo = InMemoryStateRepository()
    seed = _seed()

    director = await load_seed_room(seed, repo, PLAYER)

    # 1. Location entity exists with correct attrs["exits"]
    loc_doc = await repo.get_entity(LOC)
    assert loc_doc is not None
    assert loc_doc["kind"] == "location"
    assert loc_doc["attrs"]["exits"] == [{"direction": "on", "target_uuid": "loc2"}]
    assert loc_doc["attrs"]["description"] == "dark tunnels"

    # 2. Canon body entity exists at location
    body_doc = await repo.get_entity(BODY)
    assert body_doc is not None
    assert body_doc["kind"] == "character"
    assert body_doc["location_uuid"] == LOC

    # 3. Latent blade is NOT seeded into the repository
    blade_doc = await repo.get_entity(BLADE)
    assert blade_doc is None

    # 4. entities_at_location contains BODY but NOT the blade UUID
    entities = await repo.get_entities_at_location(LOC)
    entity_uuids = {e["uuid"] for e in entities}
    assert BODY in entity_uuids
    assert BLADE not in entity_uuids

    # 5. Returned director surfaces the canon body fact first
    assert isinstance(director, SceneDirector)
    next_fact = director.next_to_surface()
    assert next_fact is not None
    assert next_fact.key == "body"
