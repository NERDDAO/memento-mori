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

import os
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

from gateway.engine_auth import check_tool_access
from gateway.log import get_logger

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

logger = get_logger(__name__)


# ── Auth helper ─────────────────────────────────────────────────────────────

async def _check_tool_access(npc_id: str, tool_name: str) -> None:
    """Wrap ``gateway.engine_auth.check_tool_access`` for MCP tool handlers.

    The upstream helper raises ``fastapi.HTTPException`` on 403, which is
    meaningless to an MCP client. We catch that and re-raise something the
    MCP runtime can surface as a proper tool error.

    TODO(task-4+): convert to McpError when SDK path is confirmed.
    For now we raise a plain RuntimeError with a clear message so the
    first batch of ported tool handlers has something to rely on; a later
    task will swap this to ``mcp.shared.exceptions.McpError`` with a
    structured ``ErrorData`` payload once the exact surfacing behavior is
    verified end-to-end against bonfires-ai.
    """
    try:
        await check_tool_access(npc_id, tool_name)
    except Exception as exc:  # noqa: BLE001 — re-raised below
        # HTTPException has .status_code / .detail; generic exceptions just str().
        status = getattr(exc, "status_code", None)
        detail = getattr(exc, "detail", None) or str(exc)
        if status == 403:
            raise RuntimeError(
                f"capability_missing: npc={npc_id!r} tool={tool_name!r} detail={detail}"
            ) from exc
        raise


# ── Bearer auth ASGI middleware ─────────────────────────────────────────────

def _unauthorized_response_factory(message: str):
    """Build a minimal 401 Starlette ``Response`` without importing at module load."""
    from starlette.responses import JSONResponse

    return JSONResponse({"error": "unauthorized", "detail": message}, status_code=401)


class _BearerAuthMiddleware:
    """ASGI middleware that enforces the engine bearer token on /mcp.

    We duplicate the token-compare logic from ``verify_engine_token``
    rather than calling it directly because that helper is a FastAPI
    ``Depends`` — it expects a FastAPI request/dependency context, not a
    raw ASGI scope. The check here intentionally mirrors the upstream
    behavior: empty ``ENGINE_API_TOKEN`` disables auth (dev mode).
    """

    def __init__(self, app: "ASGIApp") -> None:
        self.app = app

    async def __call__(self, scope: "Scope", receive: "Receive", send: "Send") -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        expected = os.getenv("ENGINE_API_TOKEN", "")
        if not expected:
            # Dev mode — no token configured, passthrough.
            await self.app(scope, receive, send)
            return

        # Pull Authorization header from raw ASGI scope.
        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != expected:
            response = _unauthorized_response_factory("Invalid or missing engine token")
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


# ── Factory ─────────────────────────────────────────────────────────────────

def build_mcp_app(ws_hub, bridge, narrator_registry) -> "ASGIApp":
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
