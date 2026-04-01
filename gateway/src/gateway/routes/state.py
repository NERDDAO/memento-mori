"""State routes — query current game state from KG."""

import asyncio
from fastapi import APIRouter, Query

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
        return {
            "player_id": player_id,
            "location": "Unknown",
            "health": 100,
            "inventory": [],
        }
