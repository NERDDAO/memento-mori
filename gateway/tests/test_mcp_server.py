"""Tests for the MCP server — tool registration, auth middleware, handler invocation.

Covers:
  T1  tool registration count (36 tools)
  T2  bearer auth rejects missing token
  T3  bearer auth accepts valid token
  T4  bearer auth dev-mode passthrough (empty ENGINE_API_TOKEN)
  T5  read tool invocation (mm_get_world_time)
  T6  mutation tool invocation (mm_create_npc) + broadcast
  T7  tool access gating (capability_missing)
  T8  bridge-None guard on mm_trigger_npc (capability_unavailable)
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from gateway.mcp_server import build_mcp_app


def _extract_result(call_tool_result: list) -> dict:
    """Extract the JSON dict from FastMCP call_tool's TextContent list."""
    text = call_tool_result[0].text
    return json.loads(text)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_ws_hub():
    hub = AsyncMock()
    hub.broadcast_to_location = AsyncMock()
    return hub


@pytest.fixture()
def mcp_app(mock_ws_hub, monkeypatch):
    """Build the MCP ASGI app with mocked deps and auth disabled (dev mode)."""
    monkeypatch.setenv("ENGINE_API_TOKEN", "")
    return build_mcp_app(ws_hub=mock_ws_hub, bridge=None, narrator_registry={})


@pytest.fixture()
def mcp_app_authed(mock_ws_hub, monkeypatch):
    """Build the MCP ASGI app with bearer auth enabled."""
    monkeypatch.setenv("ENGINE_API_TOKEN", "test-token")
    return build_mcp_app(ws_hub=mock_ws_hub, bridge=None, narrator_registry={})


def _get_fastmcp(mock_ws_hub):
    """Build a bare FastMCP instance (no auth middleware) for tool introspection."""
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
# T2 — Bearer auth rejects missing token
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bearer_auth_rejects_missing_token(mcp_app_authed):
    """Request without Authorization header should get 401."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mcp_app_authed),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/mcp")
        assert resp.status_code == 401
        assert resp.headers.get("www-authenticate") == 'Bearer realm="memento-engine"'


# ---------------------------------------------------------------------------
# T3 — Bearer auth accepts valid token
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bearer_auth_accepts_valid_token(mcp_app_authed):
    """Request with correct Bearer token should pass through (not 401)."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mcp_app_authed, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        resp = await client.get(
            "/mcp",
            headers={"Authorization": "Bearer test-token"},
        )
        # The inner MCP app may return 405 for a plain GET — the
        # point is it passes the auth layer.
        assert resp.status_code != 401


# ---------------------------------------------------------------------------
# T4 — Bearer auth dev-mode passthrough
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bearer_auth_dev_mode_passthrough(mcp_app):
    """When ENGINE_API_TOKEN is empty, requests pass without auth."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mcp_app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/mcp")
        assert resp.status_code != 401


# ---------------------------------------------------------------------------
# T5 — Read tool invocation (mm_get_world_time)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_tool_mm_get_world_time(mock_ws_hub):
    """mm_get_world_time should call get_current_time and return its display dict."""
    mcp = _get_fastmcp(mock_ws_hub)

    display = {
        "moon_phase": "full",
        "date": "1st of Harvest",
        "time_of_day": "dusk",
        "season": "autumn",
    }
    fake_time = SimpleNamespace(to_display=lambda: display)

    # The handler does a lazy `from memento.tools.time import get_current_time`
    # — we need to ensure the module exists before patching the attribute.
    import types
    import sys
    memento_tools_time = types.ModuleType("memento.tools.time")
    memento_tools_time.get_current_time = lambda: fake_time
    with patch.dict(sys.modules, {"memento.tools.time": memento_tools_time}), \
         patch("gateway.mcp_server._check_tool_access", new_callable=AsyncMock):
        result = await mcp.call_tool("mm_get_world_time", {"npc_id": "test-npc"})

    data = _extract_result(result)
    assert data["moon_phase"] == "full"
    assert data["season"] == "autumn"


# ---------------------------------------------------------------------------
# T6 — Mutation tool invocation (mm_create_npc) + broadcast
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mutation_tool_mm_create_npc(mock_ws_hub):
    """mm_create_npc should create entity, broadcast, and return expected shape."""
    mcp = _get_fastmcp(mock_ws_hub)

    fake_create_entity = MagicMock(return_value="uuid-1234")
    fake_create_edge = MagicMock()

    # Build stub module so the lazy `from memento.tools.kg import ...` works.
    import types
    import sys
    kg_mod = types.ModuleType("memento.tools.kg")
    ce = MagicMock()
    ce.func = fake_create_entity
    ced = MagicMock()
    ced.func = fake_create_edge
    kg_mod.create_entity = ce
    kg_mod.create_edge = ced

    # Wrap sync mocks so asyncio.to_thread works
    async def _to_thread(fn, *a, **kw):
        return fn(*a, **kw)

    with patch.dict(sys.modules, {"memento.tools.kg": kg_mod}), \
         patch("gateway.mcp_server._check_tool_access", new_callable=AsyncMock), \
         patch("gateway.mcp_server.broadcast_tool_event", new_callable=AsyncMock) as mock_broadcast, \
         patch("gateway.mcp_server.asyncio.to_thread", side_effect=_to_thread):
        result = await mcp.call_tool(
            "mm_create_npc",
            {"npc_id": "test-npc", "name": "Gruk", "summary": "An orc"},
        )

    data = _extract_result(result)
    assert data["uuid"] == "uuid-1234"
    assert data["name"] == "Gruk"
    assert data["entity_type"] == "NPC"

    fake_create_entity.assert_called_once_with("Gruk", "NPC", "An orc")
    mock_broadcast.assert_awaited_once()
    call_kwargs = mock_broadcast.call_args
    assert call_kwargs[1]["tool"] == "mm_create_npc" or call_kwargs[0][1] == "mm_create_npc"


# ---------------------------------------------------------------------------
# T7 — Tool access gating (capability_missing)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_access_gating(mock_ws_hub):
    """Gated tool should raise ToolError with capability_missing prefix."""
    from mcp.server.fastmcp.exceptions import ToolError

    mcp = _get_fastmcp(mock_ws_hub)

    with patch(
        "gateway.mcp_server.check_tool_access",
        new_callable=AsyncMock,
        side_effect=__import__("fastapi").HTTPException(
            status_code=403, detail="no capability",
        ),
    ):
        with pytest.raises(ToolError, match="capability_missing"):
            await mcp.call_tool(
                "mm_create_npc",
                {"npc_id": "npc-1", "name": "X"},
            )


# ---------------------------------------------------------------------------
# T8 — Bridge-None guard on mm_trigger_npc
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bridge_none_guard_mm_trigger_npc(mock_ws_hub):
    """mm_trigger_npc with bridge=None should raise capability_unavailable."""
    from mcp.server.fastmcp.exceptions import ToolError

    mcp = _get_fastmcp(mock_ws_hub)  # bridge=None by default

    with patch("gateway.mcp_server._check_tool_access", new_callable=AsyncMock):
        with pytest.raises(ToolError, match="capability_unavailable"):
            await mcp.call_tool(
                "mm_trigger_npc",
                {"npc_id": "npc-1", "npc_name": "Gruk"},
            )
