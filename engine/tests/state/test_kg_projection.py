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
  - C3a: create stores engine→kg mapping; get(engine_uuid) works when KG uses different uuid
  - C3a: entities_at_location returns docs with engine uuids (not KG uuids)
  - C3a: update uses KG uuid internally after create
  - create calls kg.create_entity with mapped labels+attributes+engine_uuid
  - create returns the engine uuid (not server-assigned uuid)
  - get after create reconstructs EntityDoc with engine uuid
  - get returns None when engine uuid not in indirection map
  - update calls kg.update_entity with KG uuid resending name+labels+summary
  - update calls kg.get_edges and update_edge when location_uuid changes (uses KG uuids)
  - entities_at_location queries kg.get_edges with LOCATED_IN/incoming (KG location uuid)
  - items_at_location returns only owner-less items (engine uuids)
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

# UUID constants used across real-KG tests
ENGINE_UUID = ENT_1          # the engine's stable uuid
ITEM_ENGINE_UUID = ITEM_1    # engine uuid for an item


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
    """Simulate what the server returns from get_entity_or_none.

    The attributes dict includes engine_uuid so _from_kg_entity can
    reconstruct the engine-side uuid after the indirection map resolves.
    """
    attrs: dict[str, Any] = attributes if attributes is not None else {
        "_kind": "character",
        "_location_uuid": LOC_A,
        "_is_dead": False,
        "hp": 20,
        "max_hp": 20,
        "inventory": [],
    }
    # Inject engine_uuid unless the caller already provided it
    if "engine_uuid" not in attrs:
        attrs = dict(attrs)
        attrs["engine_uuid"] = ENGINE_UUID
    return {
        "uuid": uuid,
        "name": name,
        "labels": labels or ["Character", "NPC"],
        "summary": "Test NPC summary",
        "attributes": attrs,
    }


# ---------------------------------------------------------------------------
# C3a regression guard — UUID indirection: KG assigns different uuid
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_indirection_get_by_engine_uuid_after_server_assigns_different_uuid() -> None:
    """C3a: after create, get(engine_uuid) returns the doc even though the KG
    stored a different (server-assigned) uuid.

    The mock's create_entity returns SERVER_UUID != ENGINE_UUID.
    After create, the indirection map must translate engine→kg so that
    get(engine_uuid) fetches the kg entity by kg_uuid and returns a doc
    whose uuid == engine_uuid.
    """
    server_entity = _server_entity_dict(
        uuid=SERVER_UUID,
        attributes={
            "_kind": "character",
            "_location_uuid": LOC_A,
            "_is_dead": False,
            "hp": 20,
            "max_hp": 20,
            "inventory": [],
            "engine_uuid": ENGINE_UUID,
        },
    )
    kg = _make_kg_stub(
        create_entity_return=SERVER_UUID,
        get_entity_return=server_entity,
    )
    proj = KgProjection(kg=kg)
    doc = _entity(uuid=ENGINE_UUID, loc=LOC_A)

    # create returns the engine uuid (not the server uuid)
    returned_uuid = await proj.create(doc)
    assert returned_uuid == ENGINE_UUID, (
        f"create must return engine uuid; got {returned_uuid!r}"
    )

    # get by engine uuid must work even though KG has a different uuid
    result = await proj.get(ENGINE_UUID)
    assert result is not None, "get(engine_uuid) returned None — indirection broken"
    assert result["uuid"] == ENGINE_UUID, (
        f"returned doc uuid must be engine uuid; got {result['uuid']!r}"
    )
    assert result["name"] == "Test NPC"
    assert result["kind"] == "character"
    assert result["location_uuid"] == LOC_A
    assert result["is_dead"] is False

    # The KG was called with the server uuid, not the engine uuid
    kg.get_entity_or_none.assert_called_once_with(SERVER_UUID)


@pytest.mark.asyncio
async def test_real_indirection_entities_at_location_returns_engine_uuids() -> None:
    """C3a: entities_at_location must return docs with ENGINE uuids, not KG uuids.

    The edge's source.uuid is the KG uuid (SERVER_UUID). The entity's
    engine_uuid attribute must be used to reconstruct the engine uuid.
    """
    server_entity = _server_entity_dict(
        uuid=SERVER_UUID,
        attributes={
            "_kind": "character",
            "_location_uuid": LOC_A,
            "_is_dead": False,
            "hp": 20,
            "inventory": [],
            "engine_uuid": ENGINE_UUID,
        },
    )
    # Edges reference KG uuids
    loc_server_a = "loc-server-uuid-aaaa"
    incoming_edge = {
        "uuid": "edge-001",
        "name": "LOCATED_IN",
        "source": {"uuid": SERVER_UUID},  # KG uuid in the edge
        "target": {"uuid": loc_server_a},
        "expired_at": None,
    }

    kg = MagicMock()
    kg.create_edge.return_value = {"uuid": "edge-uuid-0001"}
    kg.update_entity.return_value = {}
    kg.get_edges.return_value = [incoming_edge]
    kg.get_entity_or_none.return_value = server_entity

    proj = KgProjection(kg=kg)

    # Seed location indirection
    kg.create_entity.return_value = loc_server_a
    await proj.create({
        "uuid": LOC_A,
        "name": "The Hall",
        "kind": "location",
        "labels": ["Location"],
        "location_uuid": None,
        "attrs": {},
        "is_dead": False,
    })
    # Seed entity indirection
    kg.create_entity.return_value = SERVER_UUID
    await proj.create(_entity(uuid=ENGINE_UUID, loc=LOC_A))
    kg.get_entity_or_none.return_value = server_entity

    results = await proj.entities_at_location(LOC_A)
    assert len(results) == 1, f"Expected 1 entity, got {len(results)}: {results}"
    assert results[0]["uuid"] == ENGINE_UUID, (
        f"entity uuid must be engine uuid; got {results[0]['uuid']!r}"
    )


@pytest.mark.asyncio
async def test_real_indirection_update_uses_kg_uuid() -> None:
    """C3a: update after create uses the KG uuid for the update_entity call."""
    server_entity = _server_entity_dict(
        uuid=SERVER_UUID,
        attributes={
            "_kind": "character",
            "_location_uuid": LOC_A,
            "_is_dead": False,
            "hp": 20,
            "inventory": [],
            "engine_uuid": ENGINE_UUID,
        },
    )
    kg = _make_kg_stub(
        create_entity_return=SERVER_UUID,
        get_entity_return=server_entity,
    )
    proj = KgProjection(kg=kg)
    doc = _entity(uuid=ENGINE_UUID, loc=LOC_A)
    await proj.create(doc)

    # Update with a field change — same location so no edge transition
    updated = dict(doc)
    updated["attrs"] = {**doc["attrs"], "hp": 5}
    await proj.update(updated)  # type: ignore[arg-type]

    kg.update_entity.assert_called_once()
    update_args, update_kwargs = kg.update_entity.call_args
    # The FIRST positional arg to update_entity must be the KG (server) uuid
    called_uuid = update_args[0] if update_args else update_kwargs.get("uuid")
    assert called_uuid == SERVER_UUID, (
        f"update_entity must be called with KG uuid; got {called_uuid!r}"
    )


# ---------------------------------------------------------------------------
# Original real-KG stub tests (updated for indirection semantics)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_create_calls_kg_create_entity() -> None:
    """create calls kg.create_entity with mapped labels + attributes + engine_uuid."""
    kg = _make_kg_stub()
    proj = KgProjection(kg=kg)
    doc = _entity()
    returned_uuid = await proj.create(doc)

    # After indirection: create returns the ENGINE uuid, not the server uuid
    assert returned_uuid == doc["uuid"]
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
    # engine_uuid must be embedded so KG entity carries it
    assert passed_attrs["engine_uuid"] == doc["uuid"]


@pytest.mark.asyncio
async def test_real_create_returns_engine_uuid() -> None:
    """create returns the engine (doc) uuid, not the server-assigned uuid."""
    kg = _make_kg_stub(create_entity_return="server-uuid-XYZ")
    proj = KgProjection(kg=kg)
    doc = _entity()
    returned = await proj.create(doc)
    assert returned == doc["uuid"], (
        f"create must return engine uuid {doc['uuid']!r}, not server uuid; got {returned!r}"
    )


@pytest.mark.asyncio
async def test_real_get_reconstructs_entity_doc() -> None:
    """get(engine_uuid) after create reconstructs an EntityDoc with engine uuid."""
    server_response = _server_entity_dict()
    kg = _make_kg_stub(create_entity_return=SERVER_UUID, get_entity_return=server_response)
    proj = KgProjection(kg=kg)

    # Must create first to populate indirection map
    doc = _entity(uuid=ENGINE_UUID, loc=LOC_A)
    await proj.create(doc)

    result = await proj.get(ENGINE_UUID)
    # get_entity_or_none is called with the KG (server) uuid
    kg.get_entity_or_none.assert_called_once_with(SERVER_UUID)
    assert result is not None
    assert result["uuid"] == ENGINE_UUID  # reconstructed as engine uuid
    assert result["name"] == "Test NPC"
    assert result["kind"] == "character"
    assert result["location_uuid"] == LOC_A
    assert result["is_dead"] is False


@pytest.mark.asyncio
async def test_real_get_returns_none_when_missing() -> None:
    """get returns None when the engine uuid is not in the indirection map."""
    kg = _make_kg_stub(get_entity_return=None)
    proj = KgProjection(kg=kg)
    result = await proj.get("no-such-uuid")
    assert result is None
    # No KG call should be made for an unknown engine uuid
    kg.get_entity_or_none.assert_not_called()


@pytest.mark.asyncio
async def test_real_update_calls_update_entity_with_resent_fields() -> None:
    """update calls kg.update_entity with the KG uuid and resent name+labels."""
    server_response = _server_entity_dict()
    kg = _make_kg_stub(create_entity_return=SERVER_UUID, get_entity_return=server_response)
    proj = KgProjection(kg=kg)

    doc = _entity(uuid=ENGINE_UUID, loc=LOC_A)
    await proj.create(doc)  # populate indirection map

    updated = dict(doc)
    updated["attrs"] = {**doc["attrs"], "hp": 10}
    await proj.update(updated)  # type: ignore[arg-type]

    kg.update_entity.assert_called_once()
    args, kwargs = kg.update_entity.call_args
    # uuid is first positional arg — must be KG (server) uuid
    called_uuid = args[0] if args else kwargs.get("uuid")
    assert called_uuid == SERVER_UUID, (
        f"update_entity must use KG uuid; got {called_uuid!r}"
    )
    # name must be resent
    called_name = args[1] if len(args) > 1 else kwargs.get("name")
    assert called_name == doc["name"]
    # labels must be resent
    called_labels = args[2] if len(args) > 2 else kwargs.get("labels")
    assert called_labels == doc["labels"]


@pytest.mark.asyncio
async def test_real_update_creates_new_located_in_edge_on_location_change() -> None:
    """update expires old LOCATED_IN edge and creates a new one when location changes.

    Edge target uuid must be the KG uuid of the new location (not engine uuid).
    """
    loc_server_a = "loc-server-uuid-aaaa"
    loc_server_b = "loc-server-uuid-bbbb"
    old_edge = {
        "uuid": "old-edge-uuid",
        "name": "LOCATED_IN",
        "source": {"uuid": SERVER_UUID},  # KG source uuid in edge
        "target": {"uuid": loc_server_a},
        "expired_at": None,
        "valid_at": None,
        "invalid_at": None,
    }
    server_response = _server_entity_dict(
        uuid=SERVER_UUID,
        attributes={
            "_kind": "character",
            "_location_uuid": LOC_A,
            "_is_dead": False,
            "hp": 20,
            "max_hp": 20,
            "inventory": [],
            "engine_uuid": ENGINE_UUID,
        },
    )

    kg = MagicMock()
    kg.create_edge.return_value = {"uuid": "edge-uuid-0001"}
    kg.update_edge.return_value = {}
    kg.update_entity.return_value = {}
    kg.get_edges.return_value = [old_edge]
    kg.get_entity_or_none.return_value = server_response

    proj = KgProjection(kg=kg)

    # Seed location A indirection
    kg.create_entity.return_value = loc_server_a
    await proj.create({
        "uuid": LOC_A,
        "name": "Hall A",
        "kind": "location",
        "labels": ["Location"],
        "location_uuid": None,
        "attrs": {},
        "is_dead": False,
    })
    # Seed location B indirection
    kg.create_entity.return_value = loc_server_b
    await proj.create({
        "uuid": LOC_B,
        "name": "Hall B",
        "kind": "location",
        "labels": ["Location"],
        "location_uuid": None,
        "attrs": {},
        "is_dead": False,
    })
    # Seed entity indirection
    kg.create_entity.return_value = SERVER_UUID
    await proj.create(_entity(uuid=ENGINE_UUID, loc=LOC_A))
    kg.get_entity_or_none.return_value = server_response

    # Move entity to LOC_B (using engine uuid)
    doc = _entity(uuid=ENGINE_UUID, loc=LOC_B)
    await proj.update(doc)

    # Old edge should be expired
    kg.update_edge.assert_called_once()
    update_args, update_kwargs = kg.update_edge.call_args
    called_edge_uuid = update_args[0] if update_args else update_kwargs.get("edge_uuid")
    assert called_edge_uuid == "old-edge-uuid"

    # New edge should be created; target must be KG uuid for LOC_B
    kg.create_edge.assert_called()
    last_create_args, last_create_kwargs = kg.create_edge.call_args
    all_create: dict[str, Any] = {**last_create_kwargs}
    if last_create_args:
        all_create["source_uuid"] = last_create_args[0]
        all_create["target_uuid"] = (
            last_create_args[1] if len(last_create_args) > 1
            else all_create.get("target_uuid")
        )
    assert all_create.get("target_uuid") == loc_server_b, (
        f"new LOCATED_IN target must be KG uuid for LOC_B ({loc_server_b!r}); "
        f"got {all_create.get('target_uuid')!r}"
    )


@pytest.mark.asyncio
async def test_real_entities_at_location_queries_kg_edges() -> None:
    """entities_at_location calls get_edges with KG location uuid, returns engine uuids."""
    loc_server_a = "loc-server-uuid-aaaa"
    server_entity = _server_entity_dict(
        uuid=SERVER_UUID,
        attributes={
            "_kind": "character",
            "_location_uuid": LOC_A,
            "_is_dead": False,
            "hp": 20,
            "inventory": [],
            "engine_uuid": ENGINE_UUID,
        },
    )
    incoming_edge = {
        "uuid": "edge-001",
        "name": "LOCATED_IN",
        "source": {"uuid": SERVER_UUID},  # KG uuid in edge
        "target": {"uuid": loc_server_a},
        "expired_at": None,
    }

    kg = MagicMock()
    kg.create_edge.return_value = {"uuid": "edge-uuid-0001"}
    kg.update_entity.return_value = {}
    kg.get_edges.return_value = [incoming_edge]
    kg.get_entity_or_none.return_value = server_entity

    proj = KgProjection(kg=kg)

    # Seed location indirection
    kg.create_entity.return_value = loc_server_a
    await proj.create({
        "uuid": LOC_A,
        "name": "The Hall",
        "kind": "location",
        "labels": ["Location"],
        "location_uuid": None,
        "attrs": {},
        "is_dead": False,
    })
    # Seed entity indirection
    kg.create_entity.return_value = SERVER_UUID
    await proj.create(_entity(uuid=ENGINE_UUID, loc=LOC_A))
    kg.get_entity_or_none.return_value = server_entity

    results = await proj.entities_at_location(LOC_A)

    # get_edges called with the KG uuid for LOC_A (not engine uuid)
    kg.get_edges.assert_called()
    call_args, call_kwargs = kg.get_edges.call_args
    called_uuid = call_args[0] if call_args else call_kwargs.get("entity_uuid")
    assert called_uuid == loc_server_a, (
        f"get_edges must use KG uuid for location; got {called_uuid!r}"
    )

    assert len(results) == 1
    assert results[0]["uuid"] == ENGINE_UUID


@pytest.mark.asyncio
async def test_real_items_at_location_returns_only_ownerless() -> None:
    """items_at_location returns only items with no owner_uuid, using engine uuids."""
    floor_server_uuid = "floor-server-uuid-0001"
    owned_server_uuid = "owned-server-uuid-0002"
    loc_server_uuid = "loc-server-uuid-aaaa"

    floor_item_response = {
        "uuid": floor_server_uuid,
        "name": "Iron Sword",
        "labels": ["Item", "Weapon"],
        "summary": "A sword",
        "attributes": {
            "_kind": "item",
            "_location_uuid": LOC_A,
            "_owner_uuid": None,
            "damage": 5,
            "engine_uuid": ITEM_ENGINE_UUID,
        },
    }
    owned_item_response = {
        "uuid": owned_server_uuid,
        "name": "Shield",
        "labels": ["Item", "Armor"],
        "summary": "A shield",
        "attributes": {
            "_kind": "item",
            "_location_uuid": LOC_A,
            "_owner_uuid": ENT_1,
            "defense": 3,
            "engine_uuid": ITEM_2,
        },
    }
    floor_edge = {
        "uuid": "edge-floor",
        "name": "LOCATED_IN",
        "source": {"uuid": floor_server_uuid},
        "target": {"uuid": loc_server_uuid},
        "expired_at": None,
    }
    owned_edge = {
        "uuid": "edge-owned",
        "name": "LOCATED_IN",
        "source": {"uuid": owned_server_uuid},
        "target": {"uuid": loc_server_uuid},
        "expired_at": None,
    }

    kg = MagicMock()
    kg.create_edge.return_value = {"uuid": "edge-uuid-0001"}
    kg.update_entity.return_value = {}
    kg.get_edges.return_value = [floor_edge, owned_edge]
    kg.get_entity_or_none.side_effect = lambda uuid: (
        floor_item_response if uuid == floor_server_uuid
        else owned_item_response if uuid == owned_server_uuid
        else None
    )

    proj = KgProjection(kg=kg)

    # Seed location indirection
    kg.create_entity.return_value = loc_server_uuid
    await proj.create({
        "uuid": LOC_A,
        "name": "The Hall",
        "kind": "location",
        "labels": ["Location"],
        "location_uuid": None,
        "attrs": {},
        "is_dead": False,
    })
    # Seed floor item indirection
    kg.create_entity.return_value = floor_server_uuid
    await proj.create(_item(uuid=ITEM_ENGINE_UUID, owner=None, loc=LOC_A))
    # Seed owned item indirection
    kg.create_entity.return_value = owned_server_uuid
    await proj.create(_item(uuid=ITEM_2, owner=ENT_1, loc=LOC_A))

    results = await proj.items_at_location(LOC_A)

    assert len(results) == 1
    assert results[0]["uuid"] == ITEM_ENGINE_UUID
