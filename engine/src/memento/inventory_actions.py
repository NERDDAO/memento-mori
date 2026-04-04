"""Deterministic inventory action handlers.

Each action validates, writes to chain first (capturing timestamp),
then updates KG edges with temporal fields. No LLM round-trips.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from memento.bonfires_client import get_client
from memento.inventory_manifest import (
    get_inventory_manifest,
    EQUIPMENT_SLOTS,
    DEFAULT_CAPACITY,
)
from memento.log import get_logger
from memento.tools import chain as _chain

logger = get_logger(__name__)


class InventoryError(Exception):
    """Raised when an inventory action fails validation."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_item_from_manifest(manifest: dict, item_id: str) -> dict | None:
    """Find an item in a manifest by ID (checks equipped + backpack)."""
    for slot_item in manifest["equipped"].values():
        if slot_item and slot_item["id"] == item_id:
            return slot_item
    for item in manifest["backpack"]:
        if item["id"] == item_id:
            return item
    return None


def _parse_entity_meta(entity: dict) -> dict[str, Any]:
    """Extract metadata from a KG entity."""
    summary = entity.get("summary", "")
    if isinstance(summary, str) and summary.startswith("{"):
        try:
            return json.loads(summary)
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def _update_entity_summary(client, entity_id: str, meta: dict) -> None:
    """Update an entity's summary JSON, preserving name and labels.

    The SDK's update_entity requires (uuid, name, labels, summary).
    We fetch the current entity to get name/labels, then update summary.
    """
    try:
        entity = client.kg.get_entity(entity_id)
        name = entity.get("name", "Unknown")
        labels = entity.get("labels", ["Item"])
        client.kg.update_entity(entity_id, name, labels, json.dumps(meta))
    except Exception:
        logger.warning("Failed to update entity %s", entity_id)


# ── Public Actions ──


def equip(player_uuid: str, item_id: str, slot: str) -> dict:
    """Equip an item to a slot. KG-only (no chain change for equip state).

    Returns updated manifest dict.
    """
    if slot not in EQUIPMENT_SLOTS:
        raise InventoryError(f"Invalid slot: {slot}. Must be one of {EQUIPMENT_SLOTS}")

    manifest = get_inventory_manifest(player_uuid)
    item = _get_item_from_manifest(manifest, item_id)
    if not item:
        raise InventoryError(f"Item {item_id} not in inventory")

    if item["equipped"]:
        raise InventoryError(f"Item {item['name']} is already equipped")

    item_slot = item.get("slot_type", "")
    if item_slot and item_slot != slot:
        raise InventoryError(
            f"Cannot equip {item['name']} (slot_type={item_slot}) to {slot}"
        )

    client = get_client()

    # If slot is occupied, unequip current item first
    current = manifest["equipped"].get(slot)
    if current:
        try:
            entity = client.kg.get_entity(current["id"])
            meta = _parse_entity_meta(entity)
            meta["equipped"] = False
            _update_entity_summary(client, current["id"], meta)
        except Exception:
            logger.warning("Failed to unequip current item in slot %s", slot)

    # Equip the new item
    try:
        entity = client.kg.get_entity(item_id)
        meta = _parse_entity_meta(entity)
        meta["equipped"] = True
        meta["slot_type"] = slot
        _update_entity_summary(client, item_id, meta)
    except Exception as e:
        raise InventoryError(f"Failed to equip item: {e}") from e

    return get_inventory_manifest(player_uuid)


def unequip(player_uuid: str, slot: str) -> dict:
    """Unequip an item from a slot. KG-only.

    Returns updated manifest dict.
    """
    if slot not in EQUIPMENT_SLOTS:
        raise InventoryError(f"Invalid slot: {slot}")

    manifest = get_inventory_manifest(player_uuid)
    current = manifest["equipped"].get(slot)
    if not current:
        raise InventoryError(f"No item equipped in {slot}")

    client = get_client()
    try:
        entity = client.kg.get_entity(current["id"])
        meta = _parse_entity_meta(entity)
        meta["equipped"] = False
        _update_entity_summary(client, current["id"], meta)
    except Exception as e:
        raise InventoryError(f"Failed to unequip: {e}") from e

    return get_inventory_manifest(player_uuid)


def drop(
    player_uuid: str,
    item_id: str,
    location_uuid: str,
    quantity: int | None = None,
) -> dict:
    """Drop an item into the current room.

    Chain tx first → capture timestamp → expire CARRIES → create LOCATED_IN.
    Handles stack splitting for partial drops.

    Returns updated manifest dict.
    """
    manifest = get_inventory_manifest(player_uuid)
    item = _get_item_from_manifest(manifest, item_id)
    if not item:
        raise InventoryError(f"Item {item_id} not in inventory")

    if item.get("is_quest_item"):
        raise InventoryError(f"Cannot drop quest item: {item['name']}")

    client = get_client()
    now = _now_iso()

    # Handle stack splitting
    if quantity and item.get("stackable") and item.get("quantity", 1) > 1:
        current_qty = item["quantity"]
        if quantity >= current_qty:
            quantity = None  # Drop entire stack
        else:
            # Partial drop: decrement original, create new ground entity
            new_qty = current_qty - quantity
            # Update original stack quantity in KG
            entity = client.kg.get_entity(item_id)
            meta = _parse_entity_meta(entity)
            meta["quantity"] = new_qty
            _update_entity_summary(client, item_id, meta)

            # Create new entity for the dropped portion
            split_uuid = client.kg.create_entity(
                name=item["name"],
                entity_type="Item",
                summary=json.dumps({
                    "rarity": item["rarity"],
                    "slot_type": item.get("slot_type", ""),
                    "is_consumable": item.get("is_consumable", False),
                    "stackable": True,
                    "quantity": quantity,
                }),
            )
            # Place on ground
            client.kg.create_edge(
                split_uuid, location_uuid, "LOCATED_IN",
                f"Dropped {quantity}x {item['name']}",
            )
            # Chain: register the split item on ground
            _chain.register_item(
                split_uuid, item["name"], item["rarity"],
                "", location_uuid,
                slot_type=item.get("slot_type", ""),
                quantity=quantity,
            )
            return get_inventory_manifest(player_uuid)

    # Full drop (entire stack or single item)
    # 1. Chain tx: set ownerId=0, locationId=room
    _chain.drop_item(item_id, location_uuid)

    # 2. Expire CARRIES edge
    _expire_carries_edge(client, player_uuid, item_id, now)

    # 3. Create LOCATED_IN edge to room
    client.kg.create_edge(
        item_id, location_uuid, "LOCATED_IN",
        f"Dropped: {item['name']}",
    )

    # 4. If equipped, clear equipped state
    if item.get("equipped"):
        try:
            entity = client.kg.get_entity(item_id)
            meta = _parse_entity_meta(entity)
            meta["equipped"] = False
            _update_entity_summary(client, item_id, meta)
        except Exception:
            pass

    return get_inventory_manifest(player_uuid)


def use(player_uuid: str, item_id: str) -> dict:
    """Use a consumable item. Applies effects, decrements quantity.

    Chain tx → expire CARRIES edge when quantity hits 0.

    Returns updated manifest dict.
    """
    manifest = get_inventory_manifest(player_uuid)
    item = _get_item_from_manifest(manifest, item_id)
    if not item:
        raise InventoryError(f"Item {item_id} not in inventory")

    if not item.get("is_consumable"):
        raise InventoryError(f"{item['name']} is not consumable")

    client = get_client()
    now = _now_iso()

    # Apply effects (e.g., heal)
    _apply_item_effects(client, player_uuid, item)

    # Handle quantity
    current_qty = item.get("quantity", 1)
    if current_qty > 1:
        # Decrement stack
        entity = client.kg.get_entity(item_id)
        meta = _parse_entity_meta(entity)
        meta["quantity"] = current_qty - 1
        _update_entity_summary(client, item_id, meta)
    else:
        # Last one — delete from chain + expire KG edge
        _chain.drop_item(item_id, "")  # ownerId=0 signals deletion
        _expire_carries_edge(client, player_uuid, item_id, now)

    return get_inventory_manifest(player_uuid)


def pickup(
    player_uuid: str,
    item_id: str,
    location_uuid: str,
) -> dict:
    """Pick up an item from the current room.

    Chain tx → expire LOCATED_IN → create CARRIES.
    Merges into existing stack if stackable match found.

    Returns updated manifest dict.
    """
    client = get_client()

    # Check capacity
    manifest = get_inventory_manifest(player_uuid)
    if manifest["count"] >= DEFAULT_CAPACITY:
        raise InventoryError("Inventory full — cannot carry more items")

    # Get item metadata — item may be a full KG entity or just in the room_map JSON
    entity = None
    try:
        entity = client.kg.get_entity(item_id)
    except Exception:
        pass  # Item may only exist in room_map, not as standalone KG entity

    if entity:
        meta = _parse_entity_meta(entity)
        item_name = entity.get("name", "Unknown")
    else:
        # Item exists only in room_map — look it up from room manifest
        from memento.room_manifest import get_room_manifest
        room = get_room_manifest(location_uuid)
        room_item = next(
            (i for i in room.get("items", []) if i.get("id") == item_id),
            None,
        )
        if not room_item:
            raise InventoryError(f"Item {item_id} is not in this room")
        item_name = room_item.get("name", "Unknown")
        meta = {}

    item_rarity = meta.get("rarity", "common")
    is_stackable = bool(meta.get("stackable", False))

    now = _now_iso()

    # Check for stack merge
    if is_stackable:
        for bp_item in manifest["backpack"]:
            if (bp_item["name"] == item_name
                    and bp_item["rarity"] == item_rarity
                    and bp_item.get("stackable")):
                # Merge: increment existing stack, delete ground entity
                existing_entity = client.kg.get_entity(bp_item["id"])
                existing_meta = _parse_entity_meta(existing_entity)
                ground_qty = meta.get("quantity", 1)
                existing_meta["quantity"] = existing_meta.get("quantity", 1) + ground_qty
                _update_entity_summary(client, bp_item["id"], existing_meta)
                # Expire the ground entity's LOCATED_IN edge
                _expire_located_in_edge(client, item_id, location_uuid, now)
                # Chain: transfer to player (merge)
                _chain.transfer_item(item_id, player_uuid)
                return get_inventory_manifest(player_uuid)

    # No merge — standard pickup
    # 1. If item doesn't exist as KG entity yet (room_map-only), create it
    if not entity:
        try:
            item_id = client.kg.create_entity(
                name=item_name,
                entity_type="Item",
                summary=json.dumps(meta) if meta else "",
            )
        except Exception:
            pass  # Non-fatal — edge creation may still work with the ID

    # 2. Chain tx: set ownerId=player
    _chain.transfer_item(item_id, player_uuid)

    # 3. Expire LOCATED_IN edge (if it exists)
    _expire_located_in_edge(client, item_id, location_uuid, now)

    # 4. Create CARRIES edge
    client.kg.create_edge(
        player_uuid, item_id, "CARRIES",
        f"Picked up: {item_name}",
    )

    return get_inventory_manifest(player_uuid)


# ── Internal Helpers ──


def _expire_carries_edge(client, player_uuid: str, item_id: str, timestamp: str) -> None:
    """Find and expire ALL active CARRIES edges from player to item."""
    try:
        edges = client.kg.get_edges(
            player_uuid, direction="outgoing", edge_type="CARRIES",
        )
        for edge in edges:
            target = edge.get("target", {})
            tid = target.get("uuid", target.get("id", ""))
            if tid == item_id and not (edge.get("expired_at") or edge.get("invalid_at")):
                edge_uuid = edge.get("uuid", edge.get("id", ""))
                if edge_uuid:
                    client.kg.update_edge(edge_uuid, expired_at=timestamp)
    except Exception:
        logger.warning("Failed to expire CARRIES edge: %s -> %s", player_uuid, item_id)


def _expire_located_in_edge(
    client, item_id: str, location_uuid: str, timestamp: str,
) -> None:
    """Find and expire ALL active LOCATED_IN edges from item to location."""
    try:
        edges = client.kg.get_edges(
            item_id, direction="outgoing", edge_type="LOCATED_IN",
        )
        for edge in edges:
            target = edge.get("target", {})
            tid = target.get("uuid", target.get("id", ""))
            if tid == location_uuid and not (edge.get("expired_at") or edge.get("invalid_at")):
                edge_uuid = edge.get("uuid", edge.get("id", ""))
                if edge_uuid:
                    client.kg.update_edge(edge_uuid, expired_at=timestamp)
    except Exception:
        logger.warning("Failed to expire LOCATED_IN edge: %s -> %s", item_id, location_uuid)


def _apply_item_effects(client, player_uuid: str, item: dict) -> None:
    """Apply item effects to the player. Currently supports heal effects."""
    effects = item.get("effects", [])
    if not effects:
        return

    try:
        player_entity = client.kg.get_entity(player_uuid)
        player_meta = _parse_entity_meta(player_entity)
    except Exception:
        return

    for effect in effects:
        effect_str = str(effect).lower()
        # Parse heal effects: "Restores 20 HP", "+20 health", "heal 20"
        import re
        heal_match = re.search(r'(?:restores?|heals?|\+)\s*(\d+)\s*(?:hp|health)?', effect_str)
        if heal_match:
            amount = int(heal_match.group(1))
            current_hp = player_meta.get("health", 100)
            max_hp = player_meta.get("max_health", 100)
            new_hp = min(current_hp + amount, max_hp)
            player_meta["health"] = new_hp
            logger.info("Healed %s for %d HP (%d → %d)", player_uuid, amount, current_hp, new_hp)

    try:
        _update_entity_summary(client, player_uuid, player_meta)
    except Exception:
        logger.warning("Failed to apply effects for %s", player_uuid)
