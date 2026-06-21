"""Unit tests for lazy materialization (Task 6).

When a player reaches for a latent fact (not yet in the world), the EntityResolver
promotes it into a real persistent entity on the spot — "take the torch is what
makes the torch exist".

Scenario:
- LOC is seeded as a location.
- PLAYER is seeded at LOC.
- A latent blade SeedFact (kind="item", not yet in the repo) exists in the director.
- Resolver is built with director=<director>; TAKE frame with patient="the iron blade".
- Resolution succeeds: returns a UUID string (not a ResolutionFailure).
- The entity is now in the repo at LOC with labels including "Item".
- The director records the fact as materialized.

Control case: resolver with director=None returns unresolved_role:patient.
"""

from __future__ import annotations

from memento.cxn.definitions import TAKE_CXN
from memento.cxn.entity_resolver import EntityResolver
from memento.cxn.types import ComprehendedFrame
from memento.opening.director import SceneDirector
from memento.opening.seed_types import FORCED_FIRST, SeedFact, SeedRoom
from memento.state.in_memory import InMemoryStateRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

LOC = "507f1f77bcf86cd799439099"
PLAYER = "507f1f77bcf86cd7994390aa"
BODY = "507f1f77bcf86cd799439011"


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


def _make_repo() -> InMemoryStateRepository:
    repo = InMemoryStateRepository()
    # Location
    repo.seed_entity(
        {
            "uuid": LOC,
            "name": "The Deep Roads",
            "kind": "location",
            "labels": ["Location"],
            "location_uuid": None,
            "attrs": {"exits": [{"direction": "on", "target_uuid": "loc2"}]},
            "is_dead": False,
        }
    )
    # Player at LOC
    repo.seed_entity(
        {
            "uuid": PLAYER,
            "name": "you",
            "kind": "character",
            "labels": ["Character", "Player"],
            "location_uuid": LOC,
            "attrs": {"inventory": []},
            "is_dead": False,
        }
    )
    # Body (canon entity already seeded)
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
    return repo


def _take_frame(filler: str) -> ComprehendedFrame:
    return {
        "predicate": "take",
        "roles": [{"role": "patient", "filler": filler}],
        "matched": True,
        "raw_text": f"take {filler}",
    }


# ---------------------------------------------------------------------------
# Test: promote-on-miss when director is wired
# ---------------------------------------------------------------------------


async def test_materialize_latent_item_on_take() -> None:
    """TAKE patient='the iron blade' promotes the latent blade into the world."""
    repo = _make_repo()
    seed = _seed()
    director = SceneDirector(seed, repo, PLAYER)
    director.register_canon_uuid("body", BODY)

    resolver = EntityResolver(repo, director=director)
    frame = _take_frame("the iron blade")

    result = await resolver.resolve(frame, PLAYER, TAKE_CXN)

    # Resolution must succeed: return a UUID string, not a failure dict
    assert isinstance(result, dict), f"Expected dict, got {result!r}"
    assert "reason" not in result, f"Got failure: {result}"
    assert "patient" in result, f"Missing patient key in {result}"

    uuid = result["patient"]
    assert isinstance(uuid, str) and len(uuid) > 0

    # Entity now exists in the repo at LOC
    entity = await repo.get_entity(uuid)
    assert entity is not None, f"Entity {uuid!r} not found after materialization"
    assert entity["location_uuid"] == LOC
    assert "Item" in entity["labels"], f"Expected 'Item' in labels: {entity['labels']}"

    # Director records it as materialized: find_latent returns None now
    assert director.find_latent("the iron blade") is None, (
        "Expected blade to be marked materialized"
    )


# ---------------------------------------------------------------------------
# Control: director=None still returns unresolved_role:patient
# ---------------------------------------------------------------------------


async def test_no_director_still_returns_unresolved() -> None:
    """Without a director wired, an absent patient returns the standard failure."""
    repo = _make_repo()
    resolver = EntityResolver(repo)  # director=None (default)

    frame = _take_frame("the iron blade")

    result = await resolver.resolve(frame, PLAYER, TAKE_CXN)

    assert isinstance(result, dict)
    assert "reason" in result
    assert result["reason"] == "unresolved_role:patient"
