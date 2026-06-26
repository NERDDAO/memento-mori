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
  * The ``location`` role is filled by the executor (the single source of
    truth) from the caller's current room — handlers do NOT pre-read it. For
    MOVE the ``location`` role IS the destination room (per the MOVE
    ``CxnDef``), so it is bound from the ``destination`` arg directly; for
    ATTACK/TAKE the executor fills it from the agent's ``location_uuid``.

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

M2 addition — ``register_mm_act``:
  Registers the ``mm_act`` free-text tool.  The agent sends a natural-language
  utterance; ``TurnRouter`` comprehends it via ``ComprehensionClient`` and
  routes to the unchanged Day-1 executor or returns a ``clarify`` outcome.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from memento.cxn.definitions import CONSTRUCTION_REGISTRY
from memento.cxn.executor import DEFAULT_BONFIRE_ID, EffectExecutor
from memento.cxn.types import ConstructionError, CxnDef, MatchedCxn

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcp.server.fastmcp import FastMCP

    from memento.cxn.kernel_client import ComprehensionClient
    from memento.memory.client import MemoryClient
    from memento.state.chain_mirror import ChainMirror
    from memento.state.repository import StateRepository
    from gateway.ws import WebSocketHub


def register_cxn_tools(
    mcp: "FastMCP",
    ws_hub: "WebSocketHub | None",
    repo: "StateRepository",
    mirror: "ChainMirror",
    memory: "MemoryClient",
    bonfire_id: str = DEFAULT_BONFIRE_ID,
) -> "EffectExecutor":
    """Register the construction MCP tools on ``mcp``.

    One ``@mcp.tool`` is registered per cxn in ``CONSTRUCTION_REGISTRY``,
    under its ``mcp_tool_name`` with the exact §7.1 UUID parameters. All
    handlers close over a single shared ``EffectExecutor`` built from the
    injected ports (``repo`` / ``memory`` / ``mirror``).

    Returns the shared ``EffectExecutor`` so callers can wire the HTTP
    tool-exec route to the SAME executor instance (G1 — no divergent fork).
    """
    # Late import so this module imports cleanly even if the gateway auth
    # surface (FastMCP / JWT middleware) is unavailable in a bare unit test.
    from gateway.engine_events import broadcast_tool_event
    from gateway.mcp_server import _check_tool_access

    executor = EffectExecutor(
        repo=repo, memory=memory, chain=mirror, bonfire_id=bonfire_id
    )

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
        # `location` (the agent's current room) is filled by the executor — the
        # single source of truth (I-1/I-8). The handler passes only explicit
        # MCP args, so there is no double get_entity(agent) read here.
        bound_roles: dict[str, str] = {"agent": agent_id, "patient": patient}
        if instrument is not None:
            bound_roles["instrument"] = instrument
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
        # `location` (the agent's current room) is filled by the executor — the
        # single source of truth (I-1/I-8). Handler passes only explicit args.
        bound_roles: dict[str, str] = {"agent": agent_id, "patient": patient}
        return await _run(
            take_cxn,
            agent_id,
            bound_roles,
            summary=f"took {patient[:8]}...",
        )

    return executor


def register_mm_act(
    mcp: "FastMCP",
    ws_hub: "WebSocketHub | None",
    repo: "StateRepository",
    mirror: "ChainMirror",
    memory: "MemoryClient",
    comprehension: "ComprehensionClient",
    bonfire_id: str = "mm-world-v1",
) -> None:
    """Register the ``mm_act`` free-text MCP tool on ``mcp``.

    ``mm_act`` accepts a natural-language utterance, routes it through
    ``TurnRouter`` (comprehend → resolve → execute), and returns one of:
      - ``{"status": "clarify", "message": <player-facing string>}``
      - ``{"status": "rejected", "cause": <reason>}``  (ConstructionError)
      - the raw ``StateUpdate`` dict (on success, after broadcasting)

    The ``ComprehensionClient`` is wired from env in ``build_mcp_app``
    (``HttpComprehensionClient`` when KERNEL_BASE_URL+GM_INTERNAL_TOKEN are set,
    else a ``NullComprehensionClient`` that always returns no-match).
    """
    from gateway.engine_events import broadcast_tool_event
    from gateway.mcp_server import _check_tool_access
    from memento.cxn.constructicon import ConstructiconRegistry
    from memento.cxn.entity_resolver import EntityResolver
    from memento.cxn.turn_router import TurnRouter

    executor = EffectExecutor(
        repo=repo, memory=memory, chain=mirror, bonfire_id=bonfire_id
    )
    constructicon = ConstructiconRegistry()
    resolver = EntityResolver(repo)
    router = TurnRouter(
        comprehension=comprehension,
        constructicon=constructicon,
        resolver=resolver,
        executor=executor,
        bonfire_id=bonfire_id,
    )

    @mcp.tool(name="mm_act")
    async def mm_act(text: str) -> dict[str, Any]:
        """Perform a game action using natural language (free-text utterance).

        The engine comprehends the utterance, resolves entity references from
        the current room context, and executes the matching construction.
        Returns a clarify prompt when the action cannot be understood or the
        target cannot be found.
        """
        actor_id = await _check_tool_access("mm_act")
        try:
            outcome = await router.handle(text, actor_id)
        except ConstructionError as exc:
            # Guard or transactional failure — store is untouched (all-or-nothing).
            return {"status": "rejected", "cause": str(exc)}

        if outcome["status"] == "clarify":
            return {"status": "clarify", "message": outcome["message"]}

        # "executed" — broadcast the event and return the StateUpdate
        await broadcast_tool_event(
            ws_hub,
            tool="mm_act",
            npc_id=actor_id,
            summary=f"acted: {text[:40]}",
        )
        update = outcome["update"]
        assert update is not None, "executor path must produce a StateUpdate"
        return update
