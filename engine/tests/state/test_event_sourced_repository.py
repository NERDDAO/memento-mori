"""Tests for EventSourcedStateRepository.

TDD gate:
    cd engine && python -m pytest tests/state/test_event_sourced_repository.py -q

Covers:
  Parity tests (EventSourced vs InMemory return identical results):
    - move_entity return value
    - set_attr return value (attrs field + is_dead top-level)
    - materialize return value
    - transfer_item return value (pickup, drop-to-floor)
    - link / unlink (attrs["links"] reflected in get_entity)
    - get_actor_snapshot after a move

  Tx log tests:
    - each write appends exactly one TxEntry stamped with current activation_id
    - genesis seed writes use activation_id="genesis"
    - set_activation changes the stamp for subsequent writes

  ChainMirror tests:
    - set_attr(is_dead=True) fires on_character_death
    - set_attr(is_dead=False) does NOT fire on_character_death
    - transfer_item to a new owner fires on_item_transferred
    - transfer_item to floor (to_uuid=None) does NOT fire on_item_transferred

  rebuild_projection:
    - after a sequence of writes, rebuild_projection reproduces the live projection
      (get + entities_at_location agree)
"""
from __future__ import annotations

import copy
from typing import Any

import pytest

from memento.state.chain_mirror import NoopChainMirror
from memento.state.event_sourced import EventSourcedStateRepository
from memento.state.in_memory import InMemoryStateRepository
from memento.state.kg_projection import KgProjectionFake
from memento.state.repository import EntityDoc, ItemDoc
from memento.state.tx_log import InMemoryActivationLog, InMemoryTxLog

# ---------------------------------------------------------------------------
# Test-only ChainMirror that records calls
# ---------------------------------------------------------------------------


class RecordingChainMirror:
    """Records invocations so tests can assert on them."""

    def __init__(self) -> None:
        self.death_calls: list[dict[str, Any]] = []
        self.transfer_calls: list[dict[str, Any]] = []

    def on_character_death(
        self, character_id: str, cause: str, location_id: str, tick: int
    ) -> None:
        self.death_calls.append(
            dict(character_id=character_id, cause=cause, location_id=location_id, tick=tick)
        )

    def on_item_transferred(self, item_id: str, new_owner_id: str) -> None:
        self.transfer_calls.append(dict(item_id=item_id, new_owner_id=new_owner_id))


# ---------------------------------------------------------------------------
# Stable fixture UUIDs
# ---------------------------------------------------------------------------

LOC_A = "loc-uuid-aaaa"
LOC_B = "loc-uuid-bbbb"
CHAR_1 = "char-uuid-0001"
NPC_1 = "npc-uuid-0001"
ITEM_1 = "item-uuid-0001"
ITEM_2 = "item-uuid-0002"
ACT_1 = "act-uuid-0001"
ACT_2 = "act-uuid-0002"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _location(uuid: str, exits: list[dict[str, Any]] | None = None) -> EntityDoc:
    return EntityDoc(
        uuid=uuid,
        name=f"Room {uuid[-4:]}",
        kind="location",
        labels=["Location"],
        location_uuid=None,
        attrs={
            "description": f"A room at {uuid}",
            "exits": exits or [],
            "item_ids": [],
        },
        is_dead=False,
    )


def _character(uuid: str, loc: str, hp: int = 20, max_hp: int = 20) -> EntityDoc:
    return EntityDoc(
        uuid=uuid,
        name=f"Char {uuid[-4:]}",
        kind="character",
        labels=["Character"],
        location_uuid=loc,
        attrs={
            "hp": hp,
            "max_hp": max_hp,
            "level": 1,
            "xp": 0,
            "inventory": [],
            "equipped": {},
        },
        is_dead=False,
    )


def _item(uuid: str, owner: str | None = None, loc: str | None = None) -> ItemDoc:
    return ItemDoc(
        uuid=uuid,
        name=f"Item {uuid[-4:]}",
        kind="item",
        labels=["Item"],
        owner_uuid=owner,
        location_uuid=loc,
        attrs={"slot_type": "misc", "weight": 1},
    )


# ---------------------------------------------------------------------------
# Shared factory: seeded EventSourced repo + matching InMemory repo
# ---------------------------------------------------------------------------


async def _make_pair(
    entities: list[EntityDoc] | None = None,
    items: list[ItemDoc] | None = None,
    chain: RecordingChainMirror | None = None,
) -> tuple[EventSourcedStateRepository, InMemoryStateRepository, RecordingChainMirror]:
    """Build a pair of (EventSourced, InMemory) repos seeded identically."""
    chain = chain or RecordingChainMirror()
    proj = KgProjectionFake()
    tx_log = InMemoryTxLog()
    act_log = InMemoryActivationLog()
    es = EventSourcedStateRepository(
        tx_log=tx_log,
        activation_log=act_log,
        projection=proj,
        chain=chain,
    )
    mem = InMemoryStateRepository()

    for doc in (entities or []):
        await es.seed_entity(doc)
        mem.seed_entity(doc)
    for doc in (items or []):
        await es.seed_item(doc)
        mem.seed_item(doc)

    return es, mem, chain


# ---------------------------------------------------------------------------
# Parity: move_entity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_move_entity_return_parity() -> None:
    """move_entity returns the same doc as InMemoryStateRepository."""
    loc_a = _location(LOC_A, exits=[{"direction": "north", "target_uuid": LOC_B}])
    loc_b = _location(LOC_B)
    char = _character(CHAR_1, LOC_A)

    es, mem, _ = await _make_pair(entities=[loc_a, loc_b, char])
    es.set_activation(ACT_1, tool="mm_move")

    es_result = await es.move_entity(CHAR_1, LOC_B)
    mem_result = await mem.move_entity(CHAR_1, LOC_B)

    assert es_result["uuid"] == mem_result["uuid"]
    assert es_result["location_uuid"] == mem_result["location_uuid"]
    assert es_result["location_uuid"] == LOC_B


@pytest.mark.asyncio
async def test_move_entity_updates_location_index() -> None:
    """After move_entity, get_entities_at_location reflects the new location."""
    loc_a = _location(LOC_A)
    loc_b = _location(LOC_B)
    char = _character(CHAR_1, LOC_A)

    es, _, _ = await _make_pair(entities=[loc_a, loc_b, char])
    es.set_activation(ACT_1, tool="mm_move")
    await es.move_entity(CHAR_1, LOC_B)

    at_a = await es.get_entities_at_location(LOC_A)
    at_b = await es.get_entities_at_location(LOC_B)
    assert not any(e["uuid"] == CHAR_1 for e in at_a)
    assert any(e["uuid"] == CHAR_1 for e in at_b)


# ---------------------------------------------------------------------------
# Parity: set_attr
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_attr_attrs_field_parity() -> None:
    """set_attr on an attrs-level field returns the same doc as InMemory."""
    loc_a = _location(LOC_A)
    char = _character(CHAR_1, LOC_A, hp=20)

    es, mem, _ = await _make_pair(entities=[loc_a, char])
    es.set_activation(ACT_1, tool="mm_attack")

    es_result = await es.set_attr(CHAR_1, "hp", 15)
    mem_result = await mem.set_attr(CHAR_1, "hp", 15)

    assert es_result["attrs"]["hp"] == 15
    assert es_result["attrs"]["hp"] == mem_result["attrs"]["hp"]


@pytest.mark.asyncio
async def test_set_attr_is_dead_top_level_parity() -> None:
    """set_attr('is_dead', True) writes top-level, matches InMemory."""
    loc_a = _location(LOC_A)
    char = _character(CHAR_1, LOC_A)

    es, mem, _ = await _make_pair(entities=[loc_a, char])
    es.set_activation(ACT_1, tool="mm_die")

    es_result = await es.set_attr(CHAR_1, "is_dead", True)
    mem_result = await mem.set_attr(CHAR_1, "is_dead", True)

    assert es_result["is_dead"] is True
    assert es_result["is_dead"] == mem_result["is_dead"]


@pytest.mark.asyncio
async def test_set_attr_missing_entity_raises() -> None:
    """set_attr on a missing entity raises KeyError, same as InMemory."""
    es, _, _ = await _make_pair()
    es.set_activation(ACT_1)
    with pytest.raises(KeyError):
        await es.set_attr("no-such-uuid", "hp", 5)


# ---------------------------------------------------------------------------
# Parity: materialize
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_materialize_entity_parity() -> None:
    """materialize(doc, is_item=False) returns doc['uuid'] and makes doc gettable."""
    es, mem, _ = await _make_pair()
    es.set_activation(ACT_1, tool="mm_summon")

    char_doc: EntityDoc = _character(CHAR_1, LOC_A)
    es_uuid = await es.materialize(char_doc, is_item=False)
    mem_uuid = await mem.materialize(char_doc, is_item=False)

    assert es_uuid == CHAR_1
    assert es_uuid == mem_uuid

    es_doc = await es.get_entity(CHAR_1)
    assert es_doc is not None
    assert es_doc["uuid"] == CHAR_1


@pytest.mark.asyncio
async def test_materialize_item_parity() -> None:
    """materialize(doc, is_item=True) stores as item, returns uuid."""
    es, mem, _ = await _make_pair()
    es.set_activation(ACT_1, tool="mm_spawn_item")

    item_doc: ItemDoc = _item(ITEM_1, loc=LOC_A)
    es_uuid = await es.materialize(item_doc, is_item=True)
    mem_uuid = await mem.materialize(item_doc, is_item=True)

    assert es_uuid == ITEM_1
    assert es_uuid == mem_uuid


# ---------------------------------------------------------------------------
# Parity: transfer_item
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transfer_item_pickup_parity() -> None:
    """transfer_item pickup path returns same ItemDoc as InMemory."""
    loc_a = _location(LOC_A)
    char = _character(CHAR_1, LOC_A)
    item = _item(ITEM_1, loc=LOC_A)

    # Seed location to have the item in item_ids
    loc_a["attrs"]["item_ids"] = [ITEM_1]
    es, mem, _ = await _make_pair(entities=[loc_a, char], items=[item])
    es.set_activation(ACT_1, tool="mm_take")

    es_result = await es.transfer_item(ITEM_1, from_uuid=LOC_A, to_uuid=CHAR_1)
    mem_result = await mem.transfer_item(ITEM_1, from_uuid=LOC_A, to_uuid=CHAR_1)

    assert es_result["owner_uuid"] == CHAR_1
    assert es_result["owner_uuid"] == mem_result["owner_uuid"]
    assert es_result["location_uuid"] is None


@pytest.mark.asyncio
async def test_transfer_item_drop_to_floor_parity() -> None:
    """transfer_item drop-to-floor returns same doc as InMemory."""
    loc_a = _location(LOC_A)
    char = _character(CHAR_1, LOC_A)
    char["attrs"]["inventory"] = [ITEM_1]
    item = _item(ITEM_1, owner=CHAR_1)

    es, mem, _ = await _make_pair(entities=[loc_a, char], items=[item])
    es.set_activation(ACT_1, tool="mm_drop")

    es_result = await es.transfer_item(
        ITEM_1, from_uuid=CHAR_1, to_uuid=None, to_location_uuid=LOC_A
    )
    mem_result = await mem.transfer_item(
        ITEM_1, from_uuid=CHAR_1, to_uuid=None, to_location_uuid=LOC_A
    )

    assert es_result["owner_uuid"] is None
    assert es_result["location_uuid"] == LOC_A
    assert es_result["owner_uuid"] == mem_result["owner_uuid"]
    assert es_result["location_uuid"] == mem_result["location_uuid"]


# ---------------------------------------------------------------------------
# Parity: link / unlink
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_parity() -> None:
    """link appends to attrs['links'][rel]; get_entity reflects it."""
    loc_a = _location(LOC_A)
    char = _character(CHAR_1, LOC_A)

    es, mem, _ = await _make_pair(entities=[loc_a, char])
    es.set_activation(ACT_1, tool="mm_die")

    await es.link(CHAR_1, LOC_A, "DIED_IN")
    await mem.link(CHAR_1, LOC_A, "DIED_IN")

    es_doc = await es.get_entity(CHAR_1)
    mem_doc = await mem.get_entity(CHAR_1)

    assert es_doc is not None and mem_doc is not None
    assert es_doc["attrs"]["links"]["DIED_IN"] == [LOC_A]
    assert es_doc["attrs"]["links"] == mem_doc["attrs"]["links"]


@pytest.mark.asyncio
async def test_unlink_removes_target() -> None:
    """unlink removes the target from attrs['links'][rel]."""
    loc_a = _location(LOC_A)
    char = _character(CHAR_1, LOC_A)

    es, mem, _ = await _make_pair(entities=[loc_a, char])
    es.set_activation(ACT_1, tool="mm_die")

    await es.link(CHAR_1, LOC_A, "DIED_IN")
    await es.unlink(CHAR_1, LOC_A, "DIED_IN")
    await mem.link(CHAR_1, LOC_A, "DIED_IN")
    await mem.unlink(CHAR_1, LOC_A, "DIED_IN")

    es_doc = await es.get_entity(CHAR_1)
    mem_doc = await mem.get_entity(CHAR_1)

    assert es_doc is not None and mem_doc is not None
    assert es_doc["attrs"]["links"]["DIED_IN"] == []
    assert es_doc["attrs"]["links"] == mem_doc["attrs"]["links"]


@pytest.mark.asyncio
async def test_unlink_no_op_when_not_present() -> None:
    """unlink is silent when the target is not present (matches InMemory)."""
    char = _character(CHAR_1, LOC_A)
    es, _, _ = await _make_pair(entities=[char])
    es.set_activation(ACT_1)
    # Should not raise
    await es.unlink(CHAR_1, LOC_A, "DIED_IN")


# ---------------------------------------------------------------------------
# Parity: get_actor_snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_actor_snapshot_parity() -> None:
    """get_actor_snapshot returns the same dict as InMemory after a move."""
    loc_a = _location(LOC_A, exits=[{"direction": "north", "target_uuid": LOC_B}])
    loc_b = _location(LOC_B)
    char = _character(CHAR_1, LOC_A)

    es, mem, _ = await _make_pair(entities=[loc_a, loc_b, char])
    es.set_activation(ACT_1, tool="mm_move")

    await es.move_entity(CHAR_1, LOC_B)
    await mem.move_entity(CHAR_1, LOC_B)

    es_snap = await es.get_actor_snapshot(CHAR_1)
    mem_snap = await mem.get_actor_snapshot(CHAR_1)

    assert es_snap["uuid"] == mem_snap["uuid"]
    assert es_snap["location"] == LOC_B
    assert es_snap["location"] == mem_snap["location"]
    assert es_snap["health"] == mem_snap["health"]
    assert es_snap["is_dead"] == mem_snap["is_dead"]


# ---------------------------------------------------------------------------
# Tx log stamping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_appends_tx_with_activation_id() -> None:
    """Each write call appends exactly one non-genesis TxEntry per op, stamped with activation_id.

    for_actor(CHAR_1) returns entries in insertion order:
      [0] genesis create (activation_id="genesis") from seed_entity(char)
      [1] the move_entity write (activation_id=ACT_1)
    """
    loc_a = _location(LOC_A)
    loc_b = _location(LOC_B)
    char = _character(CHAR_1, LOC_A)

    chain = RecordingChainMirror()
    proj = KgProjectionFake()
    tx_log = InMemoryTxLog()
    act_log = InMemoryActivationLog()
    es = EventSourcedStateRepository(
        tx_log=tx_log, activation_log=act_log, projection=proj, chain=chain
    )
    await es.seed_entity(loc_a)
    await es.seed_entity(loc_b)
    await es.seed_entity(char)

    es.set_activation(ACT_1, tool="mm_move")
    await es.move_entity(CHAR_1, LOC_B)

    entries = tx_log.for_actor(CHAR_1)
    # One genesis entry from seed_entity + one write entry from move_entity
    assert len(entries) == 2
    # The write entry is the last one
    write_entry = entries[-1]
    assert write_entry.activation_id == ACT_1
    assert write_entry.tool == "mm_move"
    assert write_entry.actor_id == CHAR_1
    # The first entry is the genesis seed
    assert entries[0].activation_id == "genesis"


@pytest.mark.asyncio
async def test_seed_uses_genesis_activation_id() -> None:
    """seed_entity/seed_item log TxEntries with activation_id='genesis'."""
    loc_a = _location(LOC_A)
    char = _character(CHAR_1, LOC_A)
    item = _item(ITEM_1, loc=LOC_A)

    proj = KgProjectionFake()
    tx_log = InMemoryTxLog()
    act_log = InMemoryActivationLog()
    es = EventSourcedStateRepository(
        tx_log=tx_log,
        activation_log=act_log,
        projection=proj,
        chain=NoopChainMirror(),
    )
    await es.seed_entity(loc_a)
    await es.seed_entity(char)
    await es.seed_item(item)

    # Every entry uses activation_id="genesis"
    all_entries = [
        e for e in tx_log._entries  # type: ignore[attr-defined]
    ]
    assert all(e.activation_id == "genesis" for e in all_entries)
    assert len(all_entries) == 3


@pytest.mark.asyncio
async def test_set_activation_changes_stamp() -> None:
    """set_activation changes the stamp so writes after it use the new id."""
    loc_a = _location(LOC_A)
    char = _character(CHAR_1, LOC_A)

    proj = KgProjectionFake()
    tx_log = InMemoryTxLog()
    act_log = InMemoryActivationLog()
    es = EventSourcedStateRepository(
        tx_log=tx_log,
        activation_log=act_log,
        projection=proj,
        chain=NoopChainMirror(),
    )
    await es.seed_entity(loc_a)
    await es.seed_entity(char)

    es.set_activation(ACT_1, tool="mm_attack")
    await es.set_attr(CHAR_1, "hp", 15)

    es.set_activation(ACT_2, tool="mm_attack")
    await es.set_attr(CHAR_1, "hp", 10)

    char_entries = tx_log.for_actor(CHAR_1)
    # [0]=genesis seed, [1]=first set_attr (ACT_1), [2]=second set_attr (ACT_2)
    assert len(char_entries) == 3
    write_entries = [e for e in char_entries if e.activation_id != "genesis"]
    assert len(write_entries) == 2
    assert write_entries[0].activation_id == ACT_1
    assert write_entries[1].activation_id == ACT_2


# ---------------------------------------------------------------------------
# ChainMirror firing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_attr_is_dead_does_not_fire_chain_mirror_from_repo() -> None:
    """set_attr(is_dead=True) does NOT fire on_character_death from the repo.

    Chain firing is the EffectExecutor's sole responsibility (chain_kill primitive).
    The repo fires ZERO chain calls — identical to InMemoryStateRepository.
    Firing from the repo would double-notarize deaths and break InMemory parity.
    """
    loc_a = _location(LOC_A)
    char = _character(CHAR_1, LOC_A)

    es, _, chain = await _make_pair(entities=[loc_a, char])
    es.set_activation(ACT_1, tool="mm_die")

    await es.set_attr(CHAR_1, "is_dead", True)

    # State write succeeds — but chain is never touched by the repo.
    assert len(chain.death_calls) == 0


@pytest.mark.asyncio
async def test_set_attr_is_dead_false_does_not_fire_chain_mirror() -> None:
    """set_attr(is_dead=False) does NOT fire on_character_death."""
    loc_a = _location(LOC_A)
    char = _character(CHAR_1, LOC_A)

    es, _, chain = await _make_pair(entities=[loc_a, char])
    es.set_activation(ACT_1)

    await es.set_attr(CHAR_1, "is_dead", False)

    assert len(chain.death_calls) == 0


@pytest.mark.asyncio
async def test_transfer_item_to_owner_does_not_fire_chain_mirror_from_repo() -> None:
    """transfer_item to a new owner does NOT fire on_item_transferred from the repo.

    Chain firing is the EffectExecutor's sole responsibility (chain_transfer primitive).
    The repo fires ZERO chain calls — identical to InMemoryStateRepository.
    Firing from the repo would double-notarize ownership and break InMemory parity.
    """
    loc_a = _location(LOC_A)
    loc_a["attrs"]["item_ids"] = [ITEM_1]
    char = _character(CHAR_1, LOC_A)
    item = _item(ITEM_1, loc=LOC_A)

    es, _, chain = await _make_pair(entities=[loc_a, char], items=[item])
    es.set_activation(ACT_1, tool="mm_take")

    await es.transfer_item(ITEM_1, from_uuid=LOC_A, to_uuid=CHAR_1)

    # State write succeeds (item ownership updated) — but chain is never touched by repo.
    assert len(chain.transfer_calls) == 0


@pytest.mark.asyncio
async def test_transfer_item_to_floor_does_not_fire_chain_mirror() -> None:
    """Dropping an item to the floor (to_uuid=None) does NOT fire on_item_transferred."""
    loc_a = _location(LOC_A)
    char = _character(CHAR_1, LOC_A)
    char["attrs"]["inventory"] = [ITEM_1]
    item = _item(ITEM_1, owner=CHAR_1)

    es, _, chain = await _make_pair(entities=[loc_a, char], items=[item])
    es.set_activation(ACT_1, tool="mm_drop")

    await es.transfer_item(ITEM_1, from_uuid=CHAR_1, to_uuid=None, to_location_uuid=LOC_A)

    assert len(chain.transfer_calls) == 0


# ---------------------------------------------------------------------------
# rebuild_projection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rebuild_projection_reproduces_state() -> None:
    """After a sequence of writes, rebuild_projection yields identical docs."""
    loc_a = _location(LOC_A)
    loc_b = _location(LOC_B)
    char = _character(CHAR_1, LOC_A)

    proj = KgProjectionFake()
    tx_log = InMemoryTxLog()
    act_log = InMemoryActivationLog()
    es = EventSourcedStateRepository(
        tx_log=tx_log,
        activation_log=act_log,
        projection=proj,
        chain=NoopChainMirror(),
    )

    await es.seed_entity(loc_a)
    await es.seed_entity(loc_b)
    await es.seed_entity(char)

    es.set_activation(ACT_1, tool="mm_move")
    await es.move_entity(CHAR_1, LOC_B)

    es.set_activation(ACT_2, tool="mm_attack")
    await es.set_attr(CHAR_1, "hp", 12)

    # Rebuild from tx log
    rebuilt = await es.rebuild_projection(CHAR_1)

    live_doc = await es.get_entity(CHAR_1)
    rebuilt_doc = await rebuilt.get(CHAR_1)

    assert live_doc is not None and rebuilt_doc is not None
    assert rebuilt_doc["location_uuid"] == LOC_B
    assert rebuilt_doc["attrs"]["hp"] == 12


@pytest.mark.asyncio
async def test_rebuild_projection_location_index() -> None:
    """rebuild_projection correctly reflects location membership."""
    loc_a = _location(LOC_A)
    loc_b = _location(LOC_B)
    char = _character(CHAR_1, LOC_A)

    proj = KgProjectionFake()
    tx_log = InMemoryTxLog()
    act_log = InMemoryActivationLog()
    es = EventSourcedStateRepository(
        tx_log=tx_log,
        activation_log=act_log,
        projection=proj,
        chain=NoopChainMirror(),
    )
    await es.seed_entity(loc_a)
    await es.seed_entity(loc_b)
    await es.seed_entity(char)

    es.set_activation(ACT_1, tool="mm_move")
    await es.move_entity(CHAR_1, LOC_B)

    rebuilt = await es.rebuild_projection(CHAR_1)

    at_b = await rebuilt.entities_at_location(LOC_B)
    assert any(e["uuid"] == CHAR_1 for e in at_b)


# ---------------------------------------------------------------------------
# FIX 1 — Immutable log: genesis delta frozen at write time
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_genesis_delta_is_immutable_after_write() -> None:
    """Genesis delta doc must not be aliased by live projection state.

    After seed_entity seeds a character with an empty inventory, a subsequent
    transfer_item that adds an item to the character's inventory must NOT
    retroactively change the earlier genesis delta stored in the TxLog.

    This proves FIX 1: the TxLog stores a deepcopy of each entry so later
    mutations to live projection attrs cannot reach logged deltas.
    """
    loc_a = _location(LOC_A)
    char = _character(CHAR_1, LOC_A)
    # Character starts with empty inventory.
    char["attrs"]["inventory"] = []
    item = _item(ITEM_1, loc=LOC_A)
    loc_a["attrs"]["item_ids"] = [ITEM_1]

    proj = KgProjectionFake()
    tx_log = InMemoryTxLog()
    act_log = InMemoryActivationLog()
    es = EventSourcedStateRepository(
        tx_log=tx_log,
        activation_log=act_log,
        projection=proj,
        chain=NoopChainMirror(),
    )

    await es.seed_entity(loc_a)
    await es.seed_entity(char)
    await es.seed_item(item)

    # Capture the genesis delta for the character NOW (before any mutations).
    char_genesis_entries = tx_log.for_actor(CHAR_1)
    assert len(char_genesis_entries) == 1, "expected exactly one genesis entry for char"
    genesis_delta = char_genesis_entries[0].deltas[0]
    assert genesis_delta["op"] == "create"
    # Snapshot the inventory as recorded in the genesis delta.
    genesis_inventory_before = list(genesis_delta["doc"]["attrs"]["inventory"])  # type: ignore[index]
    assert genesis_inventory_before == [], "genesis inventory should be empty"

    # Now transfer the item to the character — this mutates the live projection.
    es.set_activation(ACT_1, tool="mm_take")
    await es.transfer_item(ITEM_1, from_uuid=LOC_A, to_uuid=CHAR_1)

    # Verify live projection updated correctly.
    live_char = await es.get_entity(CHAR_1)
    assert live_char is not None
    assert ITEM_1 in live_char["attrs"]["inventory"], (
        "ITEM_1 should be in live char inventory after transfer"
    )

    # The genesis delta must still show the ORIGINAL empty inventory.
    char_genesis_entries_after = tx_log.for_actor(CHAR_1)
    genesis_delta_after = char_genesis_entries_after[0].deltas[0]
    genesis_inventory_after = list(genesis_delta_after["doc"]["attrs"]["inventory"])  # type: ignore[index]
    assert genesis_inventory_after == [], (
        f"Genesis delta was mutated retroactively! "
        f"Expected empty inventory in genesis delta, got {genesis_inventory_after!r}. "
        f"Fix 1 (immutable log) is broken."
    )


# ---------------------------------------------------------------------------
# FIX 2 — Global rebuild: cross-entity writes reconstructed from full log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rebuild_projection_includes_cross_entity_transfer() -> None:
    """rebuild_projection(actor_id) must replay ALL log entries, not just actor's.

    The transfer_item TX is logged under item_uuid (not player uuid).  The old
    for_actor(CHAR_1) approach would miss it; the new all()-based replay must include it.

    This proves FIX 2: the blade is in the rebuilt inventory even though the transfer
    TX is filed under ITEM_1, not CHAR_1.
    """
    loc_a = _location(LOC_A)
    char = _character(CHAR_1, LOC_A)
    char["attrs"]["inventory"] = []
    item = _item(ITEM_1, loc=LOC_A)
    loc_a["attrs"]["item_ids"] = [ITEM_1]

    proj = KgProjectionFake()
    tx_log = InMemoryTxLog()
    act_log = InMemoryActivationLog()
    es = EventSourcedStateRepository(
        tx_log=tx_log,
        activation_log=act_log,
        projection=proj,
        chain=NoopChainMirror(),
    )

    await es.seed_entity(loc_a)
    await es.seed_entity(char)
    await es.seed_item(item)

    # Transfer: logged under ITEM_1, NOT CHAR_1.
    es.set_activation(ACT_1, tool="mm_take")
    await es.transfer_item(ITEM_1, from_uuid=LOC_A, to_uuid=CHAR_1)

    # Sanity: the transfer IS logged under ITEM_1, not CHAR_1.
    char_entries_only = tx_log.for_actor(CHAR_1)
    assert not any(
        any(d.get("op") == "transfer" for d in e.deltas) for e in char_entries_only
    ), "transfer TX should NOT appear in CHAR_1-filtered entries"

    # rebuild_projection(CHAR_1) replays the whole log — blade must appear.
    rebuilt = await es.rebuild_projection(CHAR_1)
    rebuilt_char = await rebuilt.get(CHAR_1)
    assert rebuilt_char is not None, "CHAR_1 missing from rebuilt projection"
    rebuilt_inventory = rebuilt_char.get("attrs", {}).get("inventory", [])
    assert ITEM_1 in rebuilt_inventory, (
        f"Rebuilt inventory {rebuilt_inventory!r} does not contain ITEM_1 — "
        f"Fix 2 (global rebuild) is broken: cross-entity transfer was missed."
    )
