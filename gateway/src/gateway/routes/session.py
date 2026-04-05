"""Session routes — create and join game sessions."""

import asyncio
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from gateway.log import get_logger

logger = get_logger(__name__)

router = APIRouter()


class CreateSessionRequest(BaseModel):
    player_name: str = Field(..., min_length=1, max_length=30, pattern=r'^[a-zA-Z0-9_ -]+$')
    game_id: str = Field("default", max_length=64)
    wallet_address: str = Field(..., min_length=42, max_length=42, pattern=r'^0x[a-fA-F0-9]{40}$')
    archetype: str = Field("", max_length=20, pattern=r'^[a-zA-Z]*$')


class CreateSessionResponse(BaseModel):
    player_id: str
    session_id: str
    location: str
    opening_narrative: str = ""
    archetype: str = ""
    health: int = 100
    max_health: int = 100
    skills: dict = {}
    inventory: list = []
    room_map: dict | None = None


@router.post("/session/create", response_model=CreateSessionResponse)
async def create_session(req: CreateSessionRequest, request: Request):
    """Create a new game session — creates player in KG, registers Matrix user, generates opening narration."""
    from gateway.rate_limit import session_limiter
    client_ip = request.client.host if request.client else "unknown"
    session_limiter.check(client_ip)

    try:
        from memento.session import SessionManager
        sm = SessionManager()
        result = await asyncio.to_thread(
            sm.create_player, req.player_name,
            wallet_address=req.wallet_address,
            archetype=req.archetype,
        )

        # Register a Matrix user for this player
        from gateway.app import bridge
        if bridge and bridge.connected:
            await bridge.register_player(req.player_name, result["player_id"])

        # Store player name for presence tracking
        from gateway.app import ws_hub
        if ws_hub:
            ws_hub.player_names[result["player_id"]] = req.player_name

        return CreateSessionResponse(
            player_id=result["player_id"],
            session_id=result["session_id"],
            location=result["location_name"],
            opening_narrative=result.get("opening_narrative", ""),
            archetype=result.get("archetype", ""),
            health=result.get("health", 100),
            max_health=result.get("max_health", 100),
            skills=result.get("skills", {}),
            inventory=result.get("inventory", []),
            room_map=result.get("room_map"),
        )
    except Exception:
        logger.error("Session creation via KG failed, using fallback", exc_info=True)
        import uuid
        player_id = str(uuid.uuid4())

        # Still try to register Matrix user in fallback
        from gateway.app import bridge
        if bridge and bridge.connected:
            await bridge.register_player(req.player_name, player_id)

        from gateway.app import ws_hub
        if ws_hub:
            ws_hub.player_names[player_id] = req.player_name

        return CreateSessionResponse(
            player_id=player_id,
            session_id="fallback",
            location="The Threshold",
            opening_narrative=f"Welcome, {req.player_name}. Your journey begins.",
        )


@router.get("/archetypes")
async def list_archetypes():
    """List available character archetypes."""
    from memento.config.archetypes import list_archetypes as _list
    archetypes = _list()
    # Strip starting_items details for the preview (keep names only)
    result = []
    for arch in archetypes:
        result.append({
            "name": arch["name"],
            "description": arch.get("description", ""),
            "stats": arch.get("stats", {}),
            "skills": arch.get("skills", {}),
            "starting_items": [i["name"] for i in arch.get("starting_items", [])],
        })
    return result


class CharactersRequest(BaseModel):
    wallet_address: str = Field(..., min_length=42, max_length=42, pattern=r'^0x[a-fA-F0-9]{40}$')


@router.post("/session/characters")
async def list_characters(req: CharactersRequest):
    """List existing characters for a wallet address.

    When chain is enabled, queries the MUD indexer for authoritative
    wallet→character mapping. Falls back to KG search when chain is off.
    """
    from memento.config.chain import CHAIN_ENABLED

    if CHAIN_ENABLED:
        # Onchain path: query MUD indexer (authoritative)
        from gateway.chain_client import fetch_characters_by_wallet, fetch_death_info
        try:
            characters = await fetch_characters_by_wallet(req.wallet_address)
            for char in characters:
                if not char.get("alive", True):
                    death = await fetch_death_info(char["player_id"])
                    char["is_dead"] = True
                    char["death_cause"] = death.get("cause", "") if death else ""
                    char["death_location"] = death.get("location", "") if death else ""
                else:
                    char["is_dead"] = False
                    char["death_cause"] = ""
                    char["death_location"] = ""
            return {"characters": characters}
        except Exception:
            logger.warning("Onchain character lookup failed, falling back to KG", exc_info=True)

    # Fallback: KG-based lookup
    try:
        from memento.session import SessionManager
        sm = SessionManager()
        characters = await asyncio.to_thread(sm.get_user_characters, req.wallet_address)
        return {"characters": characters}
    except Exception:
        logger.warning("Character list failed", exc_info=True)
        return {"characters": []}


class JoinSessionRequest(BaseModel):
    player_id: str
    game_id: str = "default"


class JoinSessionResponse(BaseModel):
    player_id: str
    session_id: str
    location: str
    health: int = 100
    max_health: int = 100
    archetype: str = ""
    skills: dict = {}
    inventory: list = []
    room_map: dict | None = None


@router.post("/session/join", response_model=JoinSessionResponse)
async def join_session(req: JoinSessionRequest, request: Request):
    """Join an existing game session — restores full player state from KG."""
    try:
        from memento.session import SessionManager
        sm = SessionManager()
        result = await asyncio.to_thread(sm.restore_player_state, req.player_id)

        # Register Matrix user for presence
        from gateway.app import bridge
        if bridge and bridge.connected:
            player_name = result.get("player_name", "Unknown")
            await bridge.register_player(player_name, req.player_id)

        # Store player name for presence tracking
        from gateway.app import ws_hub
        if ws_hub:
            ws_hub.player_names[req.player_id] = result.get("player_name", "Unknown")

        # Ensure NPCs are in the room (rejoin any that were kicked)
        location_name = result.get("location_name", "The Threshold")
        try:
            if bridge and bridge.connected:
                room_id = await bridge.get_or_create_room(location_name)
                logger.info("Ensuring NPCs in room %s for %s", room_id, location_name)
                await bridge.ensure_npcs_in_room(room_id)
            else:
                logger.info("Bridge not connected, skipping NPC rejoin")
        except Exception:
            logger.error("NPC rejoin on session join failed", exc_info=True)

        return JoinSessionResponse(
            player_id=req.player_id,
            session_id=f"session-{req.player_id[:8]}",
            location=result.get("location_name", "The Threshold"),
            health=result.get("health", 100),
            max_health=result.get("max_health", 100),
            archetype=result.get("archetype", ""),
            skills=result.get("skills", {}),
            inventory=result.get("inventory", []),
            room_map=result.get("room_map"),
        )
    except Exception:
        logger.error("Session join failed, using fallback", exc_info=True)
        return JoinSessionResponse(
            player_id=req.player_id,
            session_id=f"session-{req.player_id[:8]}",
            location="The Threshold",
        )
