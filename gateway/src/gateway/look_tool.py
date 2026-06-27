"""Gateway-hosted ``mm_look`` MCP tool — the first "expressive ECS" effect.

``mm_look`` is the persona ReAct loop's accretive look: it resolves the caller's
current room, advances that room's reveal-state via Plan 1's
``reveal_or_deepen`` (reveal the next salient thing, else deepen the shallowest
seen thing, else exhausted), broadcasts an *incremental* ``room_draw`` WS delta
(the client ADDS the new glyph — no redraw), and returns a narration summary
into the agent's trajectory so the same turn narrates it.

Unlike the MOVE/ATTACK/TAKE tools (``cxn_tools.py``), ``mm_look`` does NOT run
the ``EffectExecutor`` and produces NO ``StateUpdate`` — it returns its own
plain dict, so it never reaches the ``mm_act`` ``assert update is not None``
branch.  Identity comes from the JWT ContextVar (``_check_tool_access``); the
tool takes no parameters (you "look around HERE").  Every failure mode degrades
to a narration dict — ``mm_look`` never raises into the ReAct turn.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from memento.opening.reveal import DEFAULT_MAX_DEPTH, RevealDelta, reveal_or_deepen

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcp.server.fastmcp import FastMCP

    from memento.state.repository import StateRepository
    from gateway.ws import WebSocketHub

logger = logging.getLogger(__name__)


def _summarize(delta: RevealDelta) -> str:
    """A short narration hint for the ReAct trajectory (the LLM rewrites it)."""
    name = delta.entity["name"] if delta.entity else None
    if delta.kind == "revealed":
        return f"You notice {name}."
    if delta.kind == "deepened":
        return f"You look more closely at {name}."
    return "You have taken in all there is to see here."


async def _broadcast_room_draw(
    ws_hub: "WebSocketHub | None", location_uuid: str, delta: RevealDelta
) -> None:
    """Push the incremental ``room_draw`` delta to players in the room.

    On ``revealed`` the client ADDS the new glyph; on ``deepened`` no glyph
    changes (depth-only). ``exhausted`` draws nothing. Best-effort — a hub
    failure is logged and swallowed so the look still returns its narration.
    """
    if ws_hub is None or delta.kind == "exhausted":
        return
    try:
        await ws_hub.broadcast_to_location(
            location_uuid,
            {
                "type": "room_draw",
                "kind": delta.kind,
                "entity": delta.entity,
                "depth": delta.depth,
                "location": location_uuid,
            },
        )
    except Exception:  # surfacing is best-effort, never breaks the turn
        logger.warning(
            "room_draw broadcast failed for %s", location_uuid, exc_info=True
        )


def register_look_tool(
    mcp: "FastMCP",
    ws_hub: "WebSocketHub | None",
    repo: "StateRepository",
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> None:
    """Register the ``mm_look`` MCP tool on ``mcp``.

    Closes over ``repo`` (the room ECS) and ``ws_hub`` (the draw channel), the
    same injection pattern as ``register_cxn_tools``.
    """
    from gateway.mcp_server import _check_tool_access  # late import (auth surface)

    @mcp.tool(name="mm_look")
    async def mm_look() -> dict:
        """Look around the current room. Reveals the next notable thing, or —
        once everything is surfaced — looks more closely at something already
        seen. Re-looking adds detail; it never starts over."""
        actor_id = await _check_tool_access("mm_look")
        actor = await repo.get_entity(actor_id)
        location_uuid = actor.get("location_uuid") if actor else None
        if not location_uuid:
            # No room to look at — degrade, never raise into the turn.
            return {
                "kind": "exhausted",
                "entity": None,
                "depth": 0,
                "summary": "There is nothing here to see.",
            }
        delta = await reveal_or_deepen(repo, location_uuid, max_depth=max_depth)
        await _broadcast_room_draw(ws_hub, location_uuid, delta)
        return {
            "kind": delta.kind,
            "entity": delta.entity,
            "depth": delta.depth,
            "summary": _summarize(delta),
        }


async def seed_opening_room(repo: Any) -> None:
    """Seed the pre-authored Deep Roads room into the cxn repo as reveal-tracked
    ECS entities (``reveal_level=0`` + ``salience``), so the gateway-hosted
    ``mm_look`` has a room to read and advance. Gated on ``OPENING_ROOM_SEED``
    and wrapped non-fatal by the caller — a seed failure must not crash boot.
    """
    from memento.opening.deep_roads import deep_roads_seed

    from memento.opening.reveal import seed_room_ecs

    await seed_room_ecs(repo, deep_roads_seed())
    logger.info("seeded opening room ECS (Deep Roads) into the cxn repo")
