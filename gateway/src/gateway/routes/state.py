"""State routes — query current game state from KG."""

import asyncio
from fastapi import APIRouter, Query
from pydantic import BaseModel

from gateway.log import get_logger

logger = get_logger(__name__)

router = APIRouter()


async def _get_inventory_items(player_id: str, state_result: dict) -> list[dict]:
    """Get inventory items using manifest, with fallback to basic list."""
    try:
        from memento.inventory_manifest import get_inventory_as_state_update
        return await asyncio.to_thread(get_inventory_as_state_update, player_id)
    except Exception:
        # Fallback to basic inventory from session state
        return [{"name": n, "rarity": "common"} for n in state_result.get("inventory", [])]


@router.get("/state")
async def get_state(player_id: str = Query(...)):
    """Get current game state for a player from the KG (UUID-based)."""
    try:
        from memento.session import SessionManager
        sm = SessionManager()
        result = await asyncio.to_thread(sm.restore_player_state, player_id)
        return {
            "player_id": player_id,
            "name": result.get("player_name", "Unknown"),
            "location": result.get("location_name", "Unknown"),
            "health": result.get("health", 100),
            "max_health": result.get("max_health", 100),
            "level": 1,
            "xp": 0,
            "inventory": await _get_inventory_items(player_id, result),
        }
    except Exception:
        logger.error("State query failed", exc_info=True)
        return {
            "player_id": player_id,
            "location": "Unknown",
            "health": 100,
            "inventory": [],
            "degraded": True,
        }


@router.get("/worldmap")
async def get_world_map():
    """Get the world map — all locations and their exit connections from KG."""
    try:
        from memento.bonfires_client import get_client
        client = await asyncio.to_thread(get_client)

        # Search for all Location entities
        result = await asyncio.to_thread(client.kg.search, "Location", 50)
        entities = result.get("entities", result.get("nodes", []))
        edges = result.get("edges", [])

        rooms = []
        for entity in entities:
            labels = entity.get("labels", [])
            if "Location" in labels:
                rooms.append({
                    "id": str(entity.get("uuid", entity.get("name", ""))),
                    "name": entity.get("name", "Unknown"),
                    "x": 0,
                    "y": 0,
                })

        # Build connections from EXIT_TO / ADJACENT_TO edges
        connections = []
        location_names = {r["name"] for r in rooms}
        for edge in edges:
            rel = edge.get("relationship", edge.get("name", "")).upper()
            if rel in ("EXIT_TO", "ADJACENT_TO", "CONNECTS_TO"):
                source = edge.get("source_name", edge.get("source_node_name", ""))
                target = edge.get("target_name", edge.get("target_node_name", ""))
                if source in location_names and target in location_names:
                    # Try to extract direction from edge fact
                    fact = edge.get("fact", "")
                    direction = ""
                    for d in ["north", "south", "east", "west", "up", "down"]:
                        if d in fact.lower():
                            direction = d
                            break
                    connections.append({
                        "from": source,
                        "to": target,
                        "direction": direction,
                    })

        # Also build connections from room_map exits
        for room in rooms:
            try:
                entity_data = await asyncio.to_thread(client.kg.get_entity, room["id"])
                if isinstance(entity_data, dict) and "entity" in entity_data:
                    entity_data = entity_data["entity"]
                import json
                rm_str = entity_data.get("room_map", "")
                if rm_str:
                    rm = json.loads(rm_str) if isinstance(rm_str, str) else rm_str
                    for exit in rm.get("exits", []):
                        target = exit.get("target", "")
                        if target and target in location_names:
                            connections.append({
                                "from": room["name"],
                                "to": target,
                                "direction": exit.get("direction", ""),
                            })
            except Exception:
                continue

        # Deduplicate connections
        seen = set()
        unique_connections = []
        for c in connections:
            key = tuple(sorted([c["from"], c["to"]]))
            if key not in seen:
                seen.add(key)
                unique_connections.append(c)

        return {
            "rooms": rooms,
            "connections": unique_connections,
        }
    except Exception:
        logger.error("World map query failed", exc_info=True)
        return {"rooms": [], "connections": []}


class ManifestRequest(BaseModel):
    location_uuid: str


@router.post("/room-manifest")
async def room_manifest(req: ManifestRequest):
    """Get complete room manifest — all NPCs, items, players, exits, tile map.

    Public endpoint (no auth) — used by client session flow.
    """
    from memento.room_manifest import get_room_manifest
    result = await asyncio.to_thread(get_room_manifest, req.location_uuid)
    return result
