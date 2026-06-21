from __future__ import annotations

from memento.state.in_memory import InMemoryStateRepository
from memento.opening.seed_types import SeedFact, SeedRoom, FORCED_FIRST
from memento.opening.director import SceneDirector

BODY = "507f1f77bcf86cd799439011"
LOC = "507f1f77bcf86cd799439099"
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
        labels=("Item", "Weapon"),
        attrs={"power": 4},
    )
    return SeedRoom(
        location_id=LOC,
        name="the deep roads",
        description="dark",
        facts=(body, blade),
        exits=({"direction": "on", "target_uuid": "loc2"},),
        win_exit="on",
    )


async def test_surface_order_and_death_beat():
    repo = InMemoryStateRepository()
    repo.seed_entity(
        {
            "uuid": BODY,
            "name": "adventurer",
            "kind": "character",
            "labels": ["Character"],
            "location_uuid": LOC,
            "attrs": {},
            "is_dead": False,
        }
    )
    repo.seed_entity(
        {
            "uuid": PLAYER,
            "name": "you",
            "kind": "character",
            "labels": ["Character"],
            "location_uuid": LOC,
            "attrs": {"inventory": []},
            "is_dead": False,
        }
    )
    d = SceneDirector(_seed(), repo, PLAYER)
    d.register_canon_uuid("body", BODY)
    first = d.next_to_surface()
    assert first is not None and first.key == "body"  # forced-first
    d.mark_surfaced("body")
    await d.apply_surface_beats(first)
    assert (await repo.get_entity(BODY))["is_dead"] is True  # witnessed death
    assert (
        d.next_to_surface() is not None and d.next_to_surface().key == "blade"
    )  # next salient


async def test_find_latent_and_win_predicate():
    repo = InMemoryStateRepository()
    repo.seed_entity(
        {
            "uuid": PLAYER,
            "name": "you",
            "kind": "character",
            "labels": ["Character"],
            "location_uuid": LOC,
            "attrs": {"inventory": []},
            "is_dead": False,
        }
    )
    d = SceneDirector(_seed(), repo, PLAYER)
    found = d.find_latent("the iron blade")
    assert found is not None and found.key == "blade"  # normalized name-match
    assert await d.is_won() is False
    await repo.move_entity(PLAYER, "loc2")
    assert await d.is_won() is True  # left the room
