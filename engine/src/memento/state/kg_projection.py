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

A single LOCATED_IN edge (entity → location) is maintained so that
entities_at_location / items_at_location can query via
  get_edges(location_uuid, direction="incoming", edge_type="LOCATED_IN")
On a location change the old LOCATED_IN edge is expired (update_edge expired_at)
and a new one is created.

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


def _to_kg_attributes(doc: dict[str, Any]) -> dict[str, Any]:
    """Build the flat KG attribute dict from an EntityDoc or ItemDoc."""
    attrs: dict[str, Any] = {}
    # Reserved prefix scalars
    attrs["_kind"] = doc.get("kind")
    attrs["_location_uuid"] = doc.get("location_uuid")
    if "is_dead" in doc:
        attrs["_is_dead"] = doc["is_dead"]
    if "owner_uuid" in doc:
        attrs["_owner_uuid"] = doc.get("owner_uuid")
    # Game attrs merged in
    for k, v in (doc.get("attrs") or {}).items():
        attrs[k] = v
    return attrs


def _from_kg_entity(entity: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct an EntityDoc or ItemDoc from a raw KG entity dict."""
    raw_attrs: dict[str, Any] = entity.get("attributes") or {}
    kind: str = raw_attrs.get("_kind", "")

    # Separate reserved keys from game attrs
    game_attrs: dict[str, Any] = {k: v for k, v in raw_attrs.items() if k not in _RESERVED}

    base: dict[str, Any] = {
        "uuid": entity.get("uuid", ""),
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
        """Persist a new entity to the KG and return the server-assigned uuid.

        The doc must conform to EntityDoc or ItemDoc shape.  The server assigns
        the canonical uuid; the returned value supersedes doc["uuid"].
        """
        ...

    async def update(self, doc: dict[str, Any]) -> None:
        """Update an existing KG entity.

        doc["uuid"] must already be set (the server-assigned uuid from create).
        On a location change the old LOCATED_IN edge is expired and a new one
        is created pointing to the new location.
        """
        ...

    async def get(self, uuid: str) -> dict[str, Any] | None:
        """Reconstruct an EntityDoc or ItemDoc from the KG, or None if absent."""
        ...

    async def entities_at_location(self, location_uuid: str) -> list[dict[str, Any]]:
        """Return non-item entities (kind != 'item') located at location_uuid."""
        ...

    async def items_at_location(self, location_uuid: str) -> list[dict[str, Any]]:
        """Return floor items (kind == 'item', owner_uuid is None) at location_uuid."""
        ...


# ---------------------------------------------------------------------------
# KgProjection (live Bonfires KG)   alias: KgProjectionReal
# ---------------------------------------------------------------------------


class KgProjection:
    """Wraps a KGService instance.  Every blocking SDK call runs in to_thread.

    Usage::

        from memento.bonfires_client import get_client
        proj = KgProjection(kg=get_client().kg)

    Satisfies KgProjectionProtocol at runtime.
    """

    def __init__(self, kg: Any) -> None:
        self._kg = kg

    async def create(self, doc: dict[str, Any]) -> str:
        """Create a KG entity and return the server-assigned uuid.

        Also creates the initial LOCATED_IN edge if location_uuid is set.
        """
        kg = self._kg
        name = doc.get("name", "")
        labels = list(doc.get("labels") or [])
        attributes = _to_kg_attributes(doc)
        summary = _summary(doc)

        entity_uuid: str = await asyncio.to_thread(
            kg.create_entity, name, labels, attributes, summary
        )

        loc_uuid = doc.get("location_uuid")
        if loc_uuid:
            await asyncio.to_thread(
                kg.create_edge, entity_uuid, loc_uuid, "LOCATED_IN",
                f"{name} is located in {loc_uuid}"
            )

        return entity_uuid

    async def update(self, doc: dict[str, Any]) -> None:
        """Update a KG entity; expire+recreate LOCATED_IN edge on location change."""
        kg = self._kg
        entity_uuid: str = doc["uuid"]
        name = doc.get("name", "")
        labels = list(doc.get("labels") or [])
        attributes = _to_kg_attributes(doc)
        summary = _summary(doc)

        # Fetch current entity to detect location change
        current: dict[str, Any] | None = await asyncio.to_thread(
            kg.get_entity_or_none, entity_uuid
        )
        old_location: str | None = None
        if current:
            old_attrs = current.get("attributes") or {}
            old_location = old_attrs.get("_location_uuid")

        new_location = doc.get("location_uuid")

        # Update entity attributes
        await asyncio.to_thread(
            kg.update_entity, entity_uuid, name, labels, summary, attributes
        )

        # Handle LOCATED_IN edge transition
        if old_location != new_location:
            # Expire old edge if it exists
            existing_edges: list[dict[str, Any]] = await asyncio.to_thread(
                kg.get_edges, entity_uuid, "outgoing", "LOCATED_IN"
            )
            now_iso = datetime.now(tz=timezone.utc).isoformat()
            for edge in existing_edges:
                if edge.get("expired_at") is None:
                    edge_uuid = edge.get("uuid", "")
                    if edge_uuid:
                        await asyncio.to_thread(
                            kg.update_edge, edge_uuid, now_iso
                        )

            # Create new edge
            if new_location:
                await asyncio.to_thread(
                    kg.create_edge, entity_uuid, new_location, "LOCATED_IN",
                    f"{name} is located in {new_location}"
                )

    async def get(self, uuid: str) -> dict[str, Any] | None:
        """Reconstruct an EntityDoc or ItemDoc from the KG, or None if absent."""
        kg = self._kg
        entity: dict[str, Any] | None = await asyncio.to_thread(
            kg.get_entity_or_none, uuid
        )
        if entity is None:
            return None
        return _from_kg_entity(entity)

    async def entities_at_location(self, location_uuid: str) -> list[dict[str, Any]]:
        """Non-item entities at location_uuid via incoming LOCATED_IN edges."""
        kg = self._kg
        edges: list[dict[str, Any]] = await asyncio.to_thread(
            kg.get_edges, location_uuid, "incoming", "LOCATED_IN"
        )
        results: list[dict[str, Any]] = []
        for edge in edges:
            if edge.get("expired_at") is not None:
                continue
            src_uuid = (edge.get("source") or {}).get("uuid")
            if not src_uuid:
                continue
            entity = await asyncio.to_thread(kg.get_entity_or_none, src_uuid)
            if entity is None:
                continue
            doc = _from_kg_entity(entity)
            if doc.get("kind") != "item":
                results.append(doc)
        return results

    async def items_at_location(self, location_uuid: str) -> list[dict[str, Any]]:
        """Floor items (kind=='item', owner_uuid is None) at location_uuid."""
        kg = self._kg
        edges: list[dict[str, Any]] = await asyncio.to_thread(
            kg.get_edges, location_uuid, "incoming", "LOCATED_IN"
        )
        results: list[dict[str, Any]] = []
        for edge in edges:
            if edge.get("expired_at") is not None:
                continue
            src_uuid = (edge.get("source") or {}).get("uuid")
            if not src_uuid:
                continue
            entity = await asyncio.to_thread(kg.get_entity_or_none, src_uuid)
            if entity is None:
                continue
            doc = _from_kg_entity(entity)
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
