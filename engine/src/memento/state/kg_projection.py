"""KgProjection — adapter that materializes game state into the Bonfires KG.

This module provides:
  KgProjection        — Protocol (§ interface contract)
  KgProjectionReal    — wraps get_client().kg; every SDK call via asyncio.to_thread
  KgProjectionFake    — in-memory dict-backed double for tests / integration

Storage model
-------------
Each EntityDoc / ItemDoc is persisted as ONE KG entity:

  KG entity labels    ← doc["labels"]   (for capability/codex queries)
  KG entity name      ← doc["name"]
  KG entity attributes carry the doc scalars using a reserved _-prefix:
    _kind             ← doc["kind"]
    _location_uuid    ← doc["location_uuid"]
    _is_dead          ← doc["is_dead"]         (EntityDoc only)
    _owner_uuid       ← doc["owner_uuid"]       (ItemDoc only)
  All remaining entries in doc["attrs"] are merged in at the same level.

  In addition, the attribute "engine_uuid" is always written so the KG entity
  carries the engine-side uuid even though the KG assigns its own uuid.

A single LOCATED_IN edge (entity → location) is maintained so that
entities_at_location / items_at_location can query via
  get_edges(location_uuid, direction="incoming", edge_type="LOCATED_IN")
On a location change the old LOCATED_IN edge is expired (update_edge expired_at)
and a new one is created.

UUID indirection (C3a fix)
--------------------------
The real KG assigns its OWN uuid when create_entity is called, which differs
from doc["uuid"] (the engine's stable uuid).  KgProjection maintains two maps:

  self._engine_to_kg: dict[str, str]   engine uuid → KG-assigned uuid
  self._kg_to_engine: dict[str, str]   KG uuid     → engine uuid

These are populated in create() and used in all subsequent calls:
  • get(engine_uuid)          → resolve kg_uuid, fetch, reconstruct with engine uuid
  • update(doc)               → resolve kg_uuid from doc["uuid"], call update_entity
  • entities_at_location      → resolve location's kg_uuid, iterate edges (KG uuids),
                                 resolve each member's engine uuid from engine_uuid attr
  • items_at_location         → same as above, filtered to floor items

A fresh KgProjection is built per-player in /start so the maps are player-scoped
(no cross-player uuid collision — C3c isolation).

Out-of-scope (noted for Task 3 / future):
  - CARRIES edges (inventory stored in attrs["inventory"] as a UUID list)
  - HAS_STATUS "DEAD" edges (is_dead stored in _is_dead attribute)
  - DIED_IN / other relation edges (handled by ChainMirror / link method)

asyncio.to_thread
-----------------
All KGService methods are synchronous blocking HTTP.  KgProjectionReal wraps
every call in asyncio.to_thread so the event loop is never blocked.
KgProjectionFake is pure in-memory; its methods are natively async.
"""

from __future__ import annotations

import asyncio
import uuid as _uuid_mod
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from memento.state.repository import EntityDoc, ItemDoc

# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

_RESERVED = frozenset({"_kind", "_location_uuid", "_is_dead", "_owner_uuid"})
# engine_uuid is written into KG attrs; exclude from game attrs when reading back
_RESERVED_READ = _RESERVED | frozenset({"engine_uuid"})


def _to_kg_attributes(doc: dict[str, Any], *, engine_uuid: str) -> dict[str, Any]:
    """Build the flat KG attribute dict from an EntityDoc or ItemDoc.

    Embeds engine_uuid so the KG entity can be recovered back to its
    engine-side uuid without relying on the in-memory indirection map
    (useful for disaster recovery / future cross-session lookup).
    """
    attrs: dict[str, Any] = {}
    # Reserved prefix scalars
    attrs["_kind"] = doc.get("kind")
    attrs["_location_uuid"] = doc.get("location_uuid")
    if "is_dead" in doc:
        attrs["_is_dead"] = doc["is_dead"]
    if "owner_uuid" in doc:
        attrs["_owner_uuid"] = doc.get("owner_uuid")
    # Embed the engine uuid
    attrs["engine_uuid"] = engine_uuid
    # Game attrs merged in
    for k, v in (doc.get("attrs") or {}).items():
        attrs[k] = v
    return attrs


def _from_kg_entity(
    entity: dict[str, Any],
    *,
    engine_uuid: str | None = None,
) -> dict[str, Any]:
    """Reconstruct an EntityDoc or ItemDoc from a raw KG entity dict.

    If engine_uuid is provided (resolved from the indirection map), it is
    used as the doc's uuid.  Otherwise the entity's own engine_uuid attribute
    is used, falling back to the KG uuid itself for pre-existing entities
    that have no engine_uuid attr.
    """
    raw_attrs: dict[str, Any] = entity.get("attributes") or {}
    kind: str = raw_attrs.get("_kind", "")

    # Resolve the uuid to return
    resolved_uuid: str
    if engine_uuid is not None:
        resolved_uuid = engine_uuid
    else:
        resolved_uuid = raw_attrs.get("engine_uuid") or entity.get("uuid", "")

    # Separate reserved keys from game attrs (strip both prefixed + engine_uuid)
    game_attrs: dict[str, Any] = {
        k: v for k, v in raw_attrs.items() if k not in _RESERVED_READ
    }

    base: dict[str, Any] = {
        "uuid": resolved_uuid,
        "name": entity.get("name", ""),
        "kind": kind,
        "labels": list(entity.get("labels") or []),
        "location_uuid": raw_attrs.get("_location_uuid"),
        "attrs": game_attrs,
    }
    if kind == "item":
        base["owner_uuid"] = raw_attrs.get("_owner_uuid")
    else:
        base["is_dead"] = bool(raw_attrs.get("_is_dead", False))
    return base


def _summary(doc: dict[str, Any]) -> str:
    """Generate a minimal KG summary string from a doc."""
    name = doc.get("name", "")
    kind = doc.get("kind", "")
    return f"{name} ({kind})"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class KgProjectionProtocol(Protocol):
    """Structural type for KG projection adapters.

    Both KgProjection (live) and KgProjectionFake satisfy this Protocol.
    Task 3 (EventSourcedStateRepository) types its dependency as
    KgProjectionProtocol so it accepts both implementations.

    Implementations
    ---------------
    KgProjection      — wraps the live Bonfires SDK KGService (alias: KgProjectionReal)
    KgProjectionFake  — in-memory dict for tests (honours doc["uuid"] if set)
    """

    async def create(self, doc: dict[str, Any]) -> str:
        """Persist a new entity; return the ENGINE uuid (doc["uuid"]).

        The doc must conform to EntityDoc or ItemDoc shape.  The KG assigns
        its own server uuid internally; the returned value is always the
        engine uuid so callers that keep doc["uuid"] remain correct.
        """
        ...

    async def update(self, doc: dict[str, Any]) -> None:
        """Update an existing KG entity.

        doc["uuid"] is the ENGINE uuid (from create).  The projection resolves
        it to the KG uuid via its internal indirection map.
        On a location change the old LOCATED_IN edge is expired and a new one
        is created pointing to the new location.
        """
        ...

    async def get(self, uuid: str) -> dict[str, Any] | None:
        """Reconstruct an EntityDoc or ItemDoc from the KG, or None if absent.

        uuid is the ENGINE uuid.  Returns a doc whose uuid == the engine uuid.
        """
        ...

    async def entities_at_location(self, location_uuid: str) -> list[dict[str, Any]]:
        """Return non-item entities (kind != 'item') located at location_uuid.

        location_uuid is the ENGINE uuid of the location entity.
        Returned docs use ENGINE uuids.
        """
        ...

    async def items_at_location(self, location_uuid: str) -> list[dict[str, Any]]:
        """Return floor items (kind == 'item', owner_uuid is None) at location_uuid.

        location_uuid is the ENGINE uuid of the location entity.
        Returned docs use ENGINE uuids.
        """
        ...

    def kg_uuid_for(self, engine_uuid: str) -> str | None:
        """Return the KG uuid mapped from an engine uuid, or None if unmapped."""
        ...


# ---------------------------------------------------------------------------
# KgProjection (live Bonfires KG)   alias: KgProjectionReal
# ---------------------------------------------------------------------------


class KgProjection:
    """Wraps a KGService instance.  Every blocking SDK call runs in to_thread.

    Maintains an internal engine→KG uuid indirection map so that callers can
    always use the engine's stable uuids.  A fresh instance is built per-player
    in the /start route so maps are player-scoped (C3c isolation).

    Usage::

        from memento.bonfires_client import get_client
        proj = KgProjection(kg=get_client().kg)

    Satisfies KgProjectionProtocol at runtime.
    """

    def __init__(self, kg: Any) -> None:
        self._kg = kg
        # C3a indirection maps — populated in create()
        self._engine_to_kg: dict[str, str] = {}
        self._kg_to_engine: dict[str, str] = {}

    def _register(self, engine_uuid: str, kg_uuid: str) -> None:
        """Record a bidirectional engine↔kg uuid mapping."""
        self._engine_to_kg[engine_uuid] = kg_uuid
        self._kg_to_engine[kg_uuid] = engine_uuid

    def _resolve_kg(self, engine_uuid: str) -> str | None:
        """Return the KG uuid for an engine uuid, or None if unknown."""
        return self._engine_to_kg.get(engine_uuid)

    def kg_uuid_for(self, engine_uuid: str) -> str | None:
        """Public read-only view of the engine→KG indirection map."""
        return self._engine_to_kg.get(engine_uuid)

    def _resolve_engine(self, kg_uuid: str, raw_attrs: dict[str, Any] | None = None) -> str:
        """Return the engine uuid for a KG uuid.

        Falls back to reading engine_uuid from raw_attrs (embedded at create
        time), then to registering kg_uuid↔kg_uuid as a pre-existing entity.
        """
        if kg_uuid in self._kg_to_engine:
            return self._kg_to_engine[kg_uuid]
        # Try to recover from the embedded attr
        attr_engine = (raw_attrs or {}).get("engine_uuid")
        if attr_engine:
            self._register(attr_engine, kg_uuid)
            return attr_engine
        # Pre-existing real entity with no engine_uuid — identity map
        self._register(kg_uuid, kg_uuid)
        return kg_uuid

    async def create(self, doc: dict[str, Any]) -> str:
        """Create a KG entity and return the ENGINE uuid (doc["uuid"]).

        Embeds doc["uuid"] as engine_uuid in the KG attributes so the mapping
        is durable.  Records engine_uuid→kg_uuid in the indirection map.
        Creates the initial LOCATED_IN edge if location_uuid is set.
        """
        kg = self._kg
        engine_uuid: str = doc.get("uuid") or str(_uuid_mod.uuid4())
        name = doc.get("name", "")
        labels = list(doc.get("labels") or [])
        attributes = _to_kg_attributes(doc, engine_uuid=engine_uuid)
        summary = _summary(doc)

        kg_uuid: str = await asyncio.to_thread(
            kg.create_entity, name, labels, attributes, summary
        )
        self._register(engine_uuid, kg_uuid)

        loc_engine_uuid = doc.get("location_uuid")
        if loc_engine_uuid:
            # Resolve location's KG uuid (may already be in map if location was seeded first)
            loc_kg_uuid = self._engine_to_kg.get(loc_engine_uuid, loc_engine_uuid)
            await asyncio.to_thread(
                kg.create_edge, kg_uuid, loc_kg_uuid, "LOCATED_IN",
                f"{name} is located in {loc_engine_uuid}"
            )

        return engine_uuid

    async def update(self, doc: dict[str, Any]) -> None:
        """Update a KG entity; expire+recreate LOCATED_IN edge on location change.

        doc["uuid"] is the ENGINE uuid.  The KG is called with the KG uuid
        resolved from the indirection map.  If the engine uuid is unknown
        (pre-existing entity), falls back to using it directly.
        """
        kg = self._kg
        engine_uuid: str = doc["uuid"]
        kg_uuid = self._engine_to_kg.get(engine_uuid, engine_uuid)

        name = doc.get("name", "")
        labels = list(doc.get("labels") or [])
        attributes = _to_kg_attributes(doc, engine_uuid=engine_uuid)
        summary = _summary(doc)

        # Fetch current entity to detect location change
        current: dict[str, Any] | None = await asyncio.to_thread(
            kg.get_entity_or_none, kg_uuid
        )
        old_location_engine: str | None = None
        if current:
            old_attrs = current.get("attributes") or {}
            # The stored _location_uuid is the ENGINE uuid (we write engine uuids there)
            old_location_engine = old_attrs.get("_location_uuid")

        new_location_engine = doc.get("location_uuid")

        # Update entity attributes (using KG uuid)
        await asyncio.to_thread(
            kg.update_entity, kg_uuid, name, labels, summary, attributes
        )

        # Handle LOCATED_IN edge transition
        if old_location_engine != new_location_engine:
            # Expire old outgoing LOCATED_IN edge
            existing_edges: list[dict[str, Any]] = await asyncio.to_thread(
                kg.get_edges, kg_uuid, "outgoing", "LOCATED_IN"
            )
            now_iso = datetime.now(tz=timezone.utc).isoformat()
            for edge in existing_edges:
                if edge.get("expired_at") is None:
                    edge_uuid = edge.get("uuid", "")
                    if edge_uuid:
                        await asyncio.to_thread(
                            kg.update_edge, edge_uuid, now_iso
                        )

            # Create new edge pointing to the new location's KG uuid
            if new_location_engine:
                new_loc_kg_uuid = self._engine_to_kg.get(new_location_engine, new_location_engine)
                await asyncio.to_thread(
                    kg.create_edge, kg_uuid, new_loc_kg_uuid, "LOCATED_IN",
                    f"{name} is located in {new_location_engine}"
                )

    async def get(self, uuid: str) -> dict[str, Any] | None:
        """Reconstruct an EntityDoc or ItemDoc from the KG, or None if absent.

        uuid is the ENGINE uuid.  Returns None immediately if the engine uuid
        is not in the indirection map (prevents stale KG lookups on wrong uuids).
        The returned doc's uuid is always the engine uuid.
        """
        kg_uuid = self._engine_to_kg.get(uuid)
        if kg_uuid is None:
            return None
        kg = self._kg
        entity: dict[str, Any] | None = await asyncio.to_thread(
            kg.get_entity_or_none, kg_uuid
        )
        if entity is None:
            return None
        return _from_kg_entity(entity, engine_uuid=uuid)

    async def entities_at_location(self, location_uuid: str) -> list[dict[str, Any]]:
        """Non-item entities at location_uuid via incoming LOCATED_IN edges.

        location_uuid is the ENGINE uuid of the location.  Returned docs use
        ENGINE uuids resolved from the engine_uuid attribute of each KG entity.
        """
        kg = self._kg
        loc_kg_uuid = self._engine_to_kg.get(location_uuid, location_uuid)
        edges: list[dict[str, Any]] = await asyncio.to_thread(
            kg.get_edges, loc_kg_uuid, "incoming", "LOCATED_IN"
        )
        results: list[dict[str, Any]] = []
        for edge in edges:
            if edge.get("expired_at") is not None:
                continue
            src_kg_uuid = (edge.get("source") or {}).get("uuid")
            if not src_kg_uuid:
                continue
            entity = await asyncio.to_thread(kg.get_entity_or_none, src_kg_uuid)
            if entity is None:
                continue
            raw_attrs: dict[str, Any] = entity.get("attributes") or {}
            src_engine_uuid = self._resolve_engine(src_kg_uuid, raw_attrs)
            doc = _from_kg_entity(entity, engine_uuid=src_engine_uuid)
            if doc.get("kind") != "item":
                results.append(doc)
        return results

    async def items_at_location(self, location_uuid: str) -> list[dict[str, Any]]:
        """Floor items (kind=='item', owner_uuid is None) at location_uuid.

        location_uuid is the ENGINE uuid of the location.  Returned docs use
        ENGINE uuids.
        """
        kg = self._kg
        loc_kg_uuid = self._engine_to_kg.get(location_uuid, location_uuid)
        edges: list[dict[str, Any]] = await asyncio.to_thread(
            kg.get_edges, loc_kg_uuid, "incoming", "LOCATED_IN"
        )
        results: list[dict[str, Any]] = []
        for edge in edges:
            if edge.get("expired_at") is not None:
                continue
            src_kg_uuid = (edge.get("source") or {}).get("uuid")
            if not src_kg_uuid:
                continue
            entity = await asyncio.to_thread(kg.get_entity_or_none, src_kg_uuid)
            if entity is None:
                continue
            raw_attrs: dict[str, Any] = entity.get("attributes") or {}
            src_engine_uuid = self._resolve_engine(src_kg_uuid, raw_attrs)
            doc = _from_kg_entity(entity, engine_uuid=src_engine_uuid)
            if doc.get("kind") == "item" and doc.get("owner_uuid") is None:
                results.append(doc)
        return results


# Backward-compat alias: KgProjectionReal → KgProjection
KgProjectionReal = KgProjection


# ---------------------------------------------------------------------------
# KgProjectionFake — in-memory double
# ---------------------------------------------------------------------------


class KgProjectionFake:
    """In-memory KgProjection for tests and integration suites.

    Stable fixture UUIDs:
        If doc["uuid"] is present and non-empty, that value is used as the
        stored key (so test fixtures keep predictable UUIDs).  If absent or
        empty, a new uuid4 is generated.

    Location membership:
        The fake maintains an internal location→set[uuid] index so that
        entities_at_location / items_at_location are O(n_at_loc) rather than
        a full scan.

    CARRIES / HAS_STATUS edges are NOT modelled — inventory lives in
    attrs["inventory"] and is_dead in is_dead, matching KgProjectionReal.
    """

    def __init__(self) -> None:
        # uuid → stored doc dict
        self._store: dict[str, dict[str, Any]] = {}
        # location_uuid → set of entity uuids
        self._by_location: dict[str, set[str]] = {}

    def _remove_from_location(self, entity_uuid: str, loc: str | None) -> None:
        if loc and loc in self._by_location:
            self._by_location[loc].discard(entity_uuid)

    def _add_to_location(self, entity_uuid: str, loc: str | None) -> None:
        if loc:
            self._by_location.setdefault(loc, set()).add(entity_uuid)

    async def create(self, doc: dict[str, Any]) -> str:
        """Persist a new entity.  Honours doc['uuid'] if present (stable fixtures)."""
        entity_uuid: str = doc.get("uuid") or str(_uuid_mod.uuid4())
        stored = dict(doc)
        stored["uuid"] = entity_uuid
        self._store[entity_uuid] = stored
        self._add_to_location(entity_uuid, stored.get("location_uuid"))
        return entity_uuid

    async def update(self, doc: dict[str, Any]) -> None:
        """Update a stored entity; maintain location index on location_uuid change."""
        entity_uuid: str = doc["uuid"]
        old = self._store.get(entity_uuid)
        old_loc = old.get("location_uuid") if old else None
        new_loc = doc.get("location_uuid")
        if old_loc != new_loc:
            self._remove_from_location(entity_uuid, old_loc)
            self._add_to_location(entity_uuid, new_loc)
        self._store[entity_uuid] = dict(doc)
        self._store[entity_uuid]["uuid"] = entity_uuid

    async def get(self, uuid: str) -> dict[str, Any] | None:
        """Return the stored doc, or None if absent."""
        stored = self._store.get(uuid)
        if stored is None:
            return None
        return dict(stored)

    async def entities_at_location(self, location_uuid: str) -> list[dict[str, Any]]:
        """Non-item entities at location_uuid."""
        uuids = self._by_location.get(location_uuid, set())
        results: list[dict[str, Any]] = []
        for uid in uuids:
            doc = self._store.get(uid)
            if doc and doc.get("kind") != "item":
                results.append(dict(doc))
        return results

    async def items_at_location(self, location_uuid: str) -> list[dict[str, Any]]:
        """Floor items (kind=='item', owner_uuid is None) at location_uuid."""
        uuids = self._by_location.get(location_uuid, set())
        results: list[dict[str, Any]] = []
        for uid in uuids:
            doc = self._store.get(uid)
            if doc and doc.get("kind") == "item" and doc.get("owner_uuid") is None:
                results.append(dict(doc))
        return results

    def kg_uuid_for(self, engine_uuid: str) -> str | None:
        """Return the engine uuid itself if it exists in the store, else None (identity map)."""
        return engine_uuid if engine_uuid in self._store else None
