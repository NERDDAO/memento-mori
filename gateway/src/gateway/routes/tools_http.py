"""HTTP tool-exec routes: POST /v1/tools/{tool} + POST /v1/agents/{id}/activation.

G1 — gateway inbound HTTP tool-exec route.

These routes re-expose the contract the bonfires agent-runtime
``CxnGatewayClient`` already speaks, alongside ``/mcp`` (which is NOT
touched). They let a GM-voiced NPC self-execute ``mm_move`` (and other
construction tools) over HTTP, delegating to the SAME ``EffectExecutor``
instance that the MCP handlers use — no divergent fork.

Auth contract (mirrors existing gateway style):
  - Bearer JWT required on every request; ``validate_jwt`` → ``sub`` claim.
  - Missing/invalid JWT → 401 HTTPException at the ``Depends`` boundary.
  - Capability miss → 403 (re-raised from ``check_tool_access``).
  - Unknown tool name → 404.
  - ``ConstructionError`` → 200 with ``{"status":"rejected","cause":...}``
    (already handled by the shared ``_run`` helper in ``cxn_tools``).

Executor sharing:
  The ``EffectExecutor`` and ``InMemoryStateRepository`` built inside
  ``build_mcp_app`` are stored on ``app.state.cxn_executor`` and
  ``app.state.cxn_repo`` by the outer FastAPI lifespan (``app.py``).
  Routes access them via FastAPI's ``Request.app.state`` — the same dict
  the MCP handlers close over — so state mutations are visible across both
  transports.

Tool → cxn lookup:
  The ``CONSTRUCTION_REGISTRY`` (``memento.cxn.definitions``) maps cxn
  names → ``CxnDef``. This module builds a reverse lookup from
  ``CxnDef.mcp_tool_name`` → ``CxnDef`` at import time. The ``mm_move``
  handler is the proof-of-concept; any cxn in the registry whose
  ``mcp_tool_name`` matches the URL ``{tool}`` segment will be dispatched
  automatically — a general extension point with no per-tool hardcoding.

Binding strategy for ``bound_roles``:
  - ``agent`` is ALWAYS the JWT ``sub`` claim (never a request body field).
  - For MOVE: body field ``destination`` fills the ``location`` role.
  - For ATTACK: body fields ``patient`` (required) and ``instrument``
    (optional) fill those roles. The executor fills ``location`` from the
    agent's current room (single source of truth, §I-1/I-8).
  - For TAKE: body field ``patient`` fills the patient role.
  - The general mapper iterates ``cxn["semantic_roles"]`` and fills from
    the request body where a matching key is present (``agent`` always
    from JWT). MOVE is a special case: the body key ``destination`` maps
    to the ``location`` role.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from gateway.engine_auth import check_tool_access, validate_jwt
from gateway.engine_events import broadcast_tool_event

router = APIRouter()

_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# JWT Depends verifier
# ---------------------------------------------------------------------------


async def require_jwt(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """Extract and verify the Bearer JWT; return the ``sub`` claim (entity id).

    Raises 401 if the token is missing, malformed, or expired.
    """
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "detail": "Missing Bearer token"},
            headers={"WWW-Authenticate": 'Bearer realm="memento-engine"'},
        )
    claims = validate_jwt(credentials.credentials)
    if not claims:
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "detail": "Invalid or expired JWT"},
            headers={"WWW-Authenticate": 'Bearer realm="memento-engine"'},
        )
    return claims["sub"]


# ---------------------------------------------------------------------------
# Tool → CxnDef lookup (built at import time from CONSTRUCTION_REGISTRY)
# ---------------------------------------------------------------------------


def _build_tool_map() -> dict[str, Any]:
    """Build a reverse map from mcp_tool_name → CxnDef."""
    from memento.cxn.definitions import CONSTRUCTION_REGISTRY

    return {
        cxn["mcp_tool_name"]: cxn
        for cxn in CONSTRUCTION_REGISTRY.values()
        if cxn.get("mcp_tool_name")
    }


_TOOL_MAP: dict[str, Any] = _build_tool_map()


# ---------------------------------------------------------------------------
# Role binding: body dict → bound_roles for EffectExecutor
# ---------------------------------------------------------------------------

# MOVE is a special case: the caller sends ``destination`` but the CxnDef
# uses the role name ``location``. This alias map translates body keys to
# semantic role names.
_BODY_KEY_TO_ROLE: dict[str, str] = {
    "destination": "location",  # MOVE cxn
    "patient": "patient",
    "instrument": "instrument",
}


def _build_bound_roles(
    cxn: Any,
    entity_id: str,
    body: dict[str, Any],
) -> dict[str, str]:
    """Build the ``bound_roles`` dict from the entity id + request body.

    ``agent`` is always filled from the JWT ``sub``. Other roles are
    filled from the body, applying the alias map where needed.
    The executor fills any remaining roles (e.g. ``location`` for ATTACK/TAKE)
    from the agent's current room — the single source of truth.
    """
    bound: dict[str, str] = {"agent": entity_id}
    for role in cxn.get("semantic_roles", []):
        if role == "agent":
            continue
        # Check body for the role name directly, or via alias
        if role in body:
            val = body[role]
            if val is not None:
                bound[role] = str(val)
        else:
            # Check aliases: e.g. body["destination"] → role "location"
            for body_key, mapped_role in _BODY_KEY_TO_ROLE.items():
                if mapped_role == role and body_key in body:
                    val = body[body_key]
                    if val is not None:
                        bound[role] = str(val)
                    break
    return bound


# ---------------------------------------------------------------------------
# POST /v1/tools/{tool}
# ---------------------------------------------------------------------------


@router.post("/v1/tools/{tool}")
async def exec_tool(
    tool: str,
    request: Request,
    entity_id: str = Depends(require_jwt),
) -> dict[str, Any]:
    """Execute a construction tool as the calling entity.

    Looks up the ``CxnDef`` by ``tool`` name, verifies capability access,
    builds ``bound_roles`` from the request body, and dispatches through
    the shared ``EffectExecutor``. Returns the ``StateUpdate`` dict on
    success or ``{"status":"rejected","cause":...}`` on ``ConstructionError``
    (both are 200 — rejection is a domain outcome, not an HTTP error).
    """
    cxn = _TOOL_MAP.get(tool)
    if cxn is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "unknown_tool", "tool": tool},
        )

    # Capability gate (raises 403 on failure)
    await check_tool_access(entity_id, tool)

    # Parse request body
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        body = {}

    bound_roles = _build_bound_roles(cxn, entity_id, body)

    # Dispatch through the shared executor (same instance as MCP handlers)
    executor = request.app.state.cxn_executor
    ws_hub = getattr(request.app.state, "ws_hub", None)

    from memento.cxn.types import ConstructionError, MatchedCxn

    matched = MatchedCxn(cxn=cxn, bound_roles=bound_roles)
    try:
        update = await executor.execute(
            matched["cxn"],
            caller_id=entity_id,
            bindings=matched["bound_roles"],
        )
    except ConstructionError as exc:
        return {"status": "rejected", "cause": str(exc)}

    await broadcast_tool_event(
        ws_hub,
        tool=tool,
        npc_id=entity_id,
        summary=f"http:{tool} by {entity_id[:8]}...",
    )
    return update


# ---------------------------------------------------------------------------
# POST /v1/agents/{agent_id}/activation
# ---------------------------------------------------------------------------


@router.post("/v1/agents/{agent_id}/activation")
async def agent_activation(
    agent_id: str,
    request: Request,
    entity_id: str = Depends(require_jwt),
) -> dict[str, Any]:
    """Record/return the set of cxn ids unlocked for an agent.

    Inert in the proof-of-concept under ``in_loop_activation``. Built for
    contract completeness — the bonfires agent-runtime ``CxnGatewayClient``
    calls this after receiving its system prompt to register which
    constructions it has been granted access to in this session.

    Returns ``{"unlocked": [<cxn_id>, ...]}``. The current implementation
    echoes the provided ``cxn_ids`` list back; a future implementation may
    persist them to ``app.state.cxn_repo`` or a dedicated activation store.
    """
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        body = {}

    cxn_ids: list[str] = body.get("cxn_ids", [])
    return {"unlocked": list(cxn_ids)}
