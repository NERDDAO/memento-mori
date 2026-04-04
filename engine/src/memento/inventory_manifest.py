"""Inventory manifest — single source of truth for player inventory.

Assembles a complete view of a player's inventory from KG CARRIES edges,
enriched with entity metadata. Uses Graphiti's temporal fields (valid_at,
expired_at) to filter only current ownership. Chain is the canonical owner;
KG self-heals via lazy reconciliation on read.

Follows the same pattern as room_manifest.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from memento.bonfires_client import get_client
from memento.log import get_logger
from memento.room_manifest import ITEM_LABELS

logger = get_logger(__name__)

EQUIPMENT_SLOTS = ("weapon", "armor", "accessory", "ring")

# Default capacity: 10 items, 5 weight each, 50 total
DEFAULT_CAPACITY = 10
DEFAULT_WEIGHT_PER_ITEM = 5
DEFAULT_MAX_WEIGHT = 50


def _parse_entity_metadata(entity: dict) -> dict[str, Any]:
    """Extract item metadata from a KG entity's summary JSON or direct attrs."""
    meta: dict[str, Any] = {}
    summary = entity.get("summary", "")
    parsed = {}
    if isinstance(summary, str) and summary.startswith("{"):
        try:
            parsed = json.loads(summary)
        except (json.JSONDecodeError, TypeError):
            pass

    for key in ("description", "rarity", "slot_type", "effects",
                "is_consumable", "is_quest_item", "stackable", "equipped",
                "quantity"):
        val = entity.get(key) or parsed.get(key)
        if val is not None:
            meta[key] = val

    return meta


def _is_expired(edge: dict) -> bool:
    """Check if a KG edge has been expired (temporal invalidation)."""
    return bool(edge.get("expired_at") or edge.get("invalid_at"))


def get_inventory_manifest(player_uuid: str) -> dict[str, Any]:
    """Assemble a complete inventory manifest for a player from the KG.

    Queries outgoing CARRIES edges from the player entity, filters to
    only current (unexpired) edges, and enriches each item with KG metadata.

    Returns:
        {
            equipped: {weapon: item|None, armor: item|None, accessory: item|None, ring: item|None},
            backpack: [item, ...],
            capacity: int,
            count: int,
            weight: int,
            max_weight: int,
        }
    """
    client = get_client()

    equipped: dict[str, dict | None] = {slot: None for slot in EQUIPMENT_SLOTS}
    backpack: list[dict] = []

    try:
        edges = client.kg.get_edges(
            player_uuid, direction="outgoing", edge_type="CARRIES",
        )
    except Exception:
        logger.warning("Failed to query CARRIES edges for %s", player_uuid)
        return _empty_manifest()

    seen_item_ids: set[str] = set()
    for edge in edges:
        if _is_expired(edge):
            continue

        target = edge.get("target", {})
        item_uuid = target.get("uuid", target.get("id", ""))
        if not item_uuid or item_uuid in seen_item_ids:
            continue
        seen_item_ids.add(item_uuid)

        # Fetch full entity for metadata
        try:
            entity = client.kg.get_entity(item_uuid)
        except Exception:
            logger.debug("Failed to fetch item entity %s", item_uuid)
            entity = target

        labels = set(entity.get("labels", []))
        if not (labels & ITEM_LABELS):
            continue

        meta = _parse_entity_metadata(entity)
        item_name = entity.get("name", "Unknown")

        # Infer slot_type from KG labels if not in metadata
        slot_type = meta.get("slot_type", "")
        if not slot_type:
            if labels & {"Weapon"}:
                slot_type = "weapon"
            elif labels & {"Armor", "Shield"}:
                slot_type = "armor"
            elif labels & {"Scroll", "Amulet"}:
                slot_type = "accessory"
            elif labels & {"Ring"}:
                slot_type = "ring"

        # Infer consumable from labels
        is_consumable = bool(meta.get("is_consumable", False))
        if not is_consumable and labels & {"Consumable", "Potion"}:
            is_consumable = True

        item = {
            "id": item_uuid,
            "name": item_name,
            "rarity": meta.get("rarity", "common"),
            "slot_type": slot_type,
            "equipped": bool(meta.get("equipped", False)),
            "is_consumable": is_consumable,
            "is_quest_item": bool(meta.get("is_quest_item", False)),
            "effects": meta.get("effects", []),
            "stackable": bool(meta.get("stackable", False)),
            "quantity": int(meta.get("quantity", 1)),
        }

        # If effects is a string, parse it
        if isinstance(item["effects"], str):
            try:
                item["effects"] = json.loads(item["effects"])
            except (json.JSONDecodeError, TypeError):
                item["effects"] = [item["effects"]] if item["effects"] else []

        if item["equipped"] and item["slot_type"] in EQUIPMENT_SLOTS:
            equipped[item["slot_type"]] = item
        else:
            backpack.append(item)

    count = sum(1 for _ in backpack) + sum(1 for v in equipped.values() if v)
    weight = count * DEFAULT_WEIGHT_PER_ITEM

    return {
        "equipped": equipped,
        "backpack": backpack,
        "capacity": DEFAULT_CAPACITY,
        "count": count,
        "weight": weight,
        "max_weight": DEFAULT_MAX_WEIGHT,
    }


def get_inventory_as_state_update(player_uuid: str) -> list[dict]:
    """Convert inventory manifest to a list of InventoryItemUpdate dicts.

    Used by session create/join and state route to send inventory state
    to the client via WebSocket.
    """
    manifest = get_inventory_manifest(player_uuid)
    items = []

    for _, item in manifest["equipped"].items():
        if item:
            items.append({
                "id": item["id"],
                "name": item["name"],
                "rarity": item["rarity"],
                "slot_type": item["slot_type"],
                "equipped": True,
                "is_consumable": item["is_consumable"],
                "is_quest_item": item["is_quest_item"],
                "effects": item["effects"],
                "quantity": item.get("quantity", 1),
            })

    for item in manifest["backpack"]:
        items.append({
            "id": item["id"],
            "name": item["name"],
            "rarity": item["rarity"],
            "slot_type": item["slot_type"],
            "equipped": False,
            "is_consumable": item["is_consumable"],
            "is_quest_item": item["is_quest_item"],
            "effects": item["effects"],
            "quantity": item.get("quantity", 1),
        })

    return items


def reconcile_with_chain(
    player_uuid: str,
    chain_items: list[dict],
    kg_manifest: dict[str, Any] | None = None,
) -> None:
    """Lazy reconciliation: compare KG inventory with chain Items table.

    Chain always wins. Called when divergence is detected during manifest read.
    Idempotent — safe to call multiple times.

    Args:
        player_uuid: The player whose inventory to reconcile.
        chain_items: Items from chain with {id, name, rarity, ownerId, locationId}.
        kg_manifest: Pre-fetched manifest, or None to fetch fresh.
    """
    if kg_manifest is None:
        kg_manifest = get_inventory_manifest(player_uuid)

    client = get_client()
    now = datetime.now(timezone.utc).isoformat()

    # Collect KG item IDs (equipped + backpack)
    kg_items: dict[str, dict] = {}
    for _, item in kg_manifest["equipped"].items():
        if item:
            kg_items[item["id"]] = item
    for item in kg_manifest["backpack"]:
        kg_items[item["id"]] = item

    chain_item_ids = {ci["id"] for ci in chain_items}
    kg_item_ids = set(kg_items.keys())

    # Items in chain but not in KG → create missing CARRIES edges
    for ci in chain_items:
        if ci["id"] not in kg_item_ids:
            try:
                client.kg.create_edge(
                    player_uuid, ci["id"], "CARRIES",
                    f"Reconciled: {ci.get('name', 'item')}",
                )
                logger.info("Reconciled missing KG edge for item %s", ci["id"])
            except Exception:
                logger.warning("Failed to reconcile item %s", ci["id"])

    # Items in KG but not in chain → expire stale CARRIES edges
    for item_id in kg_item_ids - chain_item_ids:
        try:
            # Get the edge and mark it expired
            edges = client.kg.get_edges(
                player_uuid, direction="outgoing", edge_type="CARRIES",
            )
            for edge in edges:
                target = edge.get("target", {})
                tid = target.get("uuid", target.get("id", ""))
                if tid == item_id and not _is_expired(edge):
                    # Mark expired — Graphiti supports setting expired_at
                    edge_uuid = edge.get("uuid", edge.get("id", ""))
                    if edge_uuid:
                        client.kg.update_edge(edge_uuid, expired_at=now)
                        logger.info("Expired orphaned KG edge for item %s", item_id)
        except Exception:
            logger.warning("Failed to expire stale edge for item %s", item_id)


def _empty_manifest() -> dict[str, Any]:
    """Return an empty inventory manifest."""
    return {
        "equipped": {slot: None for slot in EQUIPMENT_SLOTS},
        "backpack": [],
        "capacity": DEFAULT_CAPACITY,
        "count": 0,
        "weight": 0,
        "max_weight": DEFAULT_MAX_WEIGHT,
    }
