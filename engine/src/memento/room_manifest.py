"""Room manifest — single source of truth for room state.

Assembles a complete view of a room's contents from the KG by UUID.
Used by session create/join, round controller, NPC agent tools, and
the gateway state route.
"""

from __future__ import annotations

import json
from typing import Any

from memento.bonfires_client import get_client
from memento.log import get_logger
from memento.room_map import generate_fallback_map

logger = get_logger(__name__)

# NPC-related labels — entities with these are NPCs, not items or players
NPC_LABELS = frozenset({
    "NPC", "Barkeeper", "Merchant", "InformationBroker", "Guard",
    "Innkeeper", "Blacksmith", "Healer", "Priest", "Villager",
})

ITEM_LABELS = frozenset({
    "Item", "Weapon", "Armor", "Consumable", "Tool", "Key", "Scroll",
})


def _extract_entity_attr(entity: dict, key: str) -> str | dict | None:
    """Extract an attribute from a KG entity.

    KG stores attributes as a JSON blob inside the summary field.
    Checks both direct entity keys and parsed summary JSON.
    """
    val = entity.get(key)
    if val is not None:
        return val
    summary = entity.get("summary", "")
    if isinstance(summary, str) and summary.startswith("{"):
        try:
            parsed = json.loads(summary)
            return parsed.get(key)
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def get_room_manifest(location_uuid: str) -> dict[str, Any]:
    """Assemble a complete manifest of a room's contents from the KG.

    Queries the location entity and its incoming/outgoing edges to build
    a unified view of tiles, NPCs, items, players, and exits.

    Args:
        location_uuid: UUID of the location entity in the KG.

    Returns:
        A room manifest dict compatible with the client's RoomMap type:
        {id, name, summary, width, height, tiles, npcs, items, players, exits, spawn}
    """
    client = get_client()

    # 1. Get location entity
    try:
        entity = client.kg.get_entity(location_uuid)
    except Exception:
        logger.warning("Location entity not found: %s", location_uuid)
        return generate_fallback_map("Unknown")

    location_name = entity.get("name", "Unknown")

    # 2. Get stored room_map (tile grid) from entity attributes
    room_map = None
    rm_raw = _extract_entity_attr(entity, "room_map")
    if rm_raw:
        try:
            room_map = json.loads(rm_raw) if isinstance(rm_raw, str) else rm_raw
        except (json.JSONDecodeError, TypeError):
            pass

    # Start with stored map or generate fallback
    if room_map and isinstance(room_map, dict) and room_map.get("tiles"):
        manifest = dict(room_map)
    else:
        manifest = generate_fallback_map(location_name)

    manifest["id"] = location_uuid
    manifest["name"] = location_name

    # Extract summary (plain text, not JSON blob)
    summary = entity.get("summary", "")
    if isinstance(summary, str) and summary.startswith("{"):
        try:
            parsed = json.loads(summary)
            summary = parsed.get("summary", summary)
        except (json.JSONDecodeError, TypeError):
            pass
    manifest["summary"] = summary

    # 3. Get entities AT this location via incoming LOCATED_IN edges
    npcs: list[dict] = list(manifest.get("npcs", []))
    items: list[dict] = list(manifest.get("items", []))
    players: list[dict] = []
    known_ids = {n.get("id") for n in npcs} | {i.get("id") for i in items}

    try:
        edges = client.kg.get_edges(location_uuid, direction="incoming", edge_type="LOCATED_IN")
        for edge in edges:
            source = edge.get("source", {})
            source_id = source.get("uuid", source.get("id", ""))
            if source_id in known_ids:
                continue  # Already in the stored room_map
            known_ids.add(source_id)

            labels = set(source.get("labels", []))
            source_name = source.get("name", "Unknown")

            if labels & NPC_LABELS:
                npcs.append({
                    "id": source_id,
                    "name": source_name,
                    "x": 0, "y": 0, "ch": source_name[0].upper() if source_name else "?",
                })
            elif labels & ITEM_LABELS:
                items.append({
                    "id": source_id,
                    "name": source_name,
                    "x": 0, "y": 0, "ch": "!",
                })
            elif "Player" in labels:
                players.append({
                    "id": source_id,
                    "name": source_name,
                })
    except Exception:
        logger.debug("Failed to query LOCATED_IN edges for %s", location_uuid)

    manifest["npcs"] = npcs
    manifest["items"] = items
    manifest["players"] = players

    # 4. Get exits via outgoing EXIT_TO and ADJACENT_TO edges
    exits: list[dict] = list(manifest.get("exits", []))
    exit_target_ids = {e.get("target_id") for e in exits if e.get("target_id")}

    try:
        for edge_type in ("EXIT_TO", "ADJACENT_TO"):
            exit_edges = client.kg.get_edges(location_uuid, direction="outgoing", edge_type=edge_type)
            for edge in exit_edges:
                target = edge.get("target", {})
                target_id = target.get("uuid", target.get("id", ""))
                if target_id in exit_target_ids:
                    continue
                exit_target_ids.add(target_id)

                target_name = target.get("name", "unknown")
                direction = edge.get("label", "").lower() or "unknown"
                # Try to extract direction from edge fact/label
                fact = edge.get("fact", "")
                for d in ("north", "south", "east", "west"):
                    if d in fact.lower() or d in direction:
                        direction = d
                        break

                exits.append({
                    "direction": direction,
                    "target": target_name,
                    "target_id": target_id,
                    "x": 0, "y": 0, "ch": "+",
                })
    except Exception:
        logger.debug("Failed to query exit edges for %s", location_uuid)

    manifest["exits"] = exits

    return manifest
