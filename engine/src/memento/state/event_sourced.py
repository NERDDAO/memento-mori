"""EventSourcedStateRepository — event-sourced implementation of StateRepository.

Every write fans out to two sinks:
  1. TxLog     — append-only truth record (one TxEntry per write call)
  2. KgProjection — read-side projection (updated in-place via create/update)

ChainMirror firing is NOT the repo's responsibility.  The EffectExecutor's
Phase 3 (chain_kill / chain_transfer primitives) is the single chain authority,
identical to InMemoryStateRepository's contract.  The ``chain`` constructor
param is retained for API compatibility but is NOT used for any writes.

Reads come EXCLUSIVELY from the KgProjection — no internal dict cache.

Delta schema (replayable)
-------------------------
Each TxEntry.deltas list contains one or more StateDelta dicts.  The
_apply_delta() method is the single place that interprets them — used by
both the live write path AND rebuild_projection().

Delta ops:
  "create"    — full doc insert (seed_entity, seed_item, materialize)
                { "op": "create", "doc": <full_doc> }

  "set_attr"  — scalar field mutation
                { "op": "set_attr", "target_uuid": str, "field": str,
                  "before": <old>, "after": <new> }

  "set_top"   — top-level field mutation (e.g. is_dead, location_uuid)
                { "op": "set_top", "target_uuid": str, "field": str,
                  "before": <old>, "after": <new> }

  "move"      — location change + item_ids denorm on from/to locations
                { "op": "move", "target_uuid": str,
                  "from_uuid": str|None, "to_uuid": str }

  "transfer"  — item ownership/location change + inventory/item_ids denorm
                { "op": "transfer", "item_uuid": str,
                  "from_uuid": str|None, "to_uuid": str|None,
                  "to_location_uuid": str|None }

  "link"      — attrs["links"][rel] append
                { "op": "link", "from_uuid": str, "to_uuid": str, "rel": str }

  "unlink"    — attrs["links"][rel] remove
                { "op": "unlink", "from_uuid": str, "to_uuid": str, "rel": str }

rebuild_projection() replays TxLog.for_actor(actor_id) into a fresh
KgProjectionFake by calling _apply_delta() for each delta in each TxEntry.
"""

from __future__ import annotations

import copy
import uuid as _uuid_mod
from typing import Any

from memento.state.chain_mirror import ChainMirror
from memento.state.kg_projection import KgProjectionFake, KgProjectionProtocol
from memento.state.repository import EntityDoc, ExitRecord, ItemDoc, RoomManifest
from memento.state.tx_log import ActivationLog, TxEntry, TxLog


class EventSourcedStateRepository:
    """StateRepository backed by (TxLog, KgProjection).

    Constructor
    -----------
    tx_log          : TxLog          — append-only transaction log
    activation_log  : ActivationLog  — activation provenance (stored but not read here)
    projection      : KgProjectionProtocol — live read-side projection
    chain           : ChainMirror    — accepted for API compatibility; NOT used for
                                       any writes.  ChainMirror firing is the
                                       EffectExecutor's sole responsibility.
    """

    def __init__(
        self,
        tx_log: TxLog,
        activation_log: ActivationLog,
        projection: KgProjectionProtocol,
        chain: ChainMirror,
    ) -> None:
        self._tx_log = tx_log
        self._act_log = activation_log
        self._projection = projection
        self._chain = chain

        # Per-turn context set by set_activation() and cleared after the turn.
        self._activation_id: str = "genesis"
        self._tool: str = ""

    @property
    def projection(self) -> KgProjectionProtocol:
        """The KgProjection backing this repo (lets callers resolve KG uuids)."""
        return self._projection

    # ------------------------------------------------------------------
    # Activation context
    # ------------------------------------------------------------------

    def set_activation(self, activation_id: str, tool: str = "") -> None:
        """Set the activation context for subsequent writes."""
        self._activation_id = activation_id
        self._tool = tool

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _new_tx_id(self) -> str:
        return str(_uuid_mod.uuid4())

    async def _append_tx(
        self,
        actor_id: str,
        deltas: list[dict[str, Any]],
    ) -> None:
        """Append a TxEntry for the current activation context."""
        entry = TxEntry(
            tx_id=self._new_tx_id(),
            activation_id=self._activation_id,
            actor_id=actor_id,
            tool=self._tool,
            deltas=deltas,
        )
        self._tx_log.append(entry)

    # ------------------------------------------------------------------
    # Delta application — used by both write path and rebuild_projection
    # ------------------------------------------------------------------

    @staticmethod
    async def _apply_delta(
        projection: KgProjectionProtocol,
        delta: dict[str, Any],
    ) -> None:
        """Apply a single StateDelta to a KgProjection."""
        op: str = str(delta["op"])

        if op == "create":
            doc = copy.deepcopy(delta["doc"])  # type: ignore[arg-type]
            await projection.create(doc)  # type: ignore[arg-type]

        elif op == "set_attr":
            target_uuid = str(delta["target_uuid"])
            field = str(delta["field"])
            after = delta["after"]

            doc = await projection.get(target_uuid)
            if doc is None:
                return
            attrs = doc.setdefault("attrs", {})
            attrs[field] = after
            await projection.update(doc)

        elif op == "set_top":
            target_uuid = str(delta["target_uuid"])
            field = str(delta["field"])
            after = delta["after"]

            doc = await projection.get(target_uuid)
            if doc is None:
                return
            doc[field] = after  # type: ignore[literal-required]
            await projection.update(doc)

        elif op == "move":
            target_uuid = str(delta["target_uuid"])
            from_uuid: str | None = delta.get("from_uuid")  # type: ignore[assignment]
            to_uuid = str(delta["to_uuid"])

            # Remove from old location's item_ids
            if from_uuid and from_uuid != to_uuid:
                old_loc_doc = await projection.get(from_uuid)
                if old_loc_doc is not None:
                    old_attrs = old_loc_doc.setdefault("attrs", {})
                    old_ids: list[str] = old_attrs.get("item_ids", [])
                    if target_uuid in old_ids:
                        old_ids.remove(target_uuid)
                    old_attrs["item_ids"] = old_ids
                    await projection.update(old_loc_doc)

            # Add to new location's item_ids
            new_loc_doc = await projection.get(to_uuid)
            if new_loc_doc is not None:
                new_attrs = new_loc_doc.setdefault("attrs", {})
                new_ids: list[str] = new_attrs.get("item_ids", [])
                if target_uuid not in new_ids:
                    new_ids.append(target_uuid)
                new_attrs["item_ids"] = new_ids
                await projection.update(new_loc_doc)

            # Update entity location
            entity_doc = await projection.get(target_uuid)
            if entity_doc is not None:
                entity_doc["location_uuid"] = to_uuid
                await projection.update(entity_doc)

        elif op == "transfer":
            item_uuid = str(delta["item_uuid"])
            from_uuid_t: str | None = delta.get("from_uuid")  # type: ignore[assignment]
            to_uuid_t: str | None = delta.get("to_uuid")  # type: ignore[assignment]
            to_location_uuid: str | None = delta.get("to_location_uuid")  # type: ignore[assignment]

            # Remove from source
            if from_uuid_t is not None:
                from_doc = await projection.get(from_uuid_t)
                if from_doc is not None:
                    from_attrs = from_doc.setdefault("attrs", {})
                    if from_doc.get("kind") == "location":
                        ids: list[str] = from_attrs.get("item_ids", [])
                        if item_uuid in ids:
                            ids.remove(item_uuid)
                        from_attrs["item_ids"] = ids
                    else:
                        inv: list[str] = from_attrs.get("inventory", [])
                        if item_uuid in inv:
                            inv.remove(item_uuid)
                        from_attrs["inventory"] = inv
                    await projection.update(from_doc)

            # Add to destination
            item_doc = await projection.get(item_uuid)
            if item_doc is None:
                return

            if to_uuid_t is not None:
                to_doc = await projection.get(to_uuid_t)
                if to_doc is not None:
                    to_attrs = to_doc.setdefault("attrs", {})
                    if to_doc.get("kind") == "location":
                        to_ids: list[str] = to_attrs.get("item_ids", [])
                        if item_uuid not in to_ids:
                            to_ids.append(item_uuid)
                        to_attrs["item_ids"] = to_ids
                    else:
                        to_inv: list[str] = to_attrs.get("inventory", [])
                        if item_uuid not in to_inv:
                            to_inv.append(item_uuid)
                        to_attrs["inventory"] = to_inv
                    await projection.update(to_doc)

                item_doc["owner_uuid"] = to_uuid_t
                item_doc["location_uuid"] = None
            else:
                # Drop to floor
                item_doc["owner_uuid"] = None
                item_doc["location_uuid"] = to_location_uuid
                if to_location_uuid is not None:
                    floor_doc = await projection.get(to_location_uuid)
                    if floor_doc is not None:
                        floor_attrs = floor_doc.setdefault("attrs", {})
                        floor_ids: list[str] = floor_attrs.get("item_ids", [])
                        if item_uuid not in floor_ids:
                            floor_ids.append(item_uuid)
                        floor_attrs["item_ids"] = floor_ids
                        await projection.update(floor_doc)

            await projection.update(item_doc)

        elif op == "link":
            from_uuid_l = str(delta["from_uuid"])
            to_uuid_l = str(delta["to_uuid"])
            rel = str(delta["rel"])

            doc = await projection.get(from_uuid_l)
            if doc is None:
                return
            attrs = doc.setdefault("attrs", {})
            links: dict[str, list[str]] = attrs.setdefault("links", {})
            targets: list[str] = links.setdefault(rel, [])
            if to_uuid_l not in targets:
                targets.append(to_uuid_l)
            await projection.update(doc)

        elif op == "unlink":
            from_uuid_u = str(delta["from_uuid"])
            to_uuid_u = str(delta["to_uuid"])
            rel = str(delta["rel"])

            doc = await projection.get(from_uuid_u)
            if doc is None:
                return
            links = doc.get("attrs", {}).get("links", {})
            targets = links.get(rel, [])
            if to_uuid_u in targets:
                targets.remove(to_uuid_u)
            await projection.update(doc)

    # ------------------------------------------------------------------
    # Seeding helpers (async — Task 5 awaits these)
    # ------------------------------------------------------------------

    async def seed_entity(self, doc: EntityDoc) -> None:
        """Insert or replace an entity doc; logs a genesis TxEntry."""
        # Two independent deepcopies: one for the projection, one for the delta.
        # This ensures the logged genesis delta is immutable even if the
        # projection later mutates attrs in-place.
        proj_copy = copy.deepcopy(dict(doc))
        delta_copy = copy.deepcopy(dict(doc))
        delta: dict[str, Any] = {"op": "create", "doc": delta_copy}
        # Apply to projection
        existing = await self._projection.get(doc["uuid"])
        if existing is not None:
            await self._projection.update(proj_copy)  # type: ignore[arg-type]
        else:
            await self._projection.create(proj_copy)  # type: ignore[arg-type]
        # Log genesis tx — actor_id is the entity's own UUID
        await self._with_genesis(doc["uuid"], [delta])

    async def seed_item(self, doc: ItemDoc) -> None:
        """Insert or replace an item doc; logs a genesis TxEntry."""
        proj_copy = copy.deepcopy(dict(doc))
        delta_copy = copy.deepcopy(dict(doc))
        delta: dict[str, Any] = {"op": "create", "doc": delta_copy}
        existing = await self._projection.get(doc["uuid"])
        if existing is not None:
            await self._projection.update(proj_copy)  # type: ignore[arg-type]
        else:
            await self._projection.create(proj_copy)  # type: ignore[arg-type]
        await self._with_genesis(doc["uuid"], [delta])

    async def _with_genesis(
        self,
        actor_id: str,
        deltas: list[dict[str, Any]],
    ) -> None:
        """Append a TxEntry stamped with activation_id='genesis'."""
        entry = TxEntry(
            tx_id=self._new_tx_id(),
            activation_id="genesis",
            actor_id=actor_id,
            tool="",
            deltas=deltas,
        )
        self._tx_log.append(entry)

    # ------------------------------------------------------------------
    # Reads — delegate entirely to projection
    # ------------------------------------------------------------------

    async def get_entity(self, uuid: str) -> EntityDoc | None:
        doc = await self._projection.get(uuid)
        if doc is None:
            return None
        return copy.deepcopy(doc)  # type: ignore[return-value]

    async def get_labels(self, uuid: str) -> list[str]:
        doc = await self._projection.get(uuid)
        if doc is None:
            return []
        return list(doc.get("labels", []))

    async def get_entities_at_location(self, location_uuid: str) -> list[EntityDoc]:
        docs = await self._projection.entities_at_location(location_uuid)
        return [copy.deepcopy(d) for d in docs]  # type: ignore[misc]

    async def get_items_at_location(self, location_uuid: str) -> list[ItemDoc]:
        docs = await self._projection.items_at_location(location_uuid)
        return [copy.deepcopy(d) for d in docs]  # type: ignore[misc]

    async def get_exits(self, location_uuid: str) -> list[ExitRecord]:
        doc = await self._projection.get(location_uuid)
        if doc is None:
            return []
        raw_exits: list[dict[str, Any]] = doc.get("attrs", {}).get("exits", [])
        return [
            ExitRecord(
                direction=e["direction"],
                target_id=e["target_uuid"],
                locked=e.get("locked", False),
                key_item_id=e.get("key_item_id"),
            )
            for e in raw_exits
        ]

    async def get_actor_snapshot(self, uuid: str) -> dict[str, Any]:
        doc = await self._projection.get(uuid)
        if doc is None:
            return {}
        attrs = doc.get("attrs", {})
        loc_uuid: str | None = doc.get("location_uuid")
        loc = await self._projection.get(loc_uuid) if loc_uuid else None
        loc_attrs = loc.get("attrs", {}) if loc else {}
        return {
            "uuid": uuid,
            "name": doc.get("name", ""),
            "location": loc_uuid,
            "location_name": loc.get("name", "") if loc else "",
            "health": attrs.get("hp"),
            "max_health": attrs.get("max_hp"),
            "level": attrs.get("level"),
            "xp": attrs.get("xp"),
            "inventory": attrs.get("inventory", []),
            "equipped": attrs.get("equipped", {}),
            "exits": loc_attrs.get("exits", []),
            "is_dead": doc.get("is_dead", False),
        }

    async def room_manifest(self, location_uuid: str) -> RoomManifest:
        loc = await self._projection.get(location_uuid)
        if loc is None:
            return RoomManifest(
                location_id=location_uuid,
                name="",
                description="",
            )
        attrs = loc.get("attrs", {})
        raw_exits: list[dict[str, Any]] = attrs.get("exits", [])
        exits = [
            ExitRecord(
                direction=e["direction"],
                target_id=e["target_uuid"],
                locked=e.get("locked", False),
                key_item_id=e.get("key_item_id"),
            )
            for e in raw_exits
        ]
        npcs = await self._projection.entities_at_location(location_uuid)
        items = await self._projection.items_at_location(location_uuid)
        return RoomManifest(
            location_id=location_uuid,
            name=loc.get("name", ""),
            description=attrs.get("description", ""),
            exits=exits,
            npcs=[copy.deepcopy(d) for d in npcs],
            items=[copy.deepcopy(d) for d in items],
            room_map=attrs.get("room_map", {}),
        )

    # ------------------------------------------------------------------
    # Writes — compute delta, apply to projection, fire chain mirror
    # ------------------------------------------------------------------

    async def set_attr(self, uuid: str, field: str, value: Any) -> EntityDoc:
        """Set a scalar field on an entity doc.  Returns post-write deepcopy."""
        doc = await self._projection.get(uuid)
        if doc is None:
            raise KeyError(f"set_attr: entity {uuid!r} not found")

        if field == "is_dead":
            before = doc.get("is_dead")
            delta: dict[str, Any] = {
                "op": "set_top",
                "target_uuid": uuid,
                "field": field,
                "before": before,
                "after": value,
            }
            await self._apply_delta(self._projection, delta)
        else:
            before = doc.get("attrs", {}).get(field)
            delta = {
                "op": "set_attr",
                "target_uuid": uuid,
                "field": field,
                "before": before,
                "after": value,
            }
            await self._apply_delta(self._projection, delta)

        await self._append_tx(uuid, [delta])

        # NOTE: ChainMirror firing is NOT done here.
        # The EffectExecutor's Phase 3 is the single chain authority (chain_kill /
        # chain_transfer primitives in the effect_template).  InMemoryStateRepository
        # also never fires chain — the executor always does.  Firing chain here would
        # double-notarize ownership and break parity with InMemory.

        result = await self._projection.get(uuid)
        return copy.deepcopy(result)  # type: ignore[return-value]

    async def move_entity(self, uuid: str, to_location_uuid: str) -> EntityDoc:
        """Relocate an entity; maintain location/item_ids denorm."""
        doc = await self._projection.get(uuid)
        if doc is None:
            raise KeyError(f"move_entity: entity {uuid!r} not found")

        from_uuid: str | None = doc.get("location_uuid")

        delta: dict[str, Any] = {
            "op": "move",
            "target_uuid": uuid,
            "from_uuid": from_uuid,
            "to_uuid": to_location_uuid,
        }
        await self._apply_delta(self._projection, delta)
        await self._append_tx(uuid, [delta])

        result = await self._projection.get(uuid)
        return copy.deepcopy(result)  # type: ignore[return-value]

    async def transfer_item(
        self,
        item_uuid: str,
        from_uuid: str | None,
        to_uuid: str | None,
        to_location_uuid: str | None = None,
    ) -> ItemDoc:
        """Move an item between holder/floor."""
        item_doc = await self._projection.get(item_uuid)
        if item_doc is None:
            raise KeyError(f"transfer_item: item {item_uuid!r} not found")

        delta: dict[str, Any] = {
            "op": "transfer",
            "item_uuid": item_uuid,
            "from_uuid": from_uuid,
            "to_uuid": to_uuid,
            "to_location_uuid": to_location_uuid,
        }
        await self._apply_delta(self._projection, delta)
        await self._append_tx(item_uuid, [delta])

        # NOTE: ChainMirror firing is NOT done here.
        # The EffectExecutor's Phase 3 (chain_transfer primitive) is the single
        # chain authority.  InMemoryStateRepository also never fires chain.
        # Firing here would double-notarize ownership and break parity with InMemory.

        result = await self._projection.get(item_uuid)
        return copy.deepcopy(result)  # type: ignore[return-value]

    async def link(self, from_uuid: str, to_uuid: str, rel: str) -> None:
        """Append to attrs['links'][rel]; KeyError if from_uuid missing."""
        doc = await self._projection.get(from_uuid)
        if doc is None:
            raise KeyError(f"link: entity {from_uuid!r} not found")

        delta: dict[str, Any] = {
            "op": "link",
            "from_uuid": from_uuid,
            "to_uuid": to_uuid,
            "rel": rel,
        }
        await self._apply_delta(self._projection, delta)
        await self._append_tx(from_uuid, [delta])

    async def unlink(self, from_uuid: str, to_uuid: str, rel: str) -> None:
        """Remove to_uuid from attrs['links'][rel]; silent no-op if missing."""
        doc = await self._projection.get(from_uuid)
        if doc is None:
            return  # silent no-op (matches InMemory: returns without KeyError)

        delta: dict[str, Any] = {
            "op": "unlink",
            "from_uuid": from_uuid,
            "to_uuid": to_uuid,
            "rel": rel,
        }
        await self._apply_delta(self._projection, delta)
        await self._append_tx(from_uuid, [delta])

    async def materialize(self, doc: EntityDoc | ItemDoc, *, is_item: bool) -> str:
        """Persist a newly-promoted latent fact; returns doc['uuid']."""
        # Two independent deepcopies: one for the projection, one for the delta.
        proj_copy = copy.deepcopy(dict(doc))
        delta_copy = copy.deepcopy(dict(doc))
        delta: dict[str, Any] = {"op": "create", "doc": delta_copy}

        existing = await self._projection.get(doc["uuid"])
        if existing is not None:
            await self._projection.update(proj_copy)  # type: ignore[arg-type]
        else:
            await self._projection.create(proj_copy)  # type: ignore[arg-type]

        await self._append_tx(doc["uuid"], [delta])
        return doc["uuid"]

    async def ensure_indexes(self) -> None:
        """No-op — indexes are a Mongo concern."""
        pass

    # ------------------------------------------------------------------
    # rebuild_projection
    # ------------------------------------------------------------------

    async def rebuild_projection(self, actor_id: str) -> KgProjectionFake:
        """Replay the ENTIRE TxLog into a fresh KgProjectionFake and return it.

        Replays all entries in append order regardless of actor_id, then returns
        the fresh projection.  This is true event-sourcing: cross-entity writes
        (e.g. item transfers logged under item_uuid, not player_uuid) are included.

        The ``actor_id`` parameter is retained for API compatibility and is used
        only as the docstring label — the returned projection contains the full
        reconstructed world state, which the caller can then inspect for any uuid.
        """
        fresh: KgProjectionFake = KgProjectionFake()
        entries = self._tx_log.all()
        for entry in entries:
            for delta in entry.deltas:
                await self._apply_delta(fresh, delta)
        return fresh
