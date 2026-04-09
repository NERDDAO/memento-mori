# gateway/src/gateway/mcp_server.py
"""Streamable-HTTP MCP server exposing the memento engine tools.

This module builds a ``FastMCP`` instance that bonfires-ai (and any other
MCP-aware client) can reach over HTTP. The resulting ASGI app is designed
to be mounted at ``/mcp`` on the gateway FastAPI app so it shares the same
process — and therefore the same ``ws_hub`` / ``bridge`` / ``narrator_registry``
references — as the existing HTTP routes.

Read/query tool handlers are registered via ``_register_read_tools``
(task 4). Mutation, combat, and design categories land in tasks 5-7
with their own ``_register_*`` helpers, each called from
``build_mcp_app`` to keep the factory small as the tool surface grows.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP

from gateway.engine_auth import bearer_token_valid, check_tool_access
from gateway.log import get_logger
from gateway.routes.engine import broadcast_tool_event

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


# ── Read-tool registrations ────────────────────────────────────────────────

def _register_read_tools(
    mcp: FastMCP,
    ws_hub: "WebSocketHub",
    bridge: "MatrixBridge | None",
    narrator_registry: "dict[str, str]",
) -> None:
    """Register the read/query tool handlers on ``mcp``.

    Handlers close over ``ws_hub`` / ``bridge`` / ``narrator_registry`` so
    future read tools can reach them without additional plumbing. The current
    batch does not touch those refs — they're accepted for uniformity with
    the mutation/combat/design registration helpers landing in tasks 5-7.

    These handlers mirror the matching HTTP routes in ``routes/engine.py``:
    they call the same underlying functions with the same arguments, return
    the same JSON-serialisable shapes, and do NOT broadcast tool_events
    (broadcasts belong to the mutation-tool tasks). Docstrings are copied
    verbatim from ``scripts/seed_engine_tools.py`` so the NPC-facing
    tool description stays identical across HTTP and MCP transports.

    NOTE: ``mm_skill_check`` is intentionally deferred to task 5 — the HTTP
    route broadcasts a ``tool_event`` on every call, which classifies it
    as a mutation-ish tool for the purposes of this migration.
    """
    _ = (ws_hub, bridge, narrator_registry)  # read tools don't touch these yet

    @mcp.tool(name="mm_get_state")
    async def mm_get_state(npc_id: str, entity_name: str) -> dict:
        """Get an entity's current state from the knowledge graph — HP, inventory, labels, edges, recent events. Call this before responding to check your current condition."""
        await _check_tool_access(npc_id, "mm_get_state")
        from memento.tools.state import get_entity_state
        return await get_entity_state(entity_name)

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
            from gateway.engine_state import engine_lock
            with engine_lock:
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
            from gateway.engine_state import engine_lock
            with engine_lock:
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
        # No capability gate: the HTTP route does not call check_tool_access,
        # and "mm_room_manifest" is not in INNATE_TOOLS or the generic kits,
        # so gating here would cause capability_missing errors for normal NPCs.
        from memento.room_manifest import get_room_manifest
        result = await asyncio.to_thread(get_room_manifest, location_uuid)
        return result

    @mcp.tool(name="mm_reputation")
    async def mm_reputation(npc_id: str) -> dict:
        """Check how an action affects faction reputation."""
        # No capability gate: mirrors the HTTP route, which is ungated.
        # Simplified — full implementation would use make_reputation_crew
        return {"result": "reputation check not yet implemented"}

    @mcp.tool(name="mm_detect_events")
    async def mm_detect_events(npc_id: str) -> dict:
        """Detect event types in a scene."""
        # No capability gate: mirrors the HTTP route, which is ungated.
        # Simplified — full implementation would use EventDetectionFlow
        return {"result": "event detection not yet implemented"}


# ── Mutation tools (task 5) ────────────────────────────────────────────────

def _register_mutation_tools(
    mcp: FastMCP,
    ws_hub: "WebSocketHub",
) -> None:
    """Register the world-mutation tool handlers on ``mcp``.

    Handlers close over ``ws_hub`` so they can call
    :func:`gateway.routes.engine.broadcast_tool_event` directly without a
    FastAPI ``Request`` context — exactly the broadcast points the matching
    HTTP routes hit.

    These handlers mirror the matching HTTP routes in ``routes/engine.py``:
    same underlying memento.tools / client.kg calls, same arguments, same
    return shapes. Docstrings are copied verbatim from
    ``scripts/seed_engine_tools.py`` so the NPC-facing tool description
    stays identical across HTTP and MCP transports.

    Broadcast inventory (mirrors HTTP routes exactly):
      - mm_skill_check, mm_give_item, mm_give_quest, mm_create_npc,
        mm_create_item, mm_move_to, mm_move_within, mm_inventory_transfer
        broadcast a ``tool_event``.
      - mm_remember_event, mm_update_entity, mm_create_location,
        mm_send_gossip, mm_npc_memory do NOT broadcast (HTTP routes don't
        either).
    """
    @mcp.tool(name="mm_skill_check")
    async def mm_skill_check(
        npc_id: str,
        skill_level: int,
        difficulty: int,
        modifiers: int = 0,
    ) -> dict:
        """Roll a d20 skill check. Returns PASS or FAIL with margin. Use for persuasion, stealth, lockpicking, any non-combat check."""
        # No capability gate: HTTP route does not call check_tool_access either.
        # (mm_skill_check is in INNATE_TOOLS, so any future gate would be a no-op today,
        # but the strict mirror rule requires matching HTTP behaviour exactly.)
        from memento.tools.mechanics import roll_skill_check as _rsc
        roll_skill_check = _rsc.func
        result = roll_skill_check(str(skill_level), str(difficulty), str(modifiers))
        await broadcast_tool_event(
            ws_hub,
            tool="mm_skill_check",
            npc_id=npc_id,
            summary=f"Skill check (DC {difficulty}): {result}",
        )
        return {"result": result}

    @mcp.tool(name="mm_remember_event")
    async def mm_remember_event(npc_id: str, summary: str) -> dict:
        """Record a significant event in the world's memory. Use for deaths, discoveries, betrayals, victories. The world will remember this."""
        await _check_tool_access(npc_id, "mm_remember_event")
        from memento.tools.kg import remember_event as _remember_tool
        _remember = _remember_tool.func
        result = await asyncio.to_thread(_remember, summary)
        return {"result": result}

    @mcp.tool(name="mm_update_entity")
    async def mm_update_entity(
        npc_id: str,
        name: str,
        new_summary: str = "",
        new_labels: str = "",
    ) -> dict:
        """Update an entity's summary or labels in the knowledge graph."""
        await _check_tool_access(npc_id, "mm_update_entity")
        from memento.tools.kg import update_entity as _update_tool
        _update = _update_tool.func
        result = await asyncio.to_thread(_update, name, new_summary, new_labels)
        return {"result": result}

    @mcp.tool(name="mm_give_item")
    async def mm_give_item(
        npc_id: str,
        item_name: str,
        from_entity: str,
        to_entity: str,
    ) -> dict:
        """Transfer an item from one entity to another. Use for quest rewards, trades, theft."""
        await _check_tool_access(npc_id, "mm_give_item")
        from memento.tools.kg import create_edge as _ce_tool
        create_edge = _ce_tool.func
        result = await asyncio.to_thread(
            create_edge, item_name, to_entity, "OWNED_BY",
            f"Transferred from {from_entity} to {to_entity}",
        )
        await broadcast_tool_event(
            ws_hub,
            tool="mm_give_item",
            npc_id=npc_id,
            summary=f"{from_entity} gave {item_name} to {to_entity}",
        )
        return {"result": result}

    @mcp.tool(name="mm_give_quest")
    async def mm_give_quest(
        npc_id: str,
        quest_name: str,
        description: str,
        giver_name: str,
        player_name: str,
    ) -> dict:
        """Create a quest and assign it to a player."""
        await _check_tool_access(npc_id, "mm_give_quest")
        from memento.tools.kg import create_entity as _cen, create_edge as _ced
        create_entity = _cen.func
        create_edge = _ced.func
        uuid = await asyncio.to_thread(create_entity, quest_name, "Quest", description)
        await asyncio.to_thread(
            create_edge, quest_name, player_name, "ASSIGNED_TO",
            f"Quest given by {giver_name}",
        )
        await asyncio.to_thread(
            create_edge, quest_name, giver_name, "GIVEN_BY", "",
        )
        await broadcast_tool_event(
            ws_hub,
            tool="mm_give_quest",
            npc_id=npc_id,
            summary=f"{giver_name} gave quest '{quest_name}' to {player_name}",
        )
        return {"uuid": uuid, "quest_name": quest_name, "assigned_to": player_name}

    @mcp.tool(name="mm_create_npc")
    async def mm_create_npc(
        npc_id: str,
        name: str,
        summary: str = "",
        location_name: str = "",
    ) -> dict:
        """Create a new NPC entity in the world."""
        await _check_tool_access(npc_id, "mm_create_npc")
        from memento.tools.kg import create_entity as _cen, create_edge as _ced
        create_entity = _cen.func
        create_edge = _ced.func
        uuid = await asyncio.to_thread(create_entity, name, "NPC", summary)
        if location_name:
            await asyncio.to_thread(
                create_edge, name, location_name, "LOCATED_IN", "",
            )
        await broadcast_tool_event(
            ws_hub,
            tool="mm_create_npc",
            npc_id=npc_id,
            summary=f"New NPC: {name}",
        )
        return {"uuid": uuid, "name": name, "entity_type": "NPC"}

    @mcp.tool(name="mm_create_item")
    async def mm_create_item(
        npc_id: str,
        name: str,
        summary: str = "",
        location_name: str = "",
    ) -> dict:
        """Create a new item in the world. Use for crafting, forging, finding."""
        await _check_tool_access(npc_id, "mm_create_item")
        from memento.tools.kg import create_entity as _cen, create_edge as _ced
        create_entity = _cen.func
        create_edge = _ced.func
        uuid = await asyncio.to_thread(create_entity, name, "Item", summary)
        if location_name:
            await asyncio.to_thread(
                create_edge, name, location_name, "LOCATED_IN", "",
            )
        await broadcast_tool_event(
            ws_hub,
            tool="mm_create_item",
            npc_id=npc_id,
            summary=f"New item: {name}",
        )
        return {"uuid": uuid, "name": name, "entity_type": "Item"}

    @mcp.tool(name="mm_create_location")
    async def mm_create_location(
        npc_id: str,
        name: str,
        summary: str = "",
    ) -> dict:
        """Discover or build a new location in the world."""
        await _check_tool_access(npc_id, "mm_create_location")
        from memento.tools.kg import create_entity as _cen
        create_entity = _cen.func
        uuid = await asyncio.to_thread(create_entity, name, "Location", summary)
        return {"uuid": uuid, "name": name, "entity_type": "Location"}

    @mcp.tool(name="mm_move_to")
    async def mm_move_to(
        npc_id: str,
        entity_name: str,
        destination: str,
    ) -> dict:
        """ACTUALLY move to a different location in the world. This is the mutation — calling this tool is what makes the move happen and updates the map. Your NPC will not move unless you call this (or mm_move_within for same-room moves). Narrating a move in text does nothing; you must call this tool."""
        await _check_tool_access(npc_id, "mm_move_to")
        from memento.tools.kg import create_edge as _ce_tool
        create_edge = _ce_tool.func
        result = await asyncio.to_thread(
            create_edge, entity_name, destination, "LOCATED_IN",
            f"{entity_name} moved to {destination}",
        )
        # Update agent controller tracking
        try:
            from memento.agent_controller import get_agent_controller
            controller = get_agent_controller()
            controller.move_npc_agent(entity_name, to_location=destination)
        except Exception:
            pass  # Non-fatal — agent may not exist
        await broadcast_tool_event(
            ws_hub,
            tool="mm_move_to",
            npc_id=npc_id,
            summary=f"{entity_name} moved to {destination}",
        )
        return {"result": result, "entity": entity_name, "destination": destination}

    @mcp.tool(name="mm_move_within")
    async def mm_move_within(npc_id: str, target_x: int, target_y: int) -> dict:
        """ACTUALLY move your NPC to a new position within the current room. This is the mutation — calling this tool is what updates the map and fires the move badge. Use to approach a player, back away, patrol, or reposition. Max 5 tiles per move (Manhattan distance). Narrating a move in text does nothing — your NPC will not move unless you call this tool. mm_check_plausibility is a dry run and does NOT substitute for this."""
        # No capability gate: HTTP route does not call check_tool_access either.
        from memento.tools.movement import move_within_room
        result = await move_within_room(npc_id, target_x, target_y)
        if result.get("success"):
            if ws_hub and result.get("location"):
                pos_msg = {"type": "position_update", "entity_id": result.get("npc_uuid", ""),
                           "x": target_x, "y": target_y}
                await ws_hub.broadcast_to_location(result["location"], pos_msg)
            await broadcast_tool_event(
                ws_hub, tool="mm_move_within", npc_id=npc_id,
                summary=f"{result['npc_name']} moved to ({target_x},{target_y})",
            )
        return {k: v for k, v in result.items() if k not in ("npc_name", "npc_uuid", "location")}

    @mcp.tool(name="mm_inventory_transfer")
    async def mm_inventory_transfer(
        npc_id: str,
        item_id: str,
        from_entity: str,
        to_entity: str,
        quantity: int = 1,
    ) -> dict:
        """Transfer an item from one entity to another. Use for trades, gifts, theft resolution."""
        await _check_tool_access(npc_id, "mm_inventory_transfer")

        from memento.bonfires_client import get_client
        from memento.tools import chain as _chain

        client = await asyncio.to_thread(get_client)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        # Expire CARRIES from old owner
        try:
            edges = await asyncio.to_thread(
                client.kg.get_edges, from_entity,
                direction="outgoing", edge_type="CARRIES",
            )
            for edge in edges:
                target = edge.get("target", {})
                tid = target.get("uuid", target.get("id", ""))
                if tid == item_id and not (edge.get("expired_at") or edge.get("invalid_at")):
                    edge_uuid = edge.get("uuid", edge.get("id", ""))
                    if edge_uuid:
                        await asyncio.to_thread(
                            client.kg.update_edge, edge_uuid, {"expired_at": now},
                        )
                        break
        except Exception:
            pass

        # Create CARRIES to new owner
        await asyncio.to_thread(
            client.kg.create_edge,
            to_entity, item_id, "CARRIES",
            "Traded item",
        )

        # Chain update
        _chain.transfer_item(item_id, to_entity)

        await broadcast_tool_event(
            ws_hub,
            tool="mm_inventory_transfer",
            npc_id=npc_id,
            summary=f"Item traded (id: {item_id[:8]}...)",
        )
        return {
            "status": "ok",
            "item_id": item_id,
            "from": from_entity,
            "to": to_entity,
        }

    @mcp.tool(name="mm_send_gossip")
    async def mm_send_gossip(
        npc_id: str,
        from_npc: str,
        to_npc: str,
        message: str,
    ) -> dict:
        """Send a message to another NPC. Creates organic information flow between NPCs."""
        # No capability gate: HTTP route does not call check_tool_access either.
        from memento.tools.kg import remember_event as _remember_tool
        _remember = _remember_tool.func
        summary = f"{from_npc} told {to_npc}: {message}"
        result = await asyncio.to_thread(_remember, summary)
        return {"result": result, "from": from_npc, "to": to_npc}

    @mcp.tool(name="mm_npc_memory")
    async def mm_npc_memory(npc_id: str, summary: str) -> dict:
        """Record a first-person memory of a scene from your perspective."""
        await _check_tool_access(npc_id, "mm_npc_memory")
        from memento.tools.kg import remember_event as _remember_tool
        _remember = _remember_tool.func
        result = await asyncio.to_thread(_remember, summary)
        return {"result": result}


# ── Factory ─────────────────────────────────────────────────────────────────

def build_mcp_app(
    ws_hub: "WebSocketHub",
    bridge: "MatrixBridge | None",
    narrator_registry: "dict[str, str]",
) -> "ASGIApp":
    """Build the streamable-HTTP MCP ASGI app for the memento engine.

    The returned app is meant to be mounted at /mcp on the gateway FastAPI app.
    All captured refs (ws_hub, bridge, narrator_registry) are closed over by
    the per-category registration helpers so tool handlers can reach them
    without a FastAPI Request context.

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

    _register_read_tools(mcp, ws_hub, bridge, narrator_registry)
    _register_mutation_tools(mcp, ws_hub)

    logger.info("mcp_server: built FastMCP('memento-engine') scaffold")

    raw_app = mcp.streamable_http_app()
    return _BearerAuthMiddleware(raw_app)
