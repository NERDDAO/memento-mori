"""Movement MCP tool — allows NPCs to move within a room."""

import json
import logging
from crewai.tools import tool

logger = logging.getLogger(__name__)


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
