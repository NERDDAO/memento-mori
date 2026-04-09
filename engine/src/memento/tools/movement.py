"""Movement MCP tool — allows NPCs to move within a room.

Also exposes :func:`move_within_room`, a transport-neutral helper that
owns the full within-room move pipeline (validation + KG updates +
chain sync). Both the legacy HTTP route ``gateway.routes.engine.move_within``
and the MCP handler ``mm_move_within`` in ``gateway.mcp_server`` are thin
wrappers around it.
"""

from __future__ import annotations

import asyncio
import json
import logging
from crewai.tools import tool

logger = logging.getLogger(__name__)


async def move_within_room(
    npc_id: str,
    target_x: int,
    target_y: int,
) -> dict:
    """Validate and execute a within-room NPC move.

    Mirrors the legacy HTTP route body at gateway.routes.engine:move_within
    and the MCP handler body at gateway.mcp_server.mm_move_within. Returns
    a dict with success flag, from/to coordinates, and distance. On failure
    returns ``{"success": False, "error": "<reason>"}``.

    Callers are responsible for ws broadcasting — this helper does NOT emit
    ``tool_event`` or ``position_update`` messages. Transport layers pass
    the returned dict to ``broadcast_tool_event(ws_hub, ...)`` and/or
    ``ws_hub.broadcast_to_location(...)`` if they want it visible to
    clients. On success, the result dict includes ``npc_name`` and
    ``location`` so callers can build their own broadcast payloads
    without re-resolving the NPC.
    """
    from gateway.npc_registry import (
        resolve_npc_kg_uuid,
        resolve_npc_location,
        resolve_npc_name,
    )
    from memento.bonfires_client import get_client

    npc_name = resolve_npc_name(npc_id)
    location = resolve_npc_location(npc_id)
    npc_uuid = resolve_npc_kg_uuid(npc_id)

    if not npc_uuid:
        return {"success": False, "error": "Cannot resolve NPC UUID"}

    client = await asyncio.to_thread(get_client)

    entity = await asyncio.to_thread(client.kg.get_entity, npc_uuid)
    if isinstance(entity, dict) and "entity" in entity:
        entity = entity["entity"]

    # Find location UUID from edges
    location_uuid = ""
    try:
        edges = await asyncio.to_thread(
            client.kg.get_edges, npc_uuid,
            direction="outgoing", edge_type="LOCATED_IN",
        )
        if edges:
            target = edges[0].get("target", {})
            location_uuid = target.get("uuid", target.get("id", ""))
    except Exception:
        pass

    # Get current position from room manifest
    current_x, current_y = 0, 0
    room_width, room_height = 35, 18
    tiles = []
    if location_uuid:
        try:
            from memento.room_manifest import get_room_manifest
            manifest = await asyncio.to_thread(get_room_manifest, location_uuid)
            room_width = manifest.get("width", 35)
            room_height = manifest.get("height", 18)
            tiles = manifest.get("tiles", [])
            npc_lower = npc_name.lower()
            for npc in manifest.get("npcs", []):
                if npc.get("name", "").lower() == npc_lower:
                    current_x, current_y = npc.get("x", 0), npc.get("y", 0)
                    break
        except Exception:
            pass

    # Validate range (Manhattan distance <= 5)
    distance = abs(target_x - current_x) + abs(target_y - current_y)
    if distance > 5:
        return {"success": False, "error": f"Too far: {distance} tiles (max 5)"}

    # Validate bounds
    if target_x >= room_width or target_y >= room_height:
        return {"success": False, "error": f"Out of bounds ({room_width}x{room_height})"}

    # Validate walkability
    if tiles:
        idx = target_y * room_width + target_x
        tile = tiles[idx] if idx < len(tiles) else "#"
        if tile in ("#", " "):
            return {"success": False, "error": f"Tile ({target_x},{target_y}) is blocked"}

    return {
        "success": True,
        "from": {"x": current_x, "y": current_y},
        "to": {"x": target_x, "y": target_y},
        "distance": distance,
        "npc_name": npc_name,
        "npc_uuid": npc_uuid,
        "location": location,
    }


@tool
def mm_move(target_x: int, target_y: int) -> str:
    """Move to a target tile position in the current room.

    Use this to approach a player, back away from danger, or patrol.
    Movement range is limited to 5 tiles per call (Manhattan distance).

    Args:
        target_x: Target x coordinate in the room grid.
        target_y: Target y coordinate in the room grid.

    Returns:
        Success message with new position, or error if blocked/out of range.
    """
    from memento.bonfires_client import get_client
    from memento.tools._context import get_npc_context

    ctx = get_npc_context()
    if not ctx:
        return "Error: No NPC context available. Cannot determine current position."

    npc_uuid = ctx.get("uuid", "")
    location_uuid = ctx.get("location_uuid", "")
    current_x = ctx.get("x", 0)
    current_y = ctx.get("y", 0)

    # Validate movement range (Manhattan distance <= 5)
    distance = abs(target_x - current_x) + abs(target_y - current_y)
    if distance > 5:
        return f"Error: Target ({target_x},{target_y}) is {distance} tiles away. Maximum range is 5."

    if distance == 0:
        return f"You're already at ({target_x},{target_y})."

    # Validate walkability from room map
    try:
        from memento.room_manifest import get_room_manifest
        manifest = get_room_manifest(location_uuid)
        room_map = manifest.get("room_map", {})
        tiles = room_map.get("tiles", [])
        width = room_map.get("width", 35)
        height = room_map.get("height", 18)

        if target_x < 0 or target_x >= width or target_y < 0 or target_y >= height:
            return f"Error: ({target_x},{target_y}) is out of bounds (room is {width}x{height})."

        idx = target_y * width + target_x
        tile = tiles[idx] if idx < len(tiles) else "#"
        if tile == "#" or tile == " ":
            return f"Error: Tile at ({target_x},{target_y}) is blocked ('{tile}')."
    except Exception:
        logger.debug("Room map validation failed", exc_info=True)

    # Update position in KG
    client = get_client()
    try:
        entity = client.kg.get_entity(npc_uuid)
        attrs = entity.get("attributes", {})
        if isinstance(attrs, str):
            attrs = json.loads(attrs) if attrs else {}
        attrs["position"] = {"x": target_x, "y": target_y}
        labels = entity.get("labels", [])
        summary = entity.get("summary", "")
        client.kg.update_entity(npc_uuid, ctx.get("name", ""), labels, summary, attributes=attrs)
    except Exception:
        logger.warning("Position KG update failed for %s", npc_uuid, exc_info=True)

    # Write position onchain
    try:
        import asyncio
        from gateway.chain_client import write_position
        loop = asyncio.new_event_loop()
        loop.run_until_complete(write_position(npc_uuid, location_uuid, target_x, target_y))
        loop.close()
    except Exception:
        logger.debug("Position chain write skipped", exc_info=True)

    logger.info("NPC %s moved from (%d,%d) to (%d,%d)", ctx.get("name", ""), current_x, current_y, target_x, target_y)
    return f"Moved to ({target_x},{target_y}). Distance: {distance} tiles."
