"""InMemoryStateRepository — dict-backed implementation of the StateRepository Protocol.

This is the Day-1 default store.  It is the only store dependency of
construction unit tests (no Mongo, no web3, no network required).

MongoStateRepository (future, engine/src/memento/state/mongo_repository.py)
is the production motor-backed implementation; it is out of Day-1 scope.

Implementation notes
--------------------
- All entity docs are stored as plain dicts keyed by UUID string.
- Items are stored in the same _entities dict (kind=="item") plus a
  _items dict for quick ItemDoc lookup without re-casting.
- Denormalizations maintained on every write:
    entity.location_uuid ↔ location.attrs["item_ids"]  (for non-item entities: move_entity)
    item.owner_uuid / item.location_uuid ↔ owner.attrs["inventory"] / location.attrs["item_ids"]
- link/unlink maintain entity.attrs["links"][rel] = list[str]
- No transactions needed (no rollback primitives) — the EffectExecutor handles
  compensation via reverse-order inverse ops over the in-memory dicts (§3.3).
- ensure_indexes() is a no-op (indexes are a Mongo concern).
"""

from __future__ import annotations

import copy
from typing import Any

from memento.state.repository import EntityDoc, ExitRecord, ItemDoc, RoomManifest


class InMemoryStateRepository:
    """Fully dict-backed StateRepository for tests and local development.

    Seed with seed_entities / seed_items before calling executor methods.
    All methods are async to match the Protocol signature; they do not block.
    """

    def __init__(self) -> None:
        # UUID -> dict (EntityDoc or ItemDoc shape)
        self._entities: dict[str, dict[str, Any]] = {}
        self._items: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Seeding helpers (not part of the Protocol)
    # ------------------------------------------------------------------

    def seed_entity(self, doc: EntityDoc) -> None:
        """Insert or replace an entity doc."""
        self._entities[doc["uuid"]] = copy.deepcopy(dict(doc))

    def seed_item(self, doc: ItemDoc) -> None:
        """Insert or replace an item doc (also stored in _items for fast lookup)."""
        d = copy.deepcopy(dict(doc))
        self._items[doc["uuid"]] = d
        self._entities[doc["uuid"]] = d

    def _get_raw(self, uuid: str) -> dict[str, Any] | None:
        return self._entities.get(uuid)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_entity(self, uuid: str) -> EntityDoc | None:
        raw = self._entities.get(uuid)
        if raw is None:
            return None
        return copy.deepcopy(raw)  # type: ignore[return-value]

    async def get_labels(self, uuid: str) -> list[str]:
        raw = self._entities.get(uuid)
        if raw is None:
            return []
        return list(raw.get("labels", []))

    async def get_entities_at_location(self, location_uuid: str) -> list[EntityDoc]:
        return [
            copy.deepcopy(e)  # type: ignore[misc]
            for e in self._entities.values()
            if e.get("location_uuid") == location_uuid and e.get("kind") != "item"
        ]

    async def get_items_at_location(self, location_uuid: str) -> list[ItemDoc]:
        return [
            copy.deepcopy(i)  # type: ignore[misc]
            for i in self._items.values()
            if i.get("location_uuid") == location_uuid and i.get("owner_uuid") is None
        ]

    async def get_exits(self, location_uuid: str) -> list[ExitRecord]:
        loc = self._entities.get(location_uuid)
        if loc is None:
            return []
        raw_exits: list[dict[str, Any]] = loc.get("attrs", {}).get("exits", [])
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
        raw = self._entities.get(uuid)
        if raw is None:
            return {}
        attrs = raw.get("attrs", {})
        loc_uuid = raw.get("location_uuid")
        loc = self._entities.get(loc_uuid) if loc_uuid else None
        loc_attrs = loc.get("attrs", {}) if loc else {}
        return {
            "uuid": uuid,
            "name": raw.get("name", ""),
            "location": loc_uuid,
            "location_name": loc.get("name", "") if loc else "",
            "health": attrs.get("hp"),
            "max_health": attrs.get("max_hp"),
            "level": attrs.get("level"),
            "xp": attrs.get("xp"),
            "inventory": attrs.get("inventory", []),
            "equipped": attrs.get("equipped", {}),
            "exits": loc_attrs.get("exits", []),
            "is_dead": raw.get("is_dead", False),
        }

    async def room_manifest(self, location_uuid: str) -> RoomManifest:
        loc = self._entities.get(location_uuid)
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
        npcs: list[dict[str, Any]] = [
            copy.deepcopy(e)
            for e in self._entities.values()
            if e.get("location_uuid") == location_uuid and e.get("kind") != "item"
        ]
        items: list[dict[str, Any]] = [
            copy.deepcopy(i)
            for i in self._items.values()
            if i.get("location_uuid") == location_uuid and i.get("owner_uuid") is None
        ]
        return RoomManifest(
            location_id=location_uuid,
            name=loc.get("name", ""),
            description=loc.get("attrs", {}).get("description", ""),
            exits=exits,
            npcs=npcs,
            items=items,
            room_map=attrs.get("room_map", {}),
        )

    # ------------------------------------------------------------------
    # Transactional writes
    # ------------------------------------------------------------------

    async def set_attr(self, uuid: str, field: str, value: Any) -> EntityDoc:
        """Set a scalar field on attrs (or a top-level field) and return updated doc."""
        raw = self._entities.get(uuid)
        if raw is None:
            raise KeyError(f"set_attr: entity {uuid!r} not found")
        # Support both attrs-level and top-level field writes.
        # Spec says field names used are: "hp", "is_dead" (top-level on EntityDoc).
        # "is_dead" is a top-level EntityDoc field; attrs fields are everything else.
        if field == "is_dead":
            raw[field] = value
        else:
            attrs = raw.setdefault("attrs", {})
            attrs[field] = value
        return copy.deepcopy(raw)  # type: ignore[return-value]

    async def move_entity(self, uuid: str, to_location_uuid: str) -> EntityDoc:
        """Relocate a character/NPC; maintain location denormalization."""
        raw = self._entities.get(uuid)
        if raw is None:
            raise KeyError(f"move_entity: entity {uuid!r} not found")

        old_loc_uuid: str | None = raw.get("location_uuid")

        # Remove from old location's item_ids / occupant list
        if old_loc_uuid and old_loc_uuid != to_location_uuid:
            old_loc = self._entities.get(old_loc_uuid)
            if old_loc is not None:
                old_attrs = old_loc.setdefault("attrs", {})
                old_ids: list[str] = old_attrs.get("item_ids", [])
                if uuid in old_ids:
                    old_ids.remove(uuid)
                old_attrs["item_ids"] = old_ids

        # Add to new location's item_ids
        new_loc = self._entities.get(to_location_uuid)
        if new_loc is not None:
            new_attrs = new_loc.setdefault("attrs", {})
            new_ids: list[str] = new_attrs.get("item_ids", [])
            if uuid not in new_ids:
                new_ids.append(uuid)
            new_attrs["item_ids"] = new_ids

        raw["location_uuid"] = to_location_uuid
        return copy.deepcopy(raw)  # type: ignore[return-value]

    async def transfer_item(
        self,
        item_uuid: str,
        from_uuid: str | None,
        to_uuid: str | None,
        to_location_uuid: str | None = None,
    ) -> ItemDoc:
        """Move an item between holder/floor.

        One signature everywhere (§6.2):
          Pickup:   transfer_item(item, from_uuid=location_uuid, to_uuid=agent_uuid)
          Restore:  transfer_item(item, from_uuid=agent_uuid, to_uuid=None, to_location_uuid=location_uuid)

        Maintains:
        - item.owner_uuid / item.location_uuid
        - from entity's attrs["inventory"] or attrs["item_ids"] (if location)
        - to entity's attrs["inventory"] or attrs["item_ids"] (if location)
        """
        item_raw = self._items.get(item_uuid)
        if item_raw is None:
            raise KeyError(f"transfer_item: item {item_uuid!r} not found")

        # --- Remove from source ---
        if from_uuid is not None:
            from_entity = self._entities.get(from_uuid)
            if from_entity is not None:
                from_attrs = from_entity.setdefault("attrs", {})
                # Could be a location (item_ids) or a character (inventory)
                if from_entity.get("kind") == "location":
                    ids: list[str] = from_attrs.get("item_ids", [])
                    if item_uuid in ids:
                        ids.remove(item_uuid)
                    from_attrs["item_ids"] = ids
                else:
                    inv: list[str] = from_attrs.get("inventory", [])
                    if item_uuid in inv:
                        inv.remove(item_uuid)
                    from_attrs["inventory"] = inv

        # --- Add to destination ---
        if to_uuid is not None:
            to_entity = self._entities.get(to_uuid)
            if to_entity is not None:
                to_attrs = to_entity.setdefault("attrs", {})
                if to_entity.get("kind") == "location":
                    ids = to_attrs.get("item_ids", [])
                    if item_uuid not in ids:
                        ids.append(item_uuid)
                    to_attrs["item_ids"] = ids
                else:
                    inv = to_attrs.get("inventory", [])
                    if item_uuid not in inv:
                        inv.append(item_uuid)
                    to_attrs["inventory"] = inv
            item_raw["owner_uuid"] = to_uuid
            item_raw["location_uuid"] = None
        else:
            # Dropping to floor at to_location_uuid
            item_raw["owner_uuid"] = None
            item_raw["location_uuid"] = to_location_uuid
            if to_location_uuid is not None:
                floor_loc = self._entities.get(to_location_uuid)
                if floor_loc is not None:
                    floor_attrs = floor_loc.setdefault("attrs", {})
                    floor_ids: list[str] = floor_attrs.get("item_ids", [])
                    if item_uuid not in floor_ids:
                        floor_ids.append(item_uuid)
                    floor_attrs["item_ids"] = floor_ids

        return copy.deepcopy(item_raw)  # type: ignore[return-value]

    async def link(self, from_uuid: str, to_uuid: str, rel: str) -> None:
        """Append to attrs["links"][rel] list."""
        raw = self._entities.get(from_uuid)
        if raw is None:
            raise KeyError(f"link: entity {from_uuid!r} not found")
        attrs = raw.setdefault("attrs", {})
        links: dict[str, list[str]] = attrs.setdefault("links", {})
        targets: list[str] = links.setdefault(rel, [])
        if to_uuid not in targets:
            targets.append(to_uuid)

    async def unlink(self, from_uuid: str, to_uuid: str, rel: str) -> None:
        """Remove to_uuid from attrs["links"][rel]; no-op if not present."""
        raw = self._entities.get(from_uuid)
        if raw is None:
            return
        links: dict[str, list[str]] = raw.get("attrs", {}).get("links", {})
        targets: list[str] = links.get(rel, [])
        if to_uuid in targets:
            targets.remove(to_uuid)

    async def materialize(self, doc: EntityDoc | ItemDoc, *, is_item: bool) -> str:
        """Persist a newly-promoted latent fact and return its UUID.

        Delegates to the SYNC seed helpers (seed_item / seed_entity) so the
        resolver stays typed against the Protocol without introducing Any.
        """
        if is_item:
            self.seed_item(doc)  # type: ignore[arg-type]
        else:
            self.seed_entity(doc)  # type: ignore[arg-type]
        return doc["uuid"]

    async def ensure_indexes(self) -> None:
        """No-op for in-memory store; indexes are a Mongo concern."""
        pass
