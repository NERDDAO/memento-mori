"""Integration parity proof — three opening beats through EventSourcedStateRepository.

Drives the same three beats as test_opening_arc.py:
  Beat 1: "look around"  → witnessed death (dying adventurer marked is_dead=True)
  Beat 2: "take the iron blade" → lazy materialisation (blade in inventory)
  Beat 3: "go on" → cross-the-exit goal (location updated, won=True)

But wired against the EventSourced stack (TxLog + ActivationLog + KgProjectionFake).

Assertions (all load-bearing — the integration parity proof):
  1. Projection state — adventurer dead, blade carried, player at NEXT_ROOM, won=True.
  2. Tx Log holds cxn-stamped txs — non-"genesis" activation_id on player-driven writes.
  3. Activation join — tx activation_id joins to an ActivationRecord with message_id set.
  4. Rebuild reproduces state — rebuild_projection(PLAYER) yields same location/is_dead.
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
from memento.state.event_sourced import EventSourcedStateRepository
from memento.state.kg_projection import KgProjectionFake
from memento.state.tx_log import InMemoryActivationLog, InMemoryTxLog

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLAYER = "507f1f77bcf86cd799439020"


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_opening_three_beats_event_sourced() -> None:
    """Drive all three opening beats against EventSourcedStateRepository.

    Proves:
      1. Projection state matches expected post-beat values.
      2. Tx Log holds cxn-stamped txs (non-genesis activation_id).
      3. Activation join works — tx.activation_id → ActivationRecord.message_id.
      4. rebuild_projection(PLAYER) reproduces the live projection state.
    """

    # -- Setup: EventSourced stack -------------------------------------------
    tx_log = InMemoryTxLog()
    activation_log = InMemoryActivationLog()
    projection = KgProjectionFake()
    mirror = NoopChainMirror()
    repo = EventSourcedStateRepository(
        tx_log=tx_log,
        activation_log=activation_log,
        projection=projection,
        chain=mirror,
    )

    seed = deep_roads_seed()

    # Seed the player at the opening room.
    await repo.seed_entity(
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

    # Seed the destination room so MOVE can land.
    await repo.seed_entity(
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
    executor = EffectExecutor(repo, CapturingMemoryClient(), mirror)

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
        activation_log=activation_log,
    )

    # -- BEAT 1: witnessed death ----------------------------------------------
    look = await router.handle("look around", PLAYER)
    assert look["status"] == "narrated", f"Expected narrated, got: {look}"
    assert "dying" in look["narration"].lower(), (
        f"Expected 'dying' in narration, got: {look['narration']!r}"
    )

    # The on_surface="die" beat fires on first LOOK (FORCED_FIRST salience).
    dying_doc = await repo.get_entity(UUID_DYING_ADVENTURER)
    assert dying_doc is not None, "dying adventurer entity not found"
    assert dying_doc["is_dead"] is True, (
        f"dying adventurer should be marked dead after LOOK; "
        f"got is_dead={dying_doc['is_dead']}"
    )

    # -- BEAT 2: controls + lazy materialise ----------------------------------
    take = await router.handle("take the iron blade", PLAYER)
    assert take["status"] == "executed", (
        f"Expected executed, got: {take.get('status')!r} — reason: {take.get('reason')!r}"
    )

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

    # =========================================================================
    # Assertion 1 — Projection state (complete)
    # =========================================================================

    # 1a. Dying adventurer is dead in the projection.
    adv_doc = await repo.get_entity(UUID_DYING_ADVENTURER)
    assert adv_doc is not None, "dying adventurer not in projection"
    assert adv_doc["is_dead"] is True, (
        f"dying adventurer projection is_dead should be True; got {adv_doc['is_dead']}"
    )

    # 1b. Player is at NEXT_ROOM.
    player_doc = await repo.get_entity(PLAYER)
    assert player_doc is not None
    assert player_doc["location_uuid"] == NEXT_ROOM, (
        f"Player location_uuid should be {NEXT_ROOM!r}; got {player_doc['location_uuid']!r}"
    )

    # 1c. Blade is in player inventory (carried).
    blade_uuid = inventory_uuids[0]
    blade_doc = await repo.get_entity(blade_uuid)
    assert blade_doc is not None, "blade entity not found in projection"
    assert "blade" in blade_doc.get("name", "").lower(), (
        f"Expected blade name; got {blade_doc.get('name')!r}"
    )
    # The item's owner_uuid points to the player (carried, not on floor).
    assert blade_doc.get("owner_uuid") == PLAYER or PLAYER in player_doc.get("attrs", {}).get(
        "inventory", []
    ), "Blade should be owned by player or in inventory"

    # =========================================================================
    # Assertion 2 — Tx Log holds cxn-stamped txs (non-empty, non-genesis)
    # =========================================================================

    player_entries = tx_log.for_actor(PLAYER)
    # Must have at least the genesis seed entry + entries from the three beats.
    assert len(player_entries) >= 2, (
        f"Expected at least 2 tx entries for PLAYER; got {len(player_entries)}"
    )
    # All player-driven writes (non-genesis) must have a non-empty, non-genesis activation_id.
    non_genesis_player = [e for e in player_entries if e.activation_id != "genesis"]
    assert non_genesis_player, (
        "Expected at least one non-genesis TxEntry for PLAYER (from MOVE beat)"
    )
    for entry in non_genesis_player:
        assert entry.activation_id, (
            f"activation_id is empty on TxEntry {entry.tx_id}"
        )
        assert entry.activation_id != "genesis", (
            f"Expected non-genesis activation_id; got 'genesis' on {entry.tx_id}"
        )

    # The dying adventurer should also have a non-genesis stamped write (die beat).
    adv_entries = tx_log.for_actor(UUID_DYING_ADVENTURER)
    non_genesis_adv = [e for e in adv_entries if e.activation_id != "genesis"]
    assert non_genesis_adv, (
        "Expected at least one non-genesis TxEntry for dying adventurer (die beat)"
    )

    # =========================================================================
    # Assertion 3 — Activation join: tx.activation_id → ActivationRecord
    # =========================================================================

    # Pick the MOVE tx (last non-genesis player entry — the "go on" beat).
    move_tx = non_genesis_player[-1]
    move_activation_id = move_tx.activation_id

    joined = activation_log.join(move_activation_id)
    assert joined is not None, (
        f"activation_log.join({move_activation_id!r}) returned None; "
        f"no matching ActivationRecord — the two logs are not joinable"
    )
    assert joined.message_id, (
        f"ActivationRecord.message_id is empty for activation {move_activation_id!r}"
    )
    assert joined.actor_id == PLAYER, (
        f"Expected actor_id={PLAYER!r} on ActivationRecord; got {joined.actor_id!r}"
    )

    # =========================================================================
    # Assertion 4 — Rebuild reproduces state (THE event-sourcing proof)
    # =========================================================================

    rebuilt = await repo.rebuild_projection(PLAYER)

    # 4a. Rebuilt player doc has same location_uuid.
    rebuilt_player = await rebuilt.get(PLAYER)
    assert rebuilt_player is not None, "rebuild_projection: PLAYER not in rebuilt projection"
    assert rebuilt_player["location_uuid"] == NEXT_ROOM, (
        f"Rebuilt projection: expected location_uuid={NEXT_ROOM!r}; "
        f"got {rebuilt_player['location_uuid']!r}"
    )

    # 4b. The player's inventory in rebuilt projection includes the blade.
    rebuilt_inventory: list[str] = rebuilt_player.get("attrs", {}).get("inventory", [])
    assert rebuilt_inventory, (
        "Rebuilt projection: player inventory is empty — rebuild missed TAKE tx"
    )
    assert blade_uuid in rebuilt_inventory, (
        f"Rebuilt projection: blade {blade_uuid!r} not in rebuilt inventory {rebuilt_inventory}"
    )

    # 4c. Rebuild also reproduces dying adventurer state (if we rebuild from adv log).
    rebuilt_adv_proj = await repo.rebuild_projection(UUID_DYING_ADVENTURER)
    rebuilt_adv = await rebuilt_adv_proj.get(UUID_DYING_ADVENTURER)
    assert rebuilt_adv is not None, (
        "rebuild_projection(UUID_DYING_ADVENTURER): entity missing from rebuilt projection"
    )
    assert rebuilt_adv["is_dead"] is True, (
        f"Rebuilt projection: dying adventurer is_dead should be True; "
        f"got {rebuilt_adv['is_dead']}"
    )
