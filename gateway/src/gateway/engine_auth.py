# gateway/src/gateway/engine_auth.py
"""Auth + capability gating for engine tool endpoints.

Verifies ENGINE_API_TOKEN and checks NPC's KG labels
to determine if the requested tool is allowed.
"""

import asyncio
import os

from fastapi import HTTPException, Header


async def verify_engine_token(authorization: str = Header("")) -> None:
    """Verify the bearer token matches ENGINE_API_TOKEN."""
    expected = os.getenv("ENGINE_API_TOKEN", "")
    if not expected:
        return  # No token configured = no auth (dev mode)
    if not authorization.startswith("Bearer ") or authorization[7:] != expected:
        raise HTTPException(status_code=403, detail="Invalid engine token")


async def check_tool_access(npc_id: str, tool_name: str) -> None:
    """Check if this NPC can call this tool based on its KG labels.

    Resolves agent ID → KG UUID via npc_registry, then fetches labels from KG.
    Raises 403 if the tool is not in the NPC's allowed set.
    """
    from memento.tools.tool_labels import get_allowed_tools, INNATE_TOOLS

    # Innate tools always allowed — skip KG fetch
    if tool_name in INNATE_TOOLS:
        return

    # No NPC ID = dev/test mode, allow everything
    if not npc_id:
        return

    # Resolve agent ID → KG entity UUID via registry
    from gateway.npc_registry import resolve_npc_kg_uuid
    kg_uuid = resolve_npc_kg_uuid(npc_id)

    # No KG UUID in registry — try using npc_id directly (legacy/fallback)
    entity_id = kg_uuid or npc_id

    # Fetch NPC labels from KG
    try:
        from memento.bonfires_client import get_client
        client = await asyncio.to_thread(get_client)
        entity = await asyncio.to_thread(client.kg.get_entity, entity_id)
        if isinstance(entity, dict) and "entity" in entity:
            entity = entity["entity"]
        labels = entity.get("labels", []) if isinstance(entity, dict) else []
    except Exception:
        labels = []

    allowed = get_allowed_tools(labels)
    if tool_name not in allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "capability_missing",
                "tool": tool_name,
                "npc_labels": labels,
                "message": f"This NPC doesn't have access to {tool_name}. "
                           f"Add the required label to unlock it.",
            },
        )
