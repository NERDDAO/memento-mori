# engine/src/memento/tools/state.py
"""Pure helpers for NPC state inspection.

Callable from any transport (HTTP routes, MCP handlers, tests). No FastAPI,
no Pydantic models, no request context — just entity name in, state dict out.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def get_entity_state(entity_name: str) -> dict:
    """Return the complete inspected state for the given entity by name.

    Mirrors the legacy HTTP route body at gateway.routes.engine:get_state.
    Includes HP, labels, inventory, recent events, and (if resolvable) the
    spatial room context.

    Raises:
        Whatever the underlying KG client raises.
    """
    from memento.bonfires_client import get_client
    client = await asyncio.to_thread(get_client)

    # Search for entity
    result = await asyncio.to_thread(client.kg.search, entity_name, 5)
    entities = result.get("entities", result.get("nodes", []))
    edges = result.get("edges", [])

    entity = entities[0] if entities else {"name": entity_name, "labels": [], "summary": ""}

    # Extract recent events mentioning this entity
    episodes = result.get("episodes", [])
    recent = []
    for ep in episodes[:5]:
        content = ep.get("content", {})
        summary = content.get("content", "") if isinstance(content, dict) else str(content)
        if entity_name.lower() in summary.lower():
            recent.append(summary[:200])

    # Build spatial awareness — find the NPC's location and room positions
    spatial: dict = {}
    try:
        entity_uuid = entity.get("uuid", entity.get("id", ""))
        if entity_uuid:
            # Find LOCATED_IN edge to get current location UUID
            loc_edges = await asyncio.to_thread(
                client.kg.get_edges, entity_uuid,
                direction="outgoing", edge_type="LOCATED_IN",
            )
            if loc_edges:
                loc_target = loc_edges[0].get("target", {})
                loc_uuid = loc_target.get("uuid", loc_target.get("id", ""))
                if loc_uuid:
                    from memento.room_manifest import get_room_manifest
                    room_map = await asyncio.to_thread(get_room_manifest, loc_uuid)

                    # Find this NPC's own position in the room
                    own_x, own_y = 0, 0
                    entity_lower = entity_name.lower()
                    for npc in room_map.get("npcs", []):
                        if npc.get("name", "").lower() == entity_lower:
                            own_x, own_y = npc.get("x", 0), npc.get("y", 0)
                            break

                    spatial["room_width"] = room_map.get("width", 35)
                    spatial["room_height"] = room_map.get("height", 18)
                    spatial["own_position"] = {"x": own_x, "y": own_y}

                    # All other entities in the room with positions
                    positions = []
                    for npc in room_map.get("npcs", []):
                        positions.append({
                            "type": "NPC",
                            "name": npc.get("name", "?"),
                            "x": npc.get("x", 0),
                            "y": npc.get("y", 0),
                        })
                    for item in room_map.get("items", []):
                        positions.append({
                            "type": "ITEM",
                            "name": item.get("name", "?"),
                            "x": item.get("x", 0),
                            "y": item.get("y", 0),
                        })
                    for player in room_map.get("players", []):
                        positions.append({
                            "type": "PLAYER",
                            "name": player.get("name", "?"),
                            "x": player.get("x", 0),
                            "y": player.get("y", 0),
                        })
                    spatial["room_entities"] = positions
    except Exception:
        logger.debug("Spatial lookup failed for %s", entity_name, exc_info=True)

    return {
        "name": entity.get("name", entity_name),
        "labels": entity.get("labels", []),
        "summary": entity.get("summary", ""),
        "edges": [
            {"source": e.get("source_node_name", ""), "target": e.get("target_node_name", ""),
             "relationship": e.get("name", ""), "fact": e.get("fact", "")}
            for e in edges[:10]
        ],
        "recent_events": recent,
        **spatial,
    }
