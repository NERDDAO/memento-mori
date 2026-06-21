"""End-to-end opening arc — three beats through the real turn pipeline.

Beat 1: "look around"  → witnessed death (dying adventurer marked is_dead=True).
Beat 2: "take the iron blade" → controls + lazy materialisation (blade in inventory).
Beat 3: "go on" → cross-the-exit goal (location updated, won=True).

All wired through TurnRouter with FakeComprehensionClient + TemplateDescribeClient;
no LLM, no network, no RNG.
"""

from __future__ import annotations

import pytest

from memento.cxn.constructicon import ConstructiconRegistry
from memento.cxn.entity_resolver import EntityResolver
from memento.cxn.executor import EffectExecutor
from memento.cxn.kernel_client import FakeComprehensionClient
from memento.cxn.types import ComprehendedFrame, FrameRole
from memento.cxn.turn_router import TurnRouter
from memento.memory.capturing_client import CapturingMemoryClient
from memento.opening.deep_roads import (
    NEXT_ROOM,
    UUID_DYING_ADVENTURER,
    deep_roads_seed,
)
from memento.opening.describe import TemplateDescribeClient
from memento.opening.loader import load_seed_room
from memento.state.chain_mirror import NoopChainMirror
from memento.state.in_memory import InMemoryStateRepository

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLAYER = "507f1f77bcf86cd799439020"


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_opening_three_beats_end_to_end() -> None:
    """Drive all three opening beats end-to-end through TurnRouter."""

    # -- Setup ----------------------------------------------------------------
    seed = deep_roads_seed()
    repo = InMemoryStateRepository()

    # Seed the player at the opening room with an empty inventory.
    repo.seed_entity(
        {
            "uuid": PLAYER,
            "name": "you",
            "kind": "character",
            "labels": ["Character"],
            "location_uuid": seed.location_id,
            "attrs": {"inventory": []},
            "is_dead": False,
        }
    )

    # Seed the destination room so MOVE can land (exit_exists guard reads its uuid).
    repo.seed_entity(
        {
            "uuid": NEXT_ROOM,
            "name": "the road on",
            "kind": "location",
            "labels": ["Location"],
            "location_uuid": None,
            "attrs": {"exits": []},
            "is_dead": False,
        }
    )

    # Load seed room (seeds location + canon facts, returns director).
    director = await load_seed_room(seed, repo, PLAYER)

    # -- Wire -----------------------------------------------------------------
    resolver = EntityResolver(repo, director)
    executor = EffectExecutor(repo, CapturingMemoryClient(), NoopChainMirror())

    canned: dict[str, ComprehendedFrame] = {
        "look around": ComprehendedFrame(
            predicate="look",
            roles=[],
            matched=True,
            raw_text="look around",
        ),
        "take the iron blade": ComprehendedFrame(
            predicate="take",
            roles=[FrameRole(role="patient", filler="the iron blade")],
            matched=True,
            raw_text="take the iron blade",
        ),
        "go on": ComprehendedFrame(
            predicate="move",
            roles=[FrameRole(role="location", filler="on")],
            matched=True,
            raw_text="go on",
        ),
    }
    comprehension = FakeComprehensionClient(canned)
    router = TurnRouter(
        comprehension,
        ConstructiconRegistry(),
        resolver,
        executor,
        "mm-world-v1",
        director=director,
        describe_client=TemplateDescribeClient(),
        repo=repo,
    )

    # -- BEAT 1: witnessed death ----------------------------------------------
    look = await router.handle("look around", PLAYER)
    assert look["status"] == "narrated", f"Expected narrated, got: {look}"
    assert "dying" in look["narration"].lower(), (
        f"Expected 'dying' in narration, got: {look['narration']!r}"
    )

    # The on_surface="die" beat fires immediately on first LOOK (FORCED_FIRST salience).
    dying_doc = await repo.get_entity(UUID_DYING_ADVENTURER)
    assert dying_doc is not None, "dying adventurer entity not found"
    assert dying_doc["is_dead"] is True, (
        f"dying adventurer should be marked dead after LOOK; got is_dead={dying_doc['is_dead']}"
    )

    # -- BEAT 2: controls + lazy materialise ----------------------------------
    take = await router.handle("take the iron blade", PLAYER)
    assert take["status"] == "executed", (
        f"Expected executed, got: {take.get('status')!r} — reason: {take.get('reason')!r}"
    )

    # get_actor_snapshot inventory holds UUIDs; resolve each to check name.
    snap = await repo.get_actor_snapshot(PLAYER)
    inventory_uuids: list[str] = snap.get("inventory", [])
    assert inventory_uuids, "Player inventory is empty after TAKE"
    inventory_docs = [await repo.get_entity(uid) for uid in inventory_uuids]
    assert any(
        "blade" in (doc.get("name", "") if doc else "") for doc in inventory_docs
    ), (
        f"Expected 'blade' in an inventory item name; got: "
        f"{[d.get('name') if d else None for d in inventory_docs]}"
    )

    # -- BEAT 3: cross-the-exit goal ------------------------------------------
    go = await router.handle("go on", PLAYER)
    assert go["status"] == "executed", (
        f"Expected executed, got: {go.get('status')!r} — reason: {go.get('reason')!r}"
    )
    assert go.get("won") is True, (
        f"Expected won=True after crossing the exit; got: {go.get('won')!r}"
    )

    final_snap = await repo.get_actor_snapshot(PLAYER)
    assert final_snap["location"] == seed.exits[0]["target_uuid"], (
        f"Expected player at {seed.exits[0]['target_uuid']!r}, "
        f"got {final_snap['location']!r}"
    )
