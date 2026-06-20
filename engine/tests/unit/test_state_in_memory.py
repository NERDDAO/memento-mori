"""Unit tests for InMemoryStateRepository — one test per write method.

Tests assert exact before/after field values per the §6.2 spec contract:
- set_attr  — scalar field mutation, returns updated EntityDoc
- move_entity — relocates entity, maintains location denormalization
- transfer_item — pickup + compensating restore; denorm on both ends
- link / unlink — attrs["links"][rel] list management
- get_* reads — get_entity, get_labels, get_entities_at_location,
                get_items_at_location, get_exits, room_manifest

No mongomock, no RNG, no LLM.
"""
from __future__ import annotations

import pytest

from tests.fixtures import ASH_MARKET, GOBLIN, IRON_SWORD, KAEL, RIVER_GATE
from memento.state.in_memory import InMemoryStateRepository
from memento.state.repository import EntityDoc, ExitRecord, ItemDoc


# ---------------------------------------------------------------------------
# Helpers — build minimal fixture docs
# ---------------------------------------------------------------------------

TATTERED_SCROLL = "6650000000000000000000b2"   # non-onchain floor item


def _make_kael() -> EntityDoc:
    return EntityDoc(
        uuid=KAEL,
        name="Kael",
        kind="character",
        labels=["Character", "Player"],
        location_uuid=ASH_MARKET,
        attrs={
            "hp": 20,
            "max_hp": 20,
            "strength": 3,
            "armor": 1,
            "inventory": [],
            "equipped": {},
        },
        is_dead=False,
    )


def _make_goblin() -> EntityDoc:
    return EntityDoc(
        uuid=GOBLIN,
        name="Goblin Scout",
        kind="character",
        labels=["Character", "NPC"],
        location_uuid=ASH_MARKET,
        attrs={
            "hp": 9,
            "max_hp": 9,
            "strength": 1,
            "armor": 2,
            "inventory": [],
            "equipped": {},
        },
        is_dead=False,
    )


def _make_ash_market() -> EntityDoc:
    return EntityDoc(
        uuid=ASH_MARKET,
        name="The Ash Market",
        kind="location",
        labels=["Location"],
        location_uuid=None,
        attrs={
            "description": "A smoky bazaar.",
            "item_ids": [TATTERED_SCROLL],
            "exits": [
                {"direction": "north", "target_uuid": RIVER_GATE, "locked": False}
            ],
        },
        is_dead=False,
    )


def _make_river_gate() -> EntityDoc:
    return EntityDoc(
        uuid=RIVER_GATE,
        name="River Gate",
        kind="location",
        labels=["Location"],
        location_uuid=None,
        attrs={
            "description": "The northern gate.",
            "item_ids": [],
            "exits": [
                {"direction": "south", "target_uuid": ASH_MARKET, "locked": False}
            ],
        },
        is_dead=False,
    )


def _make_iron_sword() -> ItemDoc:
    return ItemDoc(
        uuid=IRON_SWORD,
        name="Iron Sword",
        kind="item",
        labels=["Item", "Weapon"],
        owner_uuid=KAEL,
        location_uuid=None,
        attrs={"damage": 8, "slot_type": "main_hand", "carryable": True, "onchain": True},
    )


def _make_tattered_scroll() -> ItemDoc:
    return ItemDoc(
        uuid=TATTERED_SCROLL,
        name="Tattered Scroll",
        kind="item",
        labels=["Item"],
        owner_uuid=None,
        location_uuid=ASH_MARKET,
        attrs={"carryable": True, "onchain": False},
    )


def _repo_with_world() -> InMemoryStateRepository:
    """Return a seeded repo with both locations, Kael, Goblin, Iron Sword, Tattered Scroll."""
    repo = InMemoryStateRepository()
    repo.seed_entity(_make_ash_market())
    repo.seed_entity(_make_river_gate())
    repo.seed_entity(_make_kael())
    repo.seed_entity(_make_goblin())
    repo.seed_item(_make_iron_sword())
    repo.seed_item(_make_tattered_scroll())
    return repo


# ---------------------------------------------------------------------------
# ensure_indexes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_indexes_is_noop() -> None:
    repo = InMemoryStateRepository()
    await repo.ensure_indexes()   # must not raise


# ---------------------------------------------------------------------------
# get_entity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_entity_returns_doc() -> None:
    repo = _repo_with_world()
    doc = await repo.get_entity(KAEL)
    assert doc is not None
    assert doc["uuid"] == KAEL
    assert doc["name"] == "Kael"
    assert doc["attrs"]["hp"] == 20


@pytest.mark.asyncio
async def test_get_entity_unknown_returns_none() -> None:
    repo = InMemoryStateRepository()
    doc = await repo.get_entity("000000000000000000000000")
    assert doc is None


@pytest.mark.asyncio
async def test_get_entity_returns_copy_not_reference() -> None:
    """Mutating returned doc must not corrupt the store."""
    repo = _repo_with_world()
    doc = await repo.get_entity(KAEL)
    assert doc is not None
    doc["attrs"]["hp"] = 999
    doc2 = await repo.get_entity(KAEL)
    assert doc2 is not None
    assert doc2["attrs"]["hp"] == 20


# ---------------------------------------------------------------------------
# get_labels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_labels_known_entity() -> None:
    repo = _repo_with_world()
    labels = await repo.get_labels(KAEL)
    assert "Character" in labels
    assert "Player" in labels


@pytest.mark.asyncio
async def test_get_labels_unknown_returns_empty() -> None:
    repo = InMemoryStateRepository()
    labels = await repo.get_labels("000000000000000000000000")
    assert labels == []


# ---------------------------------------------------------------------------
# get_entities_at_location
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_entities_at_location() -> None:
    repo = _repo_with_world()
    entities = await repo.get_entities_at_location(ASH_MARKET)
    uuids = {e["uuid"] for e in entities}
    # Characters at Ash Market; items excluded
    assert KAEL in uuids
    assert GOBLIN in uuids
    assert IRON_SWORD not in uuids   # iron sword is an item
    assert TATTERED_SCROLL not in uuids


@pytest.mark.asyncio
async def test_get_entities_at_location_empty_room() -> None:
    repo = _repo_with_world()
    # River Gate has no characters
    entities = await repo.get_entities_at_location(RIVER_GATE)
    assert entities == []


# ---------------------------------------------------------------------------
# get_items_at_location
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_items_at_location_floor_items_only() -> None:
    repo = _repo_with_world()
    items = await repo.get_items_at_location(ASH_MARKET)
    uuids = {i["uuid"] for i in items}
    # Tattered Scroll is on the floor (owner_uuid=None, location_uuid=ASH_MARKET)
    assert TATTERED_SCROLL in uuids
    # Iron Sword is owned by Kael — must NOT appear
    assert IRON_SWORD not in uuids


@pytest.mark.asyncio
async def test_get_items_at_location_excludes_held_items() -> None:
    repo = _repo_with_world()
    items = await repo.get_items_at_location(RIVER_GATE)
    assert items == []


# ---------------------------------------------------------------------------
# get_exits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_exits_returns_exit_records() -> None:
    repo = _repo_with_world()
    exits = await repo.get_exits(ASH_MARKET)
    assert len(exits) == 1
    ex = exits[0]
    assert isinstance(ex, ExitRecord)
    assert ex.direction == "north"
    assert ex.target_id == RIVER_GATE
    assert ex.locked is False
    assert ex.key_item_id is None


@pytest.mark.asyncio
async def test_get_exits_unknown_location_returns_empty() -> None:
    repo = InMemoryStateRepository()
    exits = await repo.get_exits("000000000000000000000000")
    assert exits == []


# ---------------------------------------------------------------------------
# get_actor_snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_actor_snapshot_shape() -> None:
    repo = _repo_with_world()
    snap = await repo.get_actor_snapshot(KAEL)
    assert snap["uuid"] == KAEL
    assert snap["location"] == ASH_MARKET
    assert snap["health"] == 20
    assert snap["is_dead"] is False


@pytest.mark.asyncio
async def test_get_actor_snapshot_unknown_returns_empty() -> None:
    repo = InMemoryStateRepository()
    snap = await repo.get_actor_snapshot("000000000000000000000000")
    assert snap == {}


# ---------------------------------------------------------------------------
# room_manifest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_room_manifest_exits_npcs_items() -> None:
    repo = _repo_with_world()
    manifest = await repo.room_manifest(ASH_MARKET)
    assert manifest.location_id == ASH_MARKET
    assert manifest.name == "The Ash Market"
    npc_uuids = {e["uuid"] for e in manifest.npcs}
    assert KAEL in npc_uuids
    assert GOBLIN in npc_uuids
    item_uuids = {i["uuid"] for i in manifest.items}
    assert TATTERED_SCROLL in item_uuids
    assert IRON_SWORD not in item_uuids  # held, not on floor
    assert len(manifest.exits) == 1
    assert manifest.exits[0].direction == "north"


@pytest.mark.asyncio
async def test_room_manifest_unknown_location() -> None:
    repo = InMemoryStateRepository()
    manifest = await repo.room_manifest("000000000000000000000000")
    assert manifest.location_id == "000000000000000000000000"
    assert manifest.name == ""
    assert manifest.exits == []


# ---------------------------------------------------------------------------
# set_attr
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_attr_attrs_level_field() -> None:
    """set_attr on an attrs-level field (hp) returns the updated doc."""
    repo = _repo_with_world()
    before = (await repo.get_entity(GOBLIN))["attrs"]["hp"]  # type: ignore[index]
    assert before == 9

    updated = await repo.set_attr(GOBLIN, "hp", 0)

    assert updated["attrs"]["hp"] == 0
    assert updated["uuid"] == GOBLIN

    # Verify the store is actually updated
    fresh = await repo.get_entity(GOBLIN)
    assert fresh is not None
    assert fresh["attrs"]["hp"] == 0


@pytest.mark.asyncio
async def test_set_attr_is_dead_top_level_field() -> None:
    """set_attr("is_dead", True) sets the top-level EntityDoc field."""
    repo = _repo_with_world()
    assert (await repo.get_entity(GOBLIN))["is_dead"] is False  # type: ignore[index]

    updated = await repo.set_attr(GOBLIN, "is_dead", True)

    assert updated["is_dead"] is True
    fresh = await repo.get_entity(GOBLIN)
    assert fresh is not None
    assert fresh["is_dead"] is True


@pytest.mark.asyncio
async def test_set_attr_returns_copy_not_reference() -> None:
    """Mutating the returned doc must not corrupt the store."""
    repo = _repo_with_world()
    returned = await repo.set_attr(GOBLIN, "hp", 5)
    returned["attrs"]["hp"] = 999  # mutate the returned copy
    fresh = await repo.get_entity(GOBLIN)
    assert fresh is not None
    assert fresh["attrs"]["hp"] == 5


@pytest.mark.asyncio
async def test_set_attr_unknown_entity_raises() -> None:
    repo = InMemoryStateRepository()
    with pytest.raises(KeyError):
        await repo.set_attr("000000000000000000000000", "hp", 0)


# ---------------------------------------------------------------------------
# move_entity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_move_entity_updates_location_uuid() -> None:
    """move_entity sets the entity's location_uuid."""
    repo = _repo_with_world()
    assert (await repo.get_entity(KAEL))["location_uuid"] == ASH_MARKET  # type: ignore[index]

    updated = await repo.move_entity(KAEL, RIVER_GATE)

    assert updated["location_uuid"] == RIVER_GATE
    fresh = await repo.get_entity(KAEL)
    assert fresh is not None
    assert fresh["location_uuid"] == RIVER_GATE


@pytest.mark.asyncio
async def test_move_entity_removes_from_old_location_item_ids() -> None:
    """move_entity removes entity UUID from old location's attrs["item_ids"]."""
    repo = _repo_with_world()
    # Ash Market should initially have Kael (if they were in item_ids; some impls track occupants)
    # To test reliably, manually place KAEL in ASH_MARKET item_ids first
    ash = repo._entities[ASH_MARKET]
    ash["attrs"].setdefault("item_ids", [])
    if KAEL not in ash["attrs"]["item_ids"]:
        ash["attrs"]["item_ids"].append(KAEL)

    await repo.move_entity(KAEL, RIVER_GATE)

    ash_after = await repo.get_entity(ASH_MARKET)
    assert ash_after is not None
    assert KAEL not in ash_after["attrs"].get("item_ids", [])


@pytest.mark.asyncio
async def test_move_entity_adds_to_new_location_item_ids() -> None:
    """move_entity appends entity UUID to new location's attrs["item_ids"]."""
    repo = _repo_with_world()
    # Ensure KAEL not already in RIVER_GATE item_ids
    river = repo._entities[RIVER_GATE]
    river["attrs"]["item_ids"] = []

    await repo.move_entity(KAEL, RIVER_GATE)

    river_after = await repo.get_entity(RIVER_GATE)
    assert river_after is not None
    assert KAEL in river_after["attrs"].get("item_ids", [])


@pytest.mark.asyncio
async def test_move_entity_unknown_entity_raises() -> None:
    repo = InMemoryStateRepository()
    with pytest.raises(KeyError):
        await repo.move_entity("000000000000000000000000", ASH_MARKET)


# ---------------------------------------------------------------------------
# transfer_item — pickup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transfer_item_pickup_sets_owner_uuid() -> None:
    """Pickup: item.owner_uuid set to agent; item.location_uuid cleared."""
    repo = _repo_with_world()
    # Tattered Scroll is on floor at Ash Market
    item_before = await repo.get_entity(TATTERED_SCROLL)
    assert item_before is not None
    assert item_before.get("owner_uuid") is None  # type: ignore[call-overload]
    assert item_before.get("location_uuid") == ASH_MARKET  # type: ignore[call-overload]

    updated: ItemDoc = await repo.transfer_item(
        item_uuid=TATTERED_SCROLL,
        from_uuid=ASH_MARKET,
        to_uuid=KAEL,
    )

    assert updated["owner_uuid"] == KAEL
    assert updated["location_uuid"] is None


@pytest.mark.asyncio
async def test_transfer_item_pickup_adds_to_agent_inventory() -> None:
    """Pickup: agent's attrs["inventory"] gains the item UUID."""
    repo = _repo_with_world()
    kael_before = await repo.get_entity(KAEL)
    assert kael_before is not None
    assert TATTERED_SCROLL not in kael_before["attrs"].get("inventory", [])

    await repo.transfer_item(TATTERED_SCROLL, from_uuid=ASH_MARKET, to_uuid=KAEL)

    kael_after = await repo.get_entity(KAEL)
    assert kael_after is not None
    assert TATTERED_SCROLL in kael_after["attrs"]["inventory"]


@pytest.mark.asyncio
async def test_transfer_item_pickup_removes_from_location_item_ids() -> None:
    """Pickup: item removed from location's attrs["item_ids"]."""
    repo = _repo_with_world()
    ash_before = await repo.get_entity(ASH_MARKET)
    assert ash_before is not None
    assert TATTERED_SCROLL in ash_before["attrs"].get("item_ids", [])

    await repo.transfer_item(TATTERED_SCROLL, from_uuid=ASH_MARKET, to_uuid=KAEL)

    ash_after = await repo.get_entity(ASH_MARKET)
    assert ash_after is not None
    assert TATTERED_SCROLL not in ash_after["attrs"].get("item_ids", [])


@pytest.mark.asyncio
async def test_transfer_item_pickup_exact_before_after() -> None:
    """Exact before/after for StateDelta building by executor."""
    repo = _repo_with_world()

    before_item = await repo.get_entity(TATTERED_SCROLL)
    assert before_item is not None
    assert before_item.get("owner_uuid") is None  # type: ignore[call-overload]

    after_item: ItemDoc = await repo.transfer_item(TATTERED_SCROLL, ASH_MARKET, KAEL)

    assert after_item["owner_uuid"] == KAEL
    assert after_item["location_uuid"] is None


# ---------------------------------------------------------------------------
# transfer_item — compensating restore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transfer_item_compensating_restore_clears_owner() -> None:
    """Restore: item.owner_uuid cleared; item.location_uuid set to original."""
    repo = _repo_with_world()

    # First: pickup
    await repo.transfer_item(TATTERED_SCROLL, from_uuid=ASH_MARKET, to_uuid=KAEL)

    # Compensating restore
    restored: ItemDoc = await repo.transfer_item(
        item_uuid=TATTERED_SCROLL,
        from_uuid=KAEL,
        to_uuid=None,
        to_location_uuid=ASH_MARKET,
    )

    assert restored["owner_uuid"] is None
    assert restored["location_uuid"] == ASH_MARKET


@pytest.mark.asyncio
async def test_transfer_item_restore_returns_item_to_location_item_ids() -> None:
    """Restore: item re-appears in location's attrs["item_ids"]."""
    repo = _repo_with_world()

    await repo.transfer_item(TATTERED_SCROLL, from_uuid=ASH_MARKET, to_uuid=KAEL)

    ash_mid = await repo.get_entity(ASH_MARKET)
    assert ash_mid is not None
    assert TATTERED_SCROLL not in ash_mid["attrs"].get("item_ids", [])

    await repo.transfer_item(
        TATTERED_SCROLL, from_uuid=KAEL, to_uuid=None, to_location_uuid=ASH_MARKET
    )

    ash_after = await repo.get_entity(ASH_MARKET)
    assert ash_after is not None
    assert TATTERED_SCROLL in ash_after["attrs"]["item_ids"]


@pytest.mark.asyncio
async def test_transfer_item_restore_removes_from_agent_inventory() -> None:
    """Restore: item removed from agent's attrs["inventory"]."""
    repo = _repo_with_world()

    await repo.transfer_item(TATTERED_SCROLL, from_uuid=ASH_MARKET, to_uuid=KAEL)
    kael_mid = await repo.get_entity(KAEL)
    assert kael_mid is not None
    assert TATTERED_SCROLL in kael_mid["attrs"]["inventory"]

    await repo.transfer_item(
        TATTERED_SCROLL, from_uuid=KAEL, to_uuid=None, to_location_uuid=ASH_MARKET
    )

    kael_after = await repo.get_entity(KAEL)
    assert kael_after is not None
    assert TATTERED_SCROLL not in kael_after["attrs"]["inventory"]


@pytest.mark.asyncio
async def test_transfer_item_unknown_item_raises() -> None:
    repo = InMemoryStateRepository()
    with pytest.raises(KeyError):
        await repo.transfer_item("000000000000000000000000", from_uuid=None, to_uuid=KAEL)


# ---------------------------------------------------------------------------
# link / unlink
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_appends_to_links_dict() -> None:
    """link(from, to, rel) appends to_uuid into attrs['links'][rel]."""
    repo = _repo_with_world()

    await repo.link(GOBLIN, ASH_MARKET, "DIED_IN")

    goblin = await repo.get_entity(GOBLIN)
    assert goblin is not None
    links = goblin["attrs"].get("links", {})
    assert "DIED_IN" in links
    assert ASH_MARKET in links["DIED_IN"]


@pytest.mark.asyncio
async def test_link_idempotent_on_duplicate() -> None:
    """Linking the same edge twice must not produce duplicate entries."""
    repo = _repo_with_world()

    await repo.link(GOBLIN, ASH_MARKET, "DIED_IN")
    await repo.link(GOBLIN, ASH_MARKET, "DIED_IN")

    goblin = await repo.get_entity(GOBLIN)
    assert goblin is not None
    links = goblin["attrs"]["links"]
    assert links["DIED_IN"].count(ASH_MARKET) == 1


@pytest.mark.asyncio
async def test_link_multiple_rels() -> None:
    """Multiple relation types on one entity stay separate."""
    repo = _repo_with_world()

    await repo.link(GOBLIN, ASH_MARKET, "DIED_IN")
    await repo.link(GOBLIN, KAEL, "KILLED_BY")

    goblin = await repo.get_entity(GOBLIN)
    assert goblin is not None
    links = goblin["attrs"]["links"]
    assert ASH_MARKET in links["DIED_IN"]
    assert KAEL in links["KILLED_BY"]


@pytest.mark.asyncio
async def test_unlink_removes_edge() -> None:
    """unlink removes the target from attrs['links'][rel]."""
    repo = _repo_with_world()

    await repo.link(GOBLIN, ASH_MARKET, "DIED_IN")
    await repo.unlink(GOBLIN, ASH_MARKET, "DIED_IN")

    goblin = await repo.get_entity(GOBLIN)
    assert goblin is not None
    links = goblin["attrs"].get("links", {})
    assert ASH_MARKET not in links.get("DIED_IN", [])


@pytest.mark.asyncio
async def test_unlink_noop_when_not_present() -> None:
    """unlink on a non-existent edge must not raise."""
    repo = _repo_with_world()
    # No prior link — must be a no-op
    await repo.unlink(GOBLIN, ASH_MARKET, "DIED_IN")


@pytest.mark.asyncio
async def test_link_unknown_entity_raises() -> None:
    repo = InMemoryStateRepository()
    with pytest.raises(KeyError):
        await repo.link("000000000000000000000000", ASH_MARKET, "DIED_IN")


@pytest.mark.asyncio
async def test_unlink_unknown_entity_silent() -> None:
    """unlink on unknown entity is a no-op (from_uuid absent)."""
    repo = InMemoryStateRepository()
    await repo.unlink("000000000000000000000000", ASH_MARKET, "DIED_IN")  # must not raise


# ---------------------------------------------------------------------------
# Composite scenario: full TAKE pickup + restore cycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pickup_and_restore_cycle() -> None:
    """Full round-trip: pickup Tattered Scroll then compensating restore."""
    repo = _repo_with_world()

    # Initial state
    scroll_before = await repo.get_entity(TATTERED_SCROLL)
    assert scroll_before is not None
    assert scroll_before.get("owner_uuid") is None  # type: ignore[call-overload]
    assert scroll_before.get("location_uuid") == ASH_MARKET  # type: ignore[call-overload]

    ash_before = await repo.get_entity(ASH_MARKET)
    assert ash_before is not None
    assert TATTERED_SCROLL in ash_before["attrs"]["item_ids"]

    # Pickup
    after_pickup: ItemDoc = await repo.transfer_item(
        TATTERED_SCROLL, from_uuid=ASH_MARKET, to_uuid=KAEL
    )
    assert after_pickup["owner_uuid"] == KAEL
    assert after_pickup["location_uuid"] is None

    kael_mid = await repo.get_entity(KAEL)
    assert kael_mid is not None
    assert TATTERED_SCROLL in kael_mid["attrs"]["inventory"]

    # Compensating restore
    after_restore: ItemDoc = await repo.transfer_item(
        TATTERED_SCROLL, from_uuid=KAEL, to_uuid=None, to_location_uuid=ASH_MARKET
    )
    assert after_restore["owner_uuid"] is None
    assert after_restore["location_uuid"] == ASH_MARKET

    kael_after = await repo.get_entity(KAEL)
    assert kael_after is not None
    assert TATTERED_SCROLL not in kael_after["attrs"]["inventory"]

    ash_after = await repo.get_entity(ASH_MARKET)
    assert ash_after is not None
    assert TATTERED_SCROLL in ash_after["attrs"]["item_ids"]
