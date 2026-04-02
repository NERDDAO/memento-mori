"""State routes — query current game state from KG."""

import asyncio
from fastapi import APIRouter, Query

from gateway.log import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/state")
async def get_state(player_id: str = Query(...)):
    """Get current game state for a player from the KG."""
    try:
        from memento.bonfires_client import get_client
        client = await asyncio.to_thread(get_client)

        result = await asyncio.to_thread(client.kg.search, player_id, 10)
        entities = result.get("entities", result.get("nodes", []))

        player_data = {}
        location = "Unknown"
        inventory = []

        for entity in entities:
            labels = entity.get("labels", [])
            if "Player" in labels:
                player_data = entity
            elif "Location" in labels:
                location = entity.get("name", "Unknown")
            elif "Item" in labels:
                inventory.append({
                    "name": entity.get("name", "?"),
                    "rarity": "common",
                })

        return {
            "player_id": player_id,
            "name": player_data.get("name", "Unknown"),
            "location": location,
            "health": 100,
            "max_health": 100,
            "level": 1,
            "xp": 0,
            "inventory": inventory,
        }
    except Exception:
        logger.error("KG state query failed, returning degraded state", exc_info=True)
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
