# gateway/src/gateway/mcp_server.py
"""Streamable-HTTP MCP server exposing the memento engine tools.

This module builds a ``FastMCP`` instance that bonfires-ai (and any other
MCP-aware client) can reach over HTTP. The resulting ASGI app is designed
to be mounted at ``/mcp`` on the gateway FastAPI app so it shares the same
process — and therefore the same ``ws_hub`` / ``bridge`` / ``narrator_registry``
references — as the existing HTTP routes.

Tool handlers are registered in subsequent tasks (task-4 through task-7).
This file intentionally contains ONLY the scaffold: factory, auth
middleware, and a small ``_check_tool_access`` helper.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP

from gateway.engine_auth import bearer_token_valid, check_tool_access
from gateway.log import get_logger

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

    from gateway.matrix_bridge import MatrixBridge
    from gateway.ws import WebSocketHub

logger = get_logger(__name__)


# ── Auth helper ─────────────────────────────────────────────────────────────

async def _check_tool_access(npc_id: str, tool_name: str) -> None:
    """Wrap ``gateway.engine_auth.check_tool_access`` for MCP tool handlers.

    The upstream helper raises ``fastapi.HTTPException`` on capability failures
    (currently 403), which is meaningless to an MCP client. We catch *any*
    ``HTTPException`` and re-raise it as a ``RuntimeError`` prefixed with
    ``capability_missing:`` so the MCP runtime can surface it as a proper
    tool error.

    Stable contract — the ``capability_missing:`` prefix on the raised
    ``RuntimeError`` message is part of the tool-layer error contract.
    Future tasks (4-7) will swap the ``RuntimeError`` for
    ``mcp.shared.exceptions.McpError`` with a structured ``ErrorData``
    payload, but the ``capability_missing:`` marker must be preserved so
    downstream consumers (bonfires-ai, tests) can continue to detect this
    failure mode by string match until the structured error lands.
    """
    try:
        await check_tool_access(npc_id, tool_name)
    except HTTPException as exc:
        # Any HTTPException (not just 403) must be surfaced as a tool-layer
        # error — the MCP runtime can't render a FastAPI HTTPException.
        raise RuntimeError(
            f"capability_missing: {exc.detail or exc.status_code} "
            f"(tool={tool_name}, npc_id={npc_id})"
        ) from exc


# ── Bearer auth ASGI middleware ─────────────────────────────────────────────

def _unauthorized_response_factory(message: str):
    """Build a minimal 401 Starlette ``Response`` without importing at module load."""
    from starlette.responses import JSONResponse

    return JSONResponse(
        {"error": "unauthorized", "detail": message},
        status_code=401,
        headers={"WWW-Authenticate": 'Bearer realm="memento-engine"'},
    )


class _BearerAuthMiddleware:
    """ASGI middleware that enforces the engine bearer token on /mcp.

    Delegates the actual compare to
    :func:`gateway.engine_auth.bearer_token_valid`, which is a pure,
    framework-free predicate shared with the HTTP ``verify_engine_token``
    ``Depends``. Dev-mode passthrough (empty ``ENGINE_API_TOKEN``) is
    handled inside the predicate.
    """

    def __init__(self, app: "ASGIApp") -> None:
        self.app = app

    async def __call__(self, scope: "Scope", receive: "Receive", send: "Send") -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Pull Authorization header from raw ASGI scope.
        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        if not bearer_token_valid(auth):
            response = _unauthorized_response_factory("Invalid or missing engine token")
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


# ── Factory ─────────────────────────────────────────────────────────────────

def build_mcp_app(
    ws_hub: "WebSocketHub",
    bridge: "MatrixBridge | None",
    narrator_registry: "dict[str, str]",
) -> "ASGIApp":
    """Build the streamable-HTTP MCP ASGI app for the memento engine.

    The returned app is meant to be mounted at /mcp on the gateway FastAPI app.
    All captured refs (ws_hub, bridge, narrator_registry) are closed over so
    tool handlers can reach them without a FastAPI Request context.

    ``bridge`` may be ``None`` in dev environments where Matrix is not
    configured (see ``start.sh`` and ``example.env`` — ``MATRIX_BOT_TOKEN``
    ships empty by default). Tool handlers that can operate without Matrix
    (read-only tools, task-4) should tolerate ``bridge is None``. Tool
    handlers that genuinely require the bridge (e.g., ``mm_trigger_npc`` in
    task-6) MUST check for ``None`` at call time and raise a clear
    ``RuntimeError`` with an actionable message rather than crashing with
    an ``AttributeError`` — this is part of the tool-layer error contract.
    """
    mcp = FastMCP("memento-engine")

    # Captured for use by future tool handlers (task-5 through task-7).
    # Read-only handlers below do not touch these refs but they are kept in
    # scope via ``_unused_closure_refs`` so the factory shape is uniform.
    _unused_closure_refs = (ws_hub, bridge, narrator_registry)
    del _unused_closure_refs

    # ── Read/query tools (task 4) ──
    # These handlers mirror the matching HTTP routes in ``routes/engine.py``:
    # they call the same underlying functions with the same arguments, return
    # the same JSON-serialisable shapes, and do NOT broadcast tool_events
    # (broadcasts belong to the mutation-tool tasks). Docstrings are copied
    # verbatim from ``scripts/seed_engine_tools.py`` so the NPC-facing
    # tool description stays identical across HTTP and MCP transports.
    #
    # NOTE: ``mm_skill_check`` is intentionally deferred to task 5 — the HTTP
    # route broadcasts a ``tool_event`` on every call, which classifies it
    # as a mutation-ish tool for the purposes of this migration.

    @mcp.tool(name="mm_get_state")
    async def mm_get_state(npc_id: str, entity_name: str) -> dict:
        """Get an entity's current state from the knowledge graph — HP, inventory, labels, edges, recent events. Call this before responding to check your current condition."""
        await _check_tool_access(npc_id, "mm_get_state")
        from memento.bonfires_client import get_client
        client = await asyncio.to_thread(get_client)

        result = await asyncio.to_thread(client.kg.search, entity_name, 5)
        entities = result.get("entities", result.get("nodes", []))
        edges = result.get("edges", [])

        entity = entities[0] if entities else {"name": entity_name, "labels": [], "summary": ""}

        episodes = result.get("episodes", [])
        recent = []
        for ep in episodes[:5]:
            content = ep.get("content", {})
            summary = content.get("content", "") if isinstance(content, dict) else str(content)
            if entity_name.lower() in summary.lower():
                recent.append(summary[:200])

        spatial: dict = {}
        try:
            entity_uuid = entity.get("uuid", entity.get("id", ""))
            if entity_uuid:
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

                        own_x, own_y = 0, 0
                        entity_lower = entity_name.lower()
                        for npc in room_map.get("npcs", []):
                            if npc.get("name", "").lower() == entity_lower:
                                own_x, own_y = npc.get("x", 0), npc.get("y", 0)
                                break

                        spatial["room_width"] = room_map.get("width", 35)
                        spatial["room_height"] = room_map.get("height", 18)
                        spatial["own_position"] = {"x": own_x, "y": own_y}

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

    @mcp.tool(name="mm_get_world_time")
    async def mm_get_world_time(npc_id: str) -> dict:
        """Get current in-game time — moon phase, date, time of day, season."""
        await _check_tool_access(npc_id, "mm_get_world_time")
        from memento.tools.time import get_current_time
        t = get_current_time()
        return t.to_display()

    @mcp.tool(name="mm_search_world")
    async def mm_search_world(npc_id: str, query: str) -> dict:
        """Search the game world's knowledge graph for entities, locations, NPCs, items, relationships, and lore."""
        await _check_tool_access(npc_id, "mm_search_world")
        from memento.bonfires_client import get_client
        client = await asyncio.to_thread(get_client)
        result = await asyncio.to_thread(client.kg.search, query, 10)
        entities = result.get("entities", result.get("nodes", []))
        edges = result.get("edges", [])
        return {
            "entities": [
                {"uuid": e.get("uuid", ""), "name": e.get("name", ""), "labels": e.get("labels", []),
                 "summary": e.get("summary", "")}
                for e in entities
            ],
            "edges": [
                {"source": e.get("source_node_name", ""), "target": e.get("target_node_name", ""),
                 "relationship": e.get("name", ""), "fact": e.get("fact", "")}
                for e in edges
            ],
        }

    @mcp.tool(name="mm_get_entity")
    async def mm_get_entity(npc_id: str, name: str) -> dict:
        """Get detailed information about a specific game entity by name."""
        await _check_tool_access(npc_id, "mm_get_entity")
        from memento.bonfires_client import get_client
        from memento.tools.kg import _resolve_entity_uuid
        client = await asyncio.to_thread(get_client)
        uuid = await asyncio.to_thread(_resolve_entity_uuid, name)
        if not uuid:
            return {"error": "not_found", "name": name}
        entity = await asyncio.to_thread(client.kg.get_entity, uuid)
        if isinstance(entity, dict) and "entity" in entity:
            entity = entity["entity"]
        return {
            "uuid": uuid,
            "name": entity.get("name", name),
            "labels": entity.get("labels", []),
            "summary": entity.get("summary", ""),
        }

    @mcp.tool(name="mm_calculate_damage")
    async def mm_calculate_damage(
        npc_id: str,
        weapon_damage: int,
        attacker_strength: int,
        defender_armor: int,
    ) -> dict:
        """Calculate final damage from weapon damage, strength, and armor."""
        await _check_tool_access(npc_id, "mm_calculate_damage")
        from memento.tools.mechanics import calculate_damage as _calc
        calc = _calc.func
        result = calc(str(weapon_damage), str(attacker_strength), str(defender_armor))
        return {"result": result}

    @mcp.tool(name="mm_evaluate_disposition")
    async def mm_evaluate_disposition(
        npc_id: str,
        current_friendship: float,
        current_trust: float,
        interaction_type: str,
    ) -> dict:
        """Calculate how an interaction shifts friendship and trust."""
        await _check_tool_access(npc_id, "mm_evaluate_disposition")
        from memento.tools.mechanics import evaluate_disposition as _ed
        eval_disp = _ed.func
        result = eval_disp(str(current_friendship), str(current_trust), interaction_type)
        return {"result": result}

    @mcp.tool(name="mm_assess_combat")
    async def mm_assess_combat(
        npc_id: str,
        action: str,
        attacker: str,
        target: str,
        location: str,
    ) -> dict:
        """Evaluate a combat situation without resolving it."""
        await _check_tool_access(npc_id, "mm_assess_combat")

        def _run():
            from memento.crews.combat.assessment import make_combat_assessment_crew
            from gateway.routes.engine import _engine_lock
            with _engine_lock:
                crew = make_combat_assessment_crew(
                    action=action, attacker=attacker,
                    target=target, location=location,
                )
                return crew.kickoff().raw

        result = await asyncio.to_thread(_run)
        return {"assessment": result}

    @mcp.tool(name="mm_check_plausibility")
    async def mm_check_plausibility(npc_id: str, action: str, context: str) -> dict:
        """DRY RUN ONLY — verifies whether an action is physically valid WITHOUT performing it. DOES NOT mutate game state, DOES NOT move your NPC, DOES NOT resolve combat. This is optional validation before a mutation. After calling this and getting plausible=true, you MUST still call the action's specific mutation tool (mm_move_within, mm_move_to, mm_resolve_combat, etc.) to actually execute the action. Returns {plausible: bool, reason: string}."""
        await _check_tool_access(npc_id, "mm_check_plausibility")

        def _run():
            from memento.config import load_config, get_model_for_crew
            from crewai import LLM
            from gateway.routes.engine import _engine_lock
            with _engine_lock:
                model = get_model_for_crew("plausibility")
                llm = LLM(model=model, **load_config().get("llm", {}).get("params", {}))
                prompt = f"Is this action plausible given the context? Action: {action}\nContext: {context}\nRespond with PLAUSIBLE or IMPLAUSIBLE and a brief reason."
                response = llm.call([{"role": "user", "content": prompt}])
                plausible = "PLAUSIBLE" in response.upper() and "IMPLAUSIBLE" not in response.upper()
                return plausible, response

        plausible, reason = await asyncio.to_thread(_run)
        return {"plausible": plausible, "reason": reason}

    @mcp.tool(name="mm_inventory")
    async def mm_inventory(npc_id: str, entity_id: str) -> dict:
        """Get the inventory of any entity (player or NPC). Use to inspect what someone is carrying before trading."""
        await _check_tool_access(npc_id, "mm_inventory")
        from memento.inventory_manifest import get_inventory_manifest
        manifest = await asyncio.to_thread(get_inventory_manifest, entity_id)
        return manifest

    @mcp.tool(name="mm_room_manifest")
    async def mm_room_manifest(npc_id: str, location_uuid: str) -> dict:
        """Get complete room manifest — all NPCs, items, players, exits, tile map."""
        await _check_tool_access(npc_id, "mm_room_manifest")
        from memento.room_manifest import get_room_manifest
        result = await asyncio.to_thread(get_room_manifest, location_uuid)
        return result

    @mcp.tool(name="mm_reputation")
    async def mm_reputation(npc_id: str) -> dict:
        """Check how an action affects faction reputation."""
        await _check_tool_access(npc_id, "mm_reputation")
        # Simplified — full implementation would use make_reputation_crew
        return {"result": "reputation check not yet implemented"}

    @mcp.tool(name="mm_detect_events")
    async def mm_detect_events(npc_id: str) -> dict:
        """Detect event types in a scene."""
        await _check_tool_access(npc_id, "mm_detect_events")
        # Simplified — full implementation would use EventDetectionFlow
        return {"result": "event detection not yet implemented"}

    logger.info("mcp_server: built FastMCP('memento-engine') scaffold")

    raw_app = mcp.streamable_http_app()
    return _BearerAuthMiddleware(raw_app)
