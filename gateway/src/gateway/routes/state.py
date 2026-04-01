"""State routes — query current game state."""

from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/state")
async def get_state(player_id: str = Query(...)):
    """Get current game state for a player."""
    # Phase 8 will query the KG for actual state
    return {
        "player_id": player_id,
        "location": "Unknown",
        "health": 100,
        "inventory": [],
    }
