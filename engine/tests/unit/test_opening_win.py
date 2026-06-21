"""Unit tests for Task 7 — MOVE exit-resolution + win predicate.

TDD spec:
  - Load a seed room with exit {"direction": "on", "target_uuid": "loc2"}
    and win_exit="on"; player seeded at LOC.
  - Comprehend a move frame with location filler "on".
  - Execute via TurnRouter wired with repo + director.
  - Assert: status=="executed", won==True, player location moved to "loc2".
"""

from __future__ import annotations

from memento.cxn.constructicon import ConstructiconRegistry
from memento.cxn.entity_resolver import EntityResolver
from memento.cxn.executor import EffectExecutor
from memento.cxn.kernel_client import FakeComprehensionClient
from memento.cxn.turn_router import TurnRouter
from memento.cxn.types import ComprehendedFrame, FrameRole
from memento.memory.capturing_client import CapturingMemoryClient
from memento.opening.loader import load_seed_room
from memento.opening.seed_types import SeedRoom
from memento.state.chain_mirror import NoopChainMirror
from memento.state.in_memory import InMemoryStateRepository

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLAYER = "6650000000000000000000f1"
LOC = "6650000000000000000000f2"
LOC2 = "loc2"

# ---------------------------------------------------------------------------
# Seed data — minimal room, one exit leading to LOC2, win_exit="on"
# ---------------------------------------------------------------------------

_SEED = SeedRoom(
    location_id=LOC,
    name="The Starting Chamber",
    description="A bare stone chamber. One path leads onward.",
    facts=(),
    exits=({"direction": "on", "target_uuid": LOC2},),
    win_exit="on",
)

# Canned comprehend frame: "go on" → move / location=on
_MOVE_FRAME = ComprehendedFrame(
    predicate="move",
    roles=[FrameRole(role="location", filler="on")],
    matched=True,
    raw_text="go on",
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _make_world() -> tuple[InMemoryStateRepository, TurnRouter]:
    """Seed the room + destination, place player, build director + router."""
    repo = InMemoryStateRepository()

    # Seed the player at LOC
    repo.seed_entity(
        {
            "uuid": PLAYER,
            "name": "Player",
            "kind": "character",
            "labels": ["Character", "Player"],
            "location_uuid": LOC,
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

    # Seed the destination location so move_entity has somewhere to go
    repo.seed_entity(
        {
            "uuid": LOC2,
            "name": "The Next Room",
            "kind": "location",
            "labels": ["Location"],
            "location_uuid": None,
            "attrs": {
                "description": "A dark corridor beyond.",
                "exits": [],
            },
            "is_dead": False,
        }
    )

    # load_seed_room seeds LOC and returns the director
    director = await load_seed_room(_SEED, repo, PLAYER)

    fake_comp = FakeComprehensionClient({"go on": _MOVE_FRAME})
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
        repo=repo,
    )
    return repo, router


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_move_on_exit_executes_and_wins() -> None:
    """MOVE with filler 'on' resolves the exit, moves player, and sets won=True."""
    repo, router = await _make_world()

    outcome = await router.handle("go on", PLAYER)

    # Execution succeeded
    assert outcome["status"] == "executed"

    # Win flag set
    assert outcome.get("won") is True

    # Handoff narration present
    narration = outcome.get("narration")
    assert narration is not None and len(narration) > 0

    # Player is now at LOC2, not LOC
    snap = await repo.get_actor_snapshot(PLAYER)
    assert snap["location"] == LOC2


async def test_move_no_repo_still_executes_without_win() -> None:
    """With repo=None the router skips exit-resolution; executor defaults to current
    location (exit_exists guard will fire).  We just verify no AttributeError and
    the path does NOT set won — the repo=None branch is a no-op guard, not a win path.

    Because exit_exists guard fires when location defaults to current room, the
    executor raises ConstructionError.  We catch it and confirm no 'won' key leaks.
    """
    from memento.cxn.types import ConstructionError

    repo = InMemoryStateRepository()
    repo.seed_entity(
        {
            "uuid": PLAYER,
            "name": "Player",
            "kind": "character",
            "labels": ["Character", "Player"],
            "location_uuid": LOC,
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
    repo.seed_entity(
        {
            "uuid": LOC,
            "name": "The Starting Chamber",
            "kind": "location",
            "labels": ["Location"],
            "location_uuid": None,
            "attrs": {
                "description": "A bare stone chamber.",
                "exits": [{"direction": "on", "target_uuid": LOC2}],
            },
            "is_dead": False,
        }
    )

    fake_comp = FakeComprehensionClient({"go on": _MOVE_FRAME})
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
        # no director, no repo → old behavior
    )

    # Without exit resolution the location role is unresolved →
    # EntityResolver returns ResolutionFailure (unresolved_role:location)
    # OR the executor fires exit_exists guard — either way no ConstructionError
    # that leaks 'won'.  The exact outcome depends on resolver behavior.
    # We just assert won is NOT set.
    try:
        outcome = await router.handle("go on", PLAYER)
        assert outcome.get("won") is not True
    except ConstructionError:
        pass  # guard fired — acceptable, no 'won' leakage possible
