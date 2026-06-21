"""Unit tests for Task 5 — LOOK construction + read-only describe branch.

TDD spec:
  - Build TurnRouter with FakeComprehensionClient, a loaded SceneDirector
    (via load_seed_room), and FakeDescribeClient.
  - First look → status=="narrated", prose contains the focus key's canned
    text, and the witnessed-death beat fires (BODY is_dead True).
  - Second look → surfaces the next fact (no re-death; BODY stays dead once).
  - No director / no describe_client → clarify/no_scene outcome.
"""

from __future__ import annotations


from memento.cxn.constructicon import ConstructiconRegistry
from memento.cxn.entity_resolver import EntityResolver
from memento.cxn.executor import EffectExecutor
from memento.cxn.kernel_client import FakeComprehensionClient
from memento.cxn.turn_router import TurnRouter
from memento.cxn.types import ComprehendedFrame
from memento.memory.capturing_client import CapturingMemoryClient
from memento.opening.describe import FakeDescribeClient
from memento.opening.loader import load_seed_room
from memento.opening.seed_types import SeedFact, SeedRoom
from memento.state.chain_mirror import NoopChainMirror
from memento.state.in_memory import InMemoryStateRepository

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLAYER = "6650000000000000000000a1"
LOCATION_ID = "6650000000000000000000c9"
BODY_UUID = "6650000000000000000000d1"
LANTERN_UUID = "6650000000000000000000d2"  # a second latent fact

# ---------------------------------------------------------------------------
# Seed data — one canon character (the dying adventurer) + one latent item
# ---------------------------------------------------------------------------

_SEED = SeedRoom(
    location_id=LOCATION_ID,
    name="The Threshold",
    description="A dim antechamber at the edge of darkness.",
    facts=(
        SeedFact(
            key="body",
            name="dying adventurer",
            kind="character",
            salience=100,
            canon=True,
            uuid=BODY_UUID,
            labels=("Character",),
            attrs={},
            on_surface="die",
        ),
        SeedFact(
            key="lantern",
            name="tarnished lantern",
            kind="item",
            salience=50,
            canon=False,
            uuid=None,
            labels=("Item",),
            attrs={},
            on_surface=None,
        ),
    ),
    exits=({"direction": "north", "target_uuid": "6650000000000000000000c8"},),
    win_exit="north",
)

# Canned describe responses keyed by focus.key (or "" for no focus)
_DESCRIBE_CANNED = {
    "body": "A dying adventurer lies before you.",
    "lantern": "A tarnished lantern glows faintly on the floor.",
    "": "The antechamber is silent.",
}

# Canned comprehend frame for "look around"
_LOOK_FRAME = ComprehendedFrame(
    predicate="look",
    roles=[],
    matched=True,
    raw_text="look around",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_world() -> tuple[InMemoryStateRepository, TurnRouter]:
    """Seed the room, build director, build router."""
    repo = InMemoryStateRepository()
    # Seed the player into the room so snapshot resolves correctly
    repo.seed_entity(
        {
            "uuid": PLAYER,
            "name": "Player",
            "kind": "character",
            "labels": ["Character", "Player"],
            "location_uuid": LOCATION_ID,
            "attrs": {
                "hp": 20,
                "max_hp": 20,
                "strength": 1,
                "armor": 0,
                "inventory": [],
                "equipped": {},
            },
            "is_dead": False,
        }
    )

    director = await load_seed_room(_SEED, repo, PLAYER)

    fake_comp = FakeComprehensionClient({"look around": _LOOK_FRAME})
    fake_desc = FakeDescribeClient(_DESCRIBE_CANNED)
    mem = CapturingMemoryClient()

    constructicon = ConstructiconRegistry()
    resolver = EntityResolver(repo)
    executor = EffectExecutor(repo=repo, memory=mem, chain=NoopChainMirror())

    router = TurnRouter(
        comprehension=fake_comp,
        constructicon=constructicon,
        resolver=resolver,
        executor=executor,
        bonfire_id="mm-world-v1",
        director=director,
        describe_client=fake_desc,
    )
    return repo, router


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_look_first_surfaces_body_and_fires_death_beat() -> None:
    """First LOOK → narrated; dying adventurer prose; BODY is_dead set to True."""
    repo, router = await _make_world()

    outcome = await router.handle("look around", PLAYER)

    assert outcome["status"] == "narrated"
    narration = outcome["narration"]
    assert narration is not None
    assert "dying adventurer" in narration

    # Death beat must have fired
    body = await repo.get_entity(BODY_UUID)
    assert body is not None
    assert body["is_dead"] is True


async def test_look_second_surfaces_next_fact_no_redeath() -> None:
    """Second LOOK surfaces the next-salience fact; death beat not re-triggered."""
    repo, router = await _make_world()

    # First look — surfaces 'body'
    await router.handle("look around", PLAYER)

    # Confirm dead
    body_after_first = await repo.get_entity(BODY_UUID)
    assert body_after_first is not None
    assert body_after_first["is_dead"] is True

    # Second look — surfaces 'lantern' (next by salience)
    outcome2 = await router.handle("look around", PLAYER)

    assert outcome2["status"] == "narrated"
    narration2 = outcome2["narration"]
    assert narration2 is not None
    assert "lantern" in narration2

    # Body still dead, not touched again (idempotent)
    body_after_second = await repo.get_entity(BODY_UUID)
    assert body_after_second is not None
    assert body_after_second["is_dead"] is True


async def test_look_no_director_returns_clarify_no_scene() -> None:
    """Router with no director → clarify / no_scene."""
    fake_comp = FakeComprehensionClient({"look around": _LOOK_FRAME})
    mem = CapturingMemoryClient()
    repo = InMemoryStateRepository()

    constructicon = ConstructiconRegistry()
    resolver = EntityResolver(repo)
    executor = EffectExecutor(repo=repo, memory=mem, chain=NoopChainMirror())

    router = TurnRouter(
        comprehension=fake_comp,
        constructicon=constructicon,
        resolver=resolver,
        executor=executor,
        bonfire_id="mm-world-v1",
        # no director, no describe_client
    )

    outcome = await router.handle("look around", PLAYER)

    assert outcome["status"] == "clarify"
    assert outcome["reason"] == "no_scene"
    assert outcome["message"] == "There is nothing to perceive."
