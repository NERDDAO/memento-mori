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
    bridge: "MatrixBridge",
    narrator_registry: "dict[str, str]",
) -> "ASGIApp":
    """Build the streamable-HTTP MCP ASGI app for the memento engine.

    The returned app is meant to be mounted at /mcp on the gateway FastAPI app.
    All captured refs (ws_hub, bridge, narrator_registry) are closed over so
    tool handlers can reach them without a FastAPI Request context.
    """
    mcp = FastMCP("memento-engine")

    # Tool handlers are registered in subsequent tasks (task-4 through task-7).
    # When adding handlers, define them as nested functions inside this factory
    # so they capture ``ws_hub`` / ``bridge`` / ``narrator_registry`` by closure,
    # then decorate with ``@mcp.tool()``. Handlers should call
    # ``await _check_tool_access(npc_id, "<tool-name>")`` before doing any work.
    _ = (ws_hub, bridge, narrator_registry)  # silence unused until task-4

    logger.info("mcp_server: built FastMCP('memento-engine') scaffold")

    raw_app = mcp.streamable_http_app()
    return _BearerAuthMiddleware(raw_app)
