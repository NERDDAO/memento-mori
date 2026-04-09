# gateway/src/gateway/engine_events.py
"""Transport-neutral engine event broadcasting.

Tool handlers call ``broadcast_tool_event`` to push ``tool_event`` messages
to players at the relevant location via the shared WebSocket hub. The hub
reference is passed in explicitly so this module has no framework or
request-context coupling — it can be called from MCP tool handlers,
background tasks, or tests.
"""

from __future__ import annotations


async def broadcast_tool_event(
    ws_hub,
    tool: str,
    npc_id: str,
    summary: str,
    data: dict | None = None,
) -> None:
    """Push a ``tool_event`` to all players at the NPC's location.

    ``ws_hub`` is the gateway's :class:`gateway.ws.WebSocketHub` (or ``None``
    if the gateway is running without one — the call becomes a no-op). The
    NPC's display name and current location are resolved from
    :mod:`gateway.npc_registry` so callers only need to pass the raw id.
    """
    if not ws_hub:
        return
    from gateway.npc_registry import resolve_npc_name, resolve_npc_location
    npc = resolve_npc_name(npc_id)
    location = resolve_npc_location(npc_id)
    msg = {
        "type": "tool_event",
        "tool": tool,
        "npc": npc,
        "summary": summary,
        "data": data or {},
        "location": location,
        "channel": "narrative",
    }
    if location:
        await ws_hub.broadcast_to_location(location, msg)
    else:
        await ws_hub.broadcast_all(msg)
