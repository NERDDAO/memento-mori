"""Tests for KgProjection and KgProjectionFake.

TDD gate:
    python -m pytest tests/state/test_kg_projection.py -q

KgProjectionFake behavioural tests:
  - create EntityDoc → get round-trips the exact doc
  - create ItemDoc → get round-trips the exact doc
  - update changes a field and get reflects it
  - changing location_uuid moves entity between entities_at_location results
  - items_at_location returns only owner-less items at the location
  - get of an unknown uuid → None
  - items_at_location excludes items with an owner_uuid set
  - fake honours doc["uuid"] if present on create (stable test fixture UUIDs)

KgProjection (real) tests with a stubbed kg client:
  - create calls kg.create_entity with mapped labels+attributes
  - create returns the server-assigned uuid
  - get calls kg.get_entity_or_none and reconstructs an EntityDoc
  - get returns None when kg returns None
  - update calls kg.update_entity with resent name+labels+summary
  - update calls kg.get_edges and update_edge when location_uuid changes
  - entities_at_location queries kg.get_edges with LOCATED_IN/incoming
  - items_at_location returns only owner-less items
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from memento.state.kg_projection import KgProjection, KgProjectionFake
from memento.state.repository import EntityDoc, ItemDoc

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

LOC_A = "loc-uuid-aaaa"
LOC_B = "loc-uuid-bbbb"
ENT_1 = "ent-uuid-0001"
ENT_2 = "ent-uuid-0002"
ITEM_1 = "item-uuid-0001"
ITEM_2 = "item-uuid-0002"
SERVER_UUID = "server-assigned-uuid-9999"


def _entity(uuid: str = ENT_1, loc: str | None = LOC_A) -> EntityDoc:
    return EntityDoc(
        uuid=uuid,
        name="Test NPC",
        kind="character",
        labels=["Character", "NPC"],
        location_uuid=loc,
        attrs={"hp": 20, "max_hp": 20, "inventory": []},
        is_dead=False,
    )


def _item(uuid: str = ITEM_1, owner: str | None = None, loc: str | None = LOC_A) -> ItemDoc:
    return ItemDoc(
        uuid=uuid,
        name="Iron Sword",
        kind="item",
        labels=["Item", "Weapon"],
        owner_uuid=owner,
        location_uuid=loc,
        attrs={"damage": 5, "slot_type": "weapon"},
    )


# ===========================================================================
# KgProjectionFake — behavioural tests
# ===========================================================================


@pytest.mark.asyncio
async def test_fake_create_entity_then_get_round_trips() -> None:
    """create then get returns the exact EntityDoc."""
    fake = KgProjectionFake()
    doc = _entity()
    returned_uuid = await fake.create(doc)
    assert returned_uuid == doc["uuid"]
    result = await fake.get(returned_uuid)
    assert result is not None
    assert result["uuid"] == doc["uuid"]
    assert result["name"] == doc["name"]
    assert result["kind"] == doc["kind"]
    assert result["labels"] == doc["labels"]
    assert result["location_uuid"] == doc["location_uuid"]
    assert result["attrs"] == doc["attrs"]
    assert result["is_dead"] == doc["is_dead"]


@pytest.mark.asyncio
async def test_fake_create_item_then_get_round_trips() -> None:
    """create then get returns the exact ItemDoc (no is_dead field)."""
    fake = KgProjectionFake()
    doc = _item()
    returned_uuid = await fake.create(doc)
    assert returned_uuid == doc["uuid"]
    result = await fake.get(returned_uuid)
    assert result is not None
    assert result["uuid"] == doc["uuid"]
    assert result["name"] == doc["name"]
    assert result["kind"] == "item"
    assert result["labels"] == doc["labels"]
    assert result["owner_uuid"] == doc["owner_uuid"]
    assert result["location_uuid"] == doc["location_uuid"]
    assert result["attrs"] == doc["attrs"]


@pytest.mark.asyncio
async def test_fake_get_unknown_uuid_returns_none() -> None:
    """get of an unknown uuid returns None."""
    fake = KgProjectionFake()
    result = await fake.get("no-such-uuid")
    assert result is None


@pytest.mark.asyncio
async def test_fake_update_changes_field_visible_in_get() -> None:
    """update changes a field and get reflects the new value."""
    fake = KgProjectionFake()
    doc = _entity()
    await fake.create(doc)

    updated = dict(doc)
    updated["attrs"] = {**doc["attrs"], "hp": 5}
    updated["is_dead"] = False
    await fake.update(updated)  # type: ignore[arg-type]

    result = await fake.get(doc["uuid"])
    assert result is not None
    assert result["attrs"]["hp"] == 5


@pytest.mark.asyncio
async def test_fake_update_location_moves_entity() -> None:
    """Changing location_uuid in update moves entity between location buckets."""
    fake = KgProjectionFake()
    doc = _entity(uuid=ENT_1, loc=LOC_A)
    await fake.create(doc)

    moved = dict(doc)
    moved["location_uuid"] = LOC_B
    await fake.update(moved)  # type: ignore[arg-type]

    at_a = await fake.entities_at_location(LOC_A)
    at_b = await fake.entities_at_location(LOC_B)
    assert not any(e["uuid"] == ENT_1 for e in at_a)
    assert any(e["uuid"] == ENT_1 for e in at_b)


@pytest.mark.asyncio
async def test_fake_entities_at_location_returns_non_items() -> None:
    """entities_at_location returns only non-item entities at the given location."""
    fake = KgProjectionFake()
    npc = _entity(uuid=ENT_1, loc=LOC_A)
    item = _item(uuid=ITEM_1, owner=None, loc=LOC_A)
    await fake.create(npc)
    await fake.create(item)

    results = await fake.entities_at_location(LOC_A)
    uuids = {e["uuid"] for e in results}
    assert ENT_1 in uuids
    assert ITEM_1 not in uuids


@pytest.mark.asyncio
async def test_fake_items_at_location_only_owner_less() -> None:
    """items_at_location returns only items with no owner_uuid at the location."""
    fake = KgProjectionFake()
    floor_item = _item(uuid=ITEM_1, owner=None, loc=LOC_A)
    owned_item = _item(uuid=ITEM_2, owner=ENT_1, loc=LOC_A)
    await fake.create(floor_item)
    await fake.create(owned_item)

    results = await fake.items_at_location(LOC_A)
    uuids = {i["uuid"] for i in results}
    assert ITEM_1 in uuids
    assert ITEM_2 not in uuids


@pytest.mark.asyncio
async def test_fake_items_at_location_filters_by_location() -> None:
    """items_at_location filters by exact location match."""
    fake = KgProjectionFake()
    item_a = _item(uuid=ITEM_1, owner=None, loc=LOC_A)
    item_b = _item(uuid=ITEM_2, owner=None, loc=LOC_B)
    await fake.create(item_a)
    await fake.create(item_b)

    results_a = await fake.items_at_location(LOC_A)
    results_b = await fake.items_at_location(LOC_B)
    assert {i["uuid"] for i in results_a} == {ITEM_1}
    assert {i["uuid"] for i in results_b} == {ITEM_2}


@pytest.mark.asyncio
async def test_fake_create_honours_doc_uuid() -> None:
    """Fake honours doc['uuid'] if present (stable test fixture UUIDs)."""
    fake = KgProjectionFake()
    doc = _entity(uuid="stable-fixture-uuid")
    returned = await fake.create(doc)
    assert returned == "stable-fixture-uuid"
    result = await fake.get("stable-fixture-uuid")
    assert result is not None


@pytest.mark.asyncio
async def test_fake_create_without_uuid_generates_one() -> None:
    """Fake generates a uuid when doc has no uuid field set."""
    fake = KgProjectionFake()
    # Build a doc without uuid (simulate a caller that doesn't set it)
    doc: dict[str, Any] = {
        "name": "Ghost",
        "kind": "character",
        "labels": ["Character"],
        "location_uuid": LOC_A,
        "attrs": {},
        "is_dead": False,
        # no "uuid" key
    }
    returned = await fake.create(doc)  # type: ignore[arg-type]
    assert returned
    result = await fake.get(returned)
    assert result is not None
    assert result["uuid"] == returned


# ===========================================================================
# KgProjection (real) — stub/mock tests
# ===========================================================================


def _make_kg_stub(
    *,
    create_entity_return: str = SERVER_UUID,
    get_entity_return: dict[str, Any] | None = None,
    get_edges_return: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a mock KGService with sensible defaults."""
    kg = MagicMock()
    kg.create_entity.return_value = create_entity_return
    kg.get_entity_or_none.return_value = get_entity_return
    kg.update_entity.return_value = {}
    kg.create_edge.return_value = {"uuid": "edge-uuid-0001"}
    kg.update_edge.return_value = {}
    kg.get_edges.return_value = get_edges_return or []
    return kg


def _server_entity_dict(
    uuid: str = SERVER_UUID,
    name: str = "Test NPC",
    labels: list[str] | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Simulate what the server returns from get_entity_or_none."""
    return {
        "uuid": uuid,
        "name": name,
        "labels": labels or ["Character", "NPC"],
        "summary": "Test NPC summary",
        "attributes": attributes or {
            "_kind": "character",
            "_location_uuid": LOC_A,
            "_is_dead": False,
            "hp": 20,
            "max_hp": 20,
            "inventory": [],
        },
    }


@pytest.mark.asyncio
async def test_real_create_calls_kg_create_entity() -> None:
    """create calls kg.create_entity with mapped labels + attributes."""
    kg = _make_kg_stub()
    proj = KgProjection(kg=kg)
    doc = _entity()
    returned_uuid = await proj.create(doc)

    assert returned_uuid == SERVER_UUID
    kg.create_entity.assert_called_once()
    call_kwargs = kg.create_entity.call_args
    # name is positional or kw
    args, kwargs = call_kwargs
    all_args = {**kwargs}
    if args:
        all_args["name"] = args[0] if len(args) > 0 else all_args.get("name")
        if len(args) > 1:
            all_args["labels"] = args[1]
        if len(args) > 2:
            all_args["attributes"] = args[2]

    # Labels forwarded
    passed_labels = all_args.get("labels") or kwargs.get("labels")
    assert passed_labels == ["Character", "NPC"]

    # Reserved prefix keys present in attributes
    passed_attrs = all_args.get("attributes") or kwargs.get("attributes")
    assert passed_attrs is not None
    assert passed_attrs["_kind"] == "character"
    assert passed_attrs["_location_uuid"] == LOC_A
    assert passed_attrs["_is_dead"] is False


@pytest.mark.asyncio
async def test_real_create_returns_server_uuid() -> None:
    """create returns whatever uuid the server assigns."""
    kg = _make_kg_stub(create_entity_return="server-uuid-XYZ")
    proj = KgProjection(kg=kg)
    returned = await proj.create(_entity())
    assert returned == "server-uuid-XYZ"


@pytest.mark.asyncio
async def test_real_get_reconstructs_entity_doc() -> None:
    """get calls get_entity_or_none and reconstructs an EntityDoc."""
    server_response = _server_entity_dict()
    kg = _make_kg_stub(get_entity_return=server_response)
    proj = KgProjection(kg=kg)

    result = await proj.get(SERVER_UUID)
    kg.get_entity_or_none.assert_called_once_with(SERVER_UUID)
    assert result is not None
    assert result["uuid"] == SERVER_UUID
    assert result["name"] == "Test NPC"
    assert result["kind"] == "character"
    assert result["location_uuid"] == LOC_A
    assert result["is_dead"] is False


@pytest.mark.asyncio
async def test_real_get_returns_none_when_missing() -> None:
    """get returns None when the KG returns None."""
    kg = _make_kg_stub(get_entity_return=None)
    proj = KgProjection(kg=kg)
    result = await proj.get("no-such-uuid")
    assert result is None


@pytest.mark.asyncio
async def test_real_update_calls_update_entity_with_resent_fields() -> None:
    """update calls kg.update_entity resending name + labels + summary."""
    # Must get current entity first to know old location
    server_response = _server_entity_dict()
    kg = _make_kg_stub(get_entity_return=server_response)
    proj = KgProjection(kg=kg)

    doc = _entity()
    doc["attrs"] = {**doc["attrs"], "hp": 10}

    await proj.update(doc)

    kg.update_entity.assert_called_once()
    args, kwargs = kg.update_entity.call_args
    # uuid is first positional arg
    called_uuid = args[0] if args else kwargs.get("uuid")
    assert called_uuid == doc["uuid"]
    # name must be resent
    called_name = args[1] if len(args) > 1 else kwargs.get("name")
    assert called_name == doc["name"]
    # labels must be resent
    called_labels = args[2] if len(args) > 2 else kwargs.get("labels")
    assert called_labels == doc["labels"]


@pytest.mark.asyncio
async def test_real_update_creates_new_located_in_edge_on_location_change() -> None:
    """update expires old LOCATED_IN edge and creates a new one when location changes."""
    old_edge = {
        "uuid": "old-edge-uuid",
        "name": "LOCATED_IN",
        "source": {"uuid": ENT_1},
        "target": {"uuid": LOC_A},
        "expired_at": None,
        "valid_at": None,
        "invalid_at": None,
    }
    server_response = _server_entity_dict(
        uuid=ENT_1,
        attributes={
            "_kind": "character",
            "_location_uuid": LOC_A,
            "_is_dead": False,
            "hp": 20,
            "max_hp": 20,
            "inventory": [],
        },
    )
    kg = _make_kg_stub(get_entity_return=server_response, get_edges_return=[old_edge])
    proj = KgProjection(kg=kg)

    doc = _entity(uuid=ENT_1, loc=LOC_B)  # moved to LOC_B
    await proj.update(doc)

    # Old edge should be expired
    kg.update_edge.assert_called_once()
    update_args, update_kwargs = kg.update_edge.call_args
    called_edge_uuid = update_args[0] if update_args else update_kwargs.get("edge_uuid")
    assert called_edge_uuid == "old-edge-uuid"

    # New edge should be created
    kg.create_edge.assert_called_once()
    create_args, create_kwargs = kg.create_edge.call_args
    all_create = {**create_kwargs}
    if create_args:
        all_create["source_uuid"] = create_args[0]
        all_create["target_uuid"] = create_args[1] if len(create_args) > 1 else all_create.get("target_uuid")
    assert all_create.get("target_uuid") == LOC_B


@pytest.mark.asyncio
async def test_real_entities_at_location_queries_kg_edges() -> None:
    """entities_at_location calls get_edges on location with incoming LOCATED_IN filter."""
    loc_entity = {
        "uuid": LOC_A,
        "name": "The Hall",
        "labels": ["Location"],
        "summary": "A hall",
        "attributes": {"_kind": "location", "_location_uuid": None, "_is_dead": False},
    }
    incoming_edge = {
        "uuid": "edge-001",
        "name": "LOCATED_IN",
        "source": {"uuid": ENT_1},
        "target": {"uuid": LOC_A},
        "expired_at": None,
    }
    entity_response = _server_entity_dict(uuid=ENT_1)

    kg = MagicMock()
    kg.get_edges.return_value = [incoming_edge]
    kg.get_entity_or_none.return_value = entity_response

    proj = KgProjection(kg=kg)
    results = await proj.entities_at_location(LOC_A)

    kg.get_edges.assert_called_once()
    call_args, call_kwargs = kg.get_edges.call_args
    called_uuid = call_args[0] if call_args else call_kwargs.get("entity_uuid")
    assert called_uuid == LOC_A

    assert len(results) == 1
    assert results[0]["uuid"] == ENT_1


@pytest.mark.asyncio
async def test_real_items_at_location_returns_only_ownerless() -> None:
    """items_at_location returns only items with no owner_uuid."""
    floor_edge = {
        "uuid": "edge-floor",
        "name": "LOCATED_IN",
        "source": {"uuid": ITEM_1},
        "target": {"uuid": LOC_A},
        "expired_at": None,
    }
    floor_item_response = {
        "uuid": ITEM_1,
        "name": "Iron Sword",
        "labels": ["Item", "Weapon"],
        "summary": "A sword",
        "attributes": {
            "_kind": "item",
            "_location_uuid": LOC_A,
            "_owner_uuid": None,
            "damage": 5,
        },
    }
    owned_edge = {
        "uuid": "edge-owned",
        "name": "LOCATED_IN",
        "source": {"uuid": ITEM_2},
        "target": {"uuid": LOC_A},
        "expired_at": None,
    }
    owned_item_response = {
        "uuid": ITEM_2,
        "name": "Shield",
        "labels": ["Item", "Armor"],
        "summary": "A shield",
        "attributes": {
            "_kind": "item",
            "_location_uuid": LOC_A,
            "_owner_uuid": ENT_1,  # has an owner
            "defense": 3,
        },
    }

    kg = MagicMock()
    kg.get_edges.return_value = [floor_edge, owned_edge]
    kg.get_entity_or_none.side_effect = lambda uuid: (
        floor_item_response if uuid == ITEM_1 else owned_item_response
    )

    proj = KgProjection(kg=kg)
    results = await proj.items_at_location(LOC_A)

    assert len(results) == 1
    assert results[0]["uuid"] == ITEM_1
