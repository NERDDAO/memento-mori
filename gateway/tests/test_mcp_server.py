"""Tests for the MCP server — tool registration, JWT auth, handler invocation.

Covers:
  T1  tool registration count (36 tools)
  T2  JWT auth rejects missing token (401)
  T3  JWT auth rejects invalid token (401)
  T4  JWT auth accepts valid signed token
  T5  read tool invocation (mm_get_world_time) with ContextVar identity
  T6  mutation tool invocation (mm_create_npc) + broadcast, identity from JWT
  T7  tool access gating (capability_missing raised from check_tool_access)
  T8  bridge-None guard on mm_trigger_npc (capability_unavailable)
  T9  missing identity raises identity_missing when no JWT context set
"""

from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from gateway.mcp_server import build_mcp_app

_TEST_JWT_SECRET = "unit-test-secret-do-not-reuse"
_TEST_ENTITY_ID = "test-entity-uuid-1234"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _jwt_env(monkeypatch):
    """Every test runs with a known JWT_SECRET so sign/validate work."""
    monkeypatch.setenv("JWT_SECRET", _TEST_JWT_SECRET)


@pytest.fixture()
def test_jwt():
    """Sign a valid player JWT the tests can pass in headers."""
    from gateway.engine_auth import sign_jwt
    return sign_jwt(_TEST_ENTITY_ID, type="player", ttl_seconds=3600)


@pytest.fixture()
def mock_ws_hub():
    hub = AsyncMock()
    hub.broadcast_to_location = AsyncMock()
    return hub


@pytest.fixture()
def mcp_app(mock_ws_hub):
    """Build the full MCP ASGI app including the JWT middleware."""
    return build_mcp_app(ws_hub=mock_ws_hub, bridge=None, narrator_registry={})


def _get_fastmcp(mock_ws_hub):
    """Build a bare FastMCP instance (no auth middleware) for tool introspection
    and direct handler invocation. Tests that call tools directly do so via the
    ContextVar rather than the Bearer middleware.
    """
    from mcp.server.fastmcp import FastMCP

    from gateway.mcp_server import (
        _register_combat_narrative_tools,
        _register_design_tools,
        _register_mutation_tools,
        _register_read_tools,
    )

    mcp = FastMCP("memento-engine")
    _register_read_tools(mcp)
    _register_mutation_tools(mcp, mock_ws_hub)
    _register_combat_narrative_tools(mcp, mock_ws_hub, None)
    _register_design_tools(mcp)
    return mcp


def _with_identity(entity_id: str = _TEST_ENTITY_ID):
    """Context manager that sets the ContextVar identity so direct handler
    calls bypass the middleware but still resolve an entity id.
    """
    from contextlib import contextmanager
    from gateway.mcp_server import _current_identity

    @contextmanager
    def _cm():
        token = _current_identity.set(entity_id)
        try:
            yield
        finally:
            _current_identity.reset(token)

    return _cm()


def _extract_result(call_tool_result: list) -> dict:
    """Extract the JSON dict from FastMCP call_tool's TextContent list."""
    text = call_tool_result[0].text
    return json.loads(text)


# ---------------------------------------------------------------------------
# T1 — Tool registration count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_registration_count(mock_ws_hub):
    """All 36 engine tools should be registered on the FastMCP instance."""
    mcp = _get_fastmcp(mock_ws_hub)
    tools = await mcp.list_tools()
    assert len(tools) == 36, (
        f"Expected 36 tools, got {len(tools)}: "
        f"{sorted(t.name for t in tools)}"
    )


# ---------------------------------------------------------------------------
# T2 — JWT auth rejects missing token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jwt_auth_rejects_missing_token(mcp_app):
    """Request without Authorization header should get 401 + WWW-Authenticate."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mcp_app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/mcp")
        assert resp.status_code == 401
        assert resp.headers.get("www-authenticate") == 'Bearer realm="memento-engine"'


# ---------------------------------------------------------------------------
# T3 — JWT auth rejects invalid token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jwt_auth_rejects_invalid_token(mcp_app):
    """Request with a malformed Bearer token should also get 401."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mcp_app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get(
            "/mcp",
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# T4 — JWT auth accepts valid signed token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jwt_auth_accepts_valid_token(mcp_app, test_jwt):
    """Request with a validly-signed JWT should pass the auth layer."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mcp_app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        resp = await client.get(
            "/mcp",
            headers={"Authorization": f"Bearer {test_jwt}"},
        )
        # The inner MCP app may return 405 for a plain GET — the
        # point is it passes the auth layer.
        assert resp.status_code != 401


# ---------------------------------------------------------------------------
# T5 — Read tool invocation with ContextVar identity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_tool_mm_get_world_time(mock_ws_hub):
    """mm_get_world_time should resolve identity from ContextVar and return display dict."""
    mcp = _get_fastmcp(mock_ws_hub)

    display = {
        "moon_phase": "full",
        "date": "1st of Harvest",
        "time_of_day": "dusk",
        "season": "autumn",
    }
    fake_time = SimpleNamespace(to_display=lambda: display)

    memento_tools_time = types.ModuleType("memento.tools.time")
    memento_tools_time.get_current_time = lambda: fake_time
    with patch.dict(sys.modules, {"memento.tools.time": memento_tools_time}), \
         patch("gateway.mcp_server.check_tool_access", new_callable=AsyncMock), \
         _with_identity():
        result = await mcp.call_tool("mm_get_world_time", {})

    data = _extract_result(result)
    assert data["moon_phase"] == "full"
    assert data["season"] == "autumn"


# ---------------------------------------------------------------------------
# T6 — Mutation tool invocation + broadcast with JWT identity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mutation_tool_mm_create_npc(mock_ws_hub):
    """mm_create_npc should create entity, broadcast via ws_hub, and return expected shape."""
    mcp = _get_fastmcp(mock_ws_hub)

    fake_create_entity = MagicMock(return_value="uuid-1234")
    fake_create_edge = MagicMock()

    kg_mod = types.ModuleType("memento.tools.kg")
    ce = MagicMock()
    ce.func = fake_create_entity
    ced = MagicMock()
    ced.func = fake_create_edge
    kg_mod.create_entity = ce
    kg_mod.create_edge = ced

    async def _to_thread(fn, *a, **kw):
        return fn(*a, **kw)

    with patch.dict(sys.modules, {"memento.tools.kg": kg_mod}), \
         patch("gateway.mcp_server.check_tool_access", new_callable=AsyncMock), \
         patch("gateway.mcp_server.broadcast_tool_event", new_callable=AsyncMock) as mock_broadcast, \
         patch("gateway.mcp_server.asyncio.to_thread", side_effect=_to_thread), \
         _with_identity():
        result = await mcp.call_tool(
            "mm_create_npc",
            {"name": "Gruk", "summary": "An orc"},
        )

    data = _extract_result(result)
    assert data["uuid"] == "uuid-1234"
    assert data["name"] == "Gruk"
    assert data["entity_type"] == "NPC"

    fake_create_entity.assert_called_once_with("Gruk", "NPC", "An orc")
    mock_broadcast.assert_awaited_once()
    # Identity passed to broadcast should match the ContextVar
    call_kwargs = mock_broadcast.call_args.kwargs
    assert call_kwargs["npc_id"] == _TEST_ENTITY_ID
    assert call_kwargs["tool"] == "mm_create_npc"


# ---------------------------------------------------------------------------
# T7 — Tool access gating (capability_missing)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_access_gating(mock_ws_hub):
    """Gated tool should raise ToolError with capability_missing prefix when
    the upstream check_tool_access raises HTTPException(403)."""
    from mcp.server.fastmcp.exceptions import ToolError
    import fastapi

    mcp = _get_fastmcp(mock_ws_hub)

    with patch(
        "gateway.mcp_server.check_tool_access",
        new_callable=AsyncMock,
        side_effect=fastapi.HTTPException(status_code=403, detail="no capability"),
    ), _with_identity():
        with pytest.raises(ToolError, match="capability_missing"):
            await mcp.call_tool(
                "mm_create_npc",
                {"name": "X", "summary": ""},
            )


# ---------------------------------------------------------------------------
# T8 — Bridge-None guard on mm_trigger_npc
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bridge_none_guard_mm_trigger_npc(mock_ws_hub):
    """mm_trigger_npc with bridge=None should raise capability_unavailable."""
    from mcp.server.fastmcp.exceptions import ToolError

    mcp = _get_fastmcp(mock_ws_hub)  # bridge=None by default

    with patch("gateway.mcp_server.check_tool_access", new_callable=AsyncMock), \
         _with_identity():
        with pytest.raises(ToolError, match="capability_unavailable"):
            await mcp.call_tool(
                "mm_trigger_npc",
                {"npc_name": "Gruk"},
            )


# ---------------------------------------------------------------------------
# T9 — Missing identity raises identity_missing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_identity_missing_raises(mock_ws_hub):
    """A gated tool called without any JWT context should raise
    identity_missing — not fall back to empty string."""
    from mcp.server.fastmcp.exceptions import ToolError

    mcp = _get_fastmcp(mock_ws_hub)

    # No _with_identity() — ContextVar stays unset.
    with pytest.raises(ToolError, match="identity_missing"):
        await mcp.call_tool("mm_get_state", {"entity_name": "x"})
