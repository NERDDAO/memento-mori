"""C6 — McpToolBridge: register one MCP tool per construction.

This module is the gateway-side seam of the construction control system
(spec §7.1). It iterates ``CONSTRUCTION_REGISTRY`` and registers each
``CxnDef`` as an MCP tool on the existing ``FastMCP("memento-engine")``
instance, under the cxn's ``mcp_tool_name`` (``mm_move`` / ``mm_attack`` /
``mm_take``).

Day-1 contract (UUID args only, no comprehension, no NLP):

  * ``agent`` is NEVER a tool parameter — it comes from the caller's JWT
    ``sub`` claim, read via ``_check_tool_access`` exactly as every existing
    mutation handler does today.
  * Every other role is a UUID argument (``destination`` / ``patient`` /
    ``instrument``).
  * The ``location`` role is the agent's current room, resolved from the
    agent doc (one read). For MOVE the ``location`` role IS the destination
    room (per the MOVE ``CxnDef``), so it is bound from the ``destination``
    arg directly; for ATTACK/TAKE it is the agent's current room.

Each handler:
  1. ``await _check_tool_access(tool_name)`` → returns the acting agent UUID
     (the JWT identity) and runs the capability gate (§7.5 kit edit makes the
     three tool names pass for NPC / Player).
  2. Builds a ``MatchedCxn`` directly (cxn + ``bound_roles`` from agent +
     UUID args + resolved location).
  3. Runs ``EffectExecutor.execute(cxn, caller_id=agent, bindings=...)``.
  4. Calls ``broadcast_tool_event(...)`` to keep the live WS feed intact.
  5. Returns the ``StateUpdate`` dict.

On ``ConstructionError`` the handler returns
``{"status": "rejected", "cause": <reason>}`` with no further state change.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from memento.cxn.definitions import CONSTRUCTION_REGISTRY
from memento.cxn.executor import EffectExecutor
from memento.cxn.types import ConstructionError, CxnDef, MatchedCxn

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcp.server.fastmcp import FastMCP

    from memento.memory.client import MemoryClient
    from memento.state.chain_mirror import ChainMirror
    from memento.state.repository import StateRepository
    from gateway.ws import WebSocketHub


async def _resolve_location(repo: "StateRepository", agent_id: str) -> str | None:
    """Return the agent's current room UUID, or None if the agent has no room."""
    agent_doc = await repo.get_entity(agent_id)
    if agent_doc is None:
        return None
    return agent_doc.get("location_uuid")


def register_cxn_tools(
    mcp: "FastMCP",
    ws_hub: "WebSocketHub | None",
    repo: "StateRepository",
    mirror: "ChainMirror",
    memory: "MemoryClient",
) -> None:
    """Register the construction MCP tools on ``mcp``.

    One ``@mcp.tool`` is registered per cxn in ``CONSTRUCTION_REGISTRY``,
    under its ``mcp_tool_name`` with the exact §7.1 UUID parameters. All
    handlers close over a single shared ``EffectExecutor`` built from the
    injected ports (``repo`` / ``memory`` / ``mirror``).
    """
    # Late import so this module imports cleanly even if the gateway auth
    # surface (FastMCP / JWT middleware) is unavailable in a bare unit test.
    from gateway.engine_events import broadcast_tool_event
    from gateway.mcp_server import _check_tool_access

    executor = EffectExecutor(repo=repo, memory=memory, chain=mirror)

    move_cxn: CxnDef = CONSTRUCTION_REGISTRY["MOVE"]
    attack_cxn: CxnDef = CONSTRUCTION_REGISTRY["ATTACK"]
    take_cxn: CxnDef = CONSTRUCTION_REGISTRY["TAKE"]

    async def _run(
        cxn: CxnDef,
        agent_id: str,
        bound_roles: dict[str, str],
        summary: str,
    ) -> dict[str, Any]:
        """Build the MatchedCxn, execute, broadcast, and return the StateUpdate.

        ``bound_roles`` holds the resolved UUID role bindings (agent + UUID
        args + location). The executor re-derives agent/location itself, so
        the MatchedCxn is the authoritative record of what was bound.
        """
        matched = MatchedCxn(cxn=cxn, bound_roles=bound_roles)
        try:
            update = await executor.execute(
                matched["cxn"],
                caller_id=agent_id,
                bindings=matched["bound_roles"],
            )
        except ConstructionError as exc:
            # No state change escapes a ConstructionError (Phase 1/2 are
            # all-or-nothing). Surface the stable reason string to the caller.
            return {"status": "rejected", "cause": str(exc)}

        await broadcast_tool_event(
            ws_hub,
            tool=cxn["mcp_tool_name"],
            npc_id=agent_id,
            summary=summary,
        )
        return update

    @mcp.tool(name=move_cxn["mcp_tool_name"])
    async def mm_move(destination: str) -> dict:
        """Move the agent character to an adjacent room (by destination UUID)."""
        agent_id = await _check_tool_access(move_cxn["mcp_tool_name"])
        # MOVE: the `location` role IS the destination room (per the CxnDef).
        bound_roles = {"agent": agent_id, "location": destination}
        return await _run(
            move_cxn,
            agent_id,
            bound_roles,
            summary=f"moved to {destination[:8]}...",
        )

    @mcp.tool(name=attack_cxn["mcp_tool_name"])
    async def mm_attack(patient: str, instrument: str | None = None) -> dict:
        """Attack a target character (patient UUID); instrument is the weapon UUID."""
        agent_id = await _check_tool_access(attack_cxn["mcp_tool_name"])
        location = await _resolve_location(repo, agent_id)
        bound_roles: dict[str, str] = {"agent": agent_id, "patient": patient}
        if instrument is not None:
            bound_roles["instrument"] = instrument
        if location is not None:
            bound_roles["location"] = location
        return await _run(
            attack_cxn,
            agent_id,
            bound_roles,
            summary=f"attacked {patient[:8]}...",
        )

    @mcp.tool(name=take_cxn["mcp_tool_name"])
    async def mm_take(patient: str) -> dict:
        """Pick up an item (patient UUID) from the current room into the inventory."""
        agent_id = await _check_tool_access(take_cxn["mcp_tool_name"])
        location = await _resolve_location(repo, agent_id)
        bound_roles: dict[str, str] = {"agent": agent_id, "patient": patient}
        if location is not None:
            bound_roles["location"] = location
        return await _run(
            take_cxn,
            agent_id,
            bound_roles,
            summary=f"took {patient[:8]}...",
        )
