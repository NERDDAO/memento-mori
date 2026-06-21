"""StateRepository port — authoritative transactional store for mutable game state.

This module defines:
- EntityDoc / ItemDoc  — the canonical document shapes (§6.1)
- ExitRecord / RoomManifest — companion read-side types (§6.3)
- StateRepository — the Protocol every concrete implementation must satisfy (§6.2)

Implementations
---------------
InMemoryStateRepository  (this package, in_memory.py)  — dict-backed, Day-1 default
MongoStateRepository     (engine/src/memento/state/mongo_repository.py, FUTURE)
    Motor-backed against MongoDB replica set.  Not part of the Day-1 walking skeleton.
    Will require a running replica for multi-document transaction support (§3.3).

No component outside engine/src/memento/state/ imports concrete classes by name.
All callers depend only on StateRepository (the Protocol) and the TypedDicts here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# §6.1  Document shapes
# ---------------------------------------------------------------------------


class EntityDoc(TypedDict):
    """Character / NPC / Location document stored in mm_entities."""

    uuid: str  # == Mongo _id; canonical identifier; never changes
    name: str  # display-only; never used for lookups
    kind: str  # "character" | "location" | "item" | "region" | "faction" | "quest"
    labels: list[str]  # e.g. ["Character", "NPC"], ["Location"], ["Item", "Weapon"]
    location_uuid: str | None  # MUTABLE — which Location this entity is in
    attrs: dict[
        str, Any
    ]  # MUTABLE — hp, max_hp, strength, armor, exits[], item_ids[], …
    is_dead: bool  # MUTABLE — permadeath flag


class ItemDoc(TypedDict):
    """Item document stored in mm_entities (kind=="item")."""

    uuid: str
    name: str
    kind: str  # "item"
    labels: list[str]
    owner_uuid: str | None  # MUTABLE — holder entity UUID; None = on the floor
    location_uuid: str | None  # MUTABLE — room UUID when on the floor
    attrs: dict[
        str, Any
    ]  # slot_type, damage, defense, weight, quantity, carryable, onchain, …


# ---------------------------------------------------------------------------
# §6.3  Companion read-side types
# ---------------------------------------------------------------------------


@dataclass
class ExitRecord:
    """A single navigable exit from a location."""

    direction: str
    target_id: str
    locked: bool = False
    key_item_id: str | None = None


@dataclass
class RoomManifest:
    """Snapshot of a location's occupants and exits — single-document read."""

    location_id: str
    name: str
    description: str
    exits: list[ExitRecord] = field(default_factory=list)
    npcs: list[dict[str, Any]] = field(
        default_factory=list
    )  # characters at this location
    items: list[dict[str, Any]] = field(
        default_factory=list
    )  # floor items (owner_uuid None)
    room_map: dict[str, Any] = field(default_factory=dict)  # display hint only


# ---------------------------------------------------------------------------
# §6.2  StateRepository Protocol
# ---------------------------------------------------------------------------


class StateRepository(Protocol):
    """Port for the authoritative transactional entity store.

    All identifiers are UUID strings.  Names are never used for lookups.

    Write methods return the post-write document so callers can build
    StateDelta TypedDicts (op/target_uuid/field/before/after) without a
    second read.  The EffectExecutor (C4) is responsible for capturing the
    before-snapshot and constructing StateDelta — the repository never returns
    a StateDelta directly.

    No record_death on this port (§6.2 note) — death is expressed by the
    construction template as set_attr(patient, "is_dead", True) +
    link(patient, location, "DIED_IN").  The chain write goes through
    ChainMirror.on_character_death, which wraps chain.py's own record_death.
    """

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_entity(self, uuid: str) -> EntityDoc | None:
        """Return the full entity doc, or None if not found.

        Used for executor existence checks only.  The executor converts None
        to ConstructionError rather than letting it propagate.
        """
        ...

    async def get_labels(self, uuid: str) -> list[str]:
        """Return the entity's label list, or [] if not found.

        Used by Phase 1 selection-restriction validation.
        """
        ...

    async def get_entities_at_location(self, location_uuid: str) -> list[EntityDoc]:
        """Return all non-item entities whose location_uuid matches."""
        ...

    async def get_items_at_location(self, location_uuid: str) -> list[ItemDoc]:
        """Return floor items (owner_uuid is None) at a location."""
        ...

    async def get_exits(self, location_uuid: str) -> list[ExitRecord]:
        """Return the exits list for a location (from attrs["exits"])."""
        ...

    async def get_actor_snapshot(self, uuid: str) -> dict[str, Any]:
        """Return a health/location/inventory/exits summary for the executor's StateUpdate."""
        ...

    async def room_manifest(self, location_uuid: str) -> RoomManifest:
        """Return a full RoomManifest for a location (single-document read)."""
        ...

    # ------------------------------------------------------------------
    # Transactional writes — return post-write snapshot
    # ------------------------------------------------------------------

    async def set_attr(self, uuid: str, field: str, value: Any) -> EntityDoc:
        """Set a scalar field on an entity doc.  Returns the updated EntityDoc.

        Works for both EntityDoc and ItemDoc (both share attrs-level mutation).
        """
        ...

    async def move_entity(self, uuid: str, to_location_uuid: str) -> EntityDoc:
        """Relocate an entity.

        Maintains location/contents denormalization:
        - Sets entity.location_uuid = to_location_uuid
        - Removes entity.uuid from old location's attrs["item_ids"] (if present)
        - Appends entity.uuid to new location's attrs["item_ids"]

        Returns the updated EntityDoc.
        """
        ...

    async def transfer_item(
        self,
        item_uuid: str,
        from_uuid: str | None,
        to_uuid: str | None,
        to_location_uuid: str | None = None,
    ) -> ItemDoc:
        """Move an item between holder/floor.

        One signature everywhere (§6.2):
        - Pickup:              transfer_item(item, from_uuid=location, to_uuid=agent)
        - Compensating restore: transfer_item(item, from_uuid=agent,  to_uuid=None, to_location_uuid=original)

        Maintains:
        - item.owner_uuid / item.location_uuid
        - from entity's inventory list (attrs["inventory"]) or location's attrs["item_ids"]
        - to entity's inventory list or location's attrs["item_ids"]

        Returns the updated ItemDoc.
        """
        ...

    async def link(self, from_uuid: str, to_uuid: str, rel: str) -> None:
        """Append a relation/status-effect edge.

        Stored as attrs["links"][rel] = list of target UUIDs (appended).
        Example: link(patient, location, "DIED_IN").
        """
        ...

    async def unlink(self, from_uuid: str, to_uuid: str, rel: str) -> None:
        """Inverse of link — remove to_uuid from attrs["links"][rel] if present."""
        ...

    # ------------------------------------------------------------------
    # Lifecycle / utility
    # ------------------------------------------------------------------

    async def materialize(self, doc: EntityDoc | ItemDoc, *, is_item: bool) -> str:
        """Persist a newly-promoted latent fact and return its UUID.

        Callers (EntityResolver.promote-on-miss) pass:
          is_item=True  → the doc is an ItemDoc (kind=="item"); stored so that
                          it is resolvable as a patient AND takeable.
          is_item=False → the doc is an EntityDoc (NPC/character/etc.).

        The UUID in doc["uuid"] is the canonical identifier; it is returned
        so the caller can register it with the SceneDirector.
        """
        ...

    async def ensure_indexes(self) -> None:
        """Idempotent index creation.  Called once at startup.

        Compound indexes (§6.1):
        - kind
        - (kind, location_uuid)
        - (kind, owner_uuid)
        - (is_dead, kind)

        No (kind, assignee_id) index on Day 1 — no document carries assignee_id yet.
        """
        ...
