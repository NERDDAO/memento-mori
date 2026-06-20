"""C6 — kit edit (§7.5) + McpToolBridge wiring (§7.1) unit tests.

Two halves:

1. Capability-kit edit (``engine/src/memento/tools/tool_labels.py``):
   the three construction tool names must be present in the NPC kit, and
   ``mm_move`` / ``mm_take`` (but NOT ``mm_attack``) in the Player kit.

2. Gateway wiring (``gateway/src/gateway/cxn_tools.py`` + ``mcp_server.py``):
   ``register_cxn_tools`` imports cleanly, is callable, registers the three
   cxn tools on a bare ``FastMCP`` instance with the Day-1 default ports, and
   ``mcp_server.build_mcp_app`` still imports.

No LLM, no NLP, no network. The gateway half does not exercise the JWT
middleware or any HTTP path — it asserts import + structural registration
only (see the module-level concern note).
"""
from __future__ import annotations

import os
import sys

import pytest

from memento.tools.tool_labels import KITS


# ---------------------------------------------------------------------------
# Part 1 — §7.5 capability-kit edit
# ---------------------------------------------------------------------------


def test_npc_kit_has_all_three_cxn_tools() -> None:
    npc = KITS["NPC"]
    assert "mm_move" in npc
    assert "mm_attack" in npc
    assert "mm_take" in npc


def test_player_kit_has_move_and_take() -> None:
    player = KITS["Player"]
    assert "mm_move" in player
    assert "mm_take" in player


def test_player_kit_excludes_attack() -> None:
    # Players deliberately do NOT get combat (§7.5).
    assert "mm_attack" not in KITS["Player"]


def test_kit_edit_preserves_existing_npc_entries() -> None:
    # Minimal-edit guarantee: the legacy NPC tools must all still be present.
    npc = KITS["NPC"]
    for legacy in (
        "mm_resolve_combat",
        "mm_assess_combat",
        "mm_check_plausibility",
        "mm_give_item",
        "mm_create_item",
        "mm_inventory",
        "mm_inventory_transfer",
        "mm_remember_event",
        "mm_update_entity",
        "mm_move_to",
        "mm_move_within",
        "mm_give_quest",
    ):
        assert legacy in npc, legacy


def test_kit_edit_preserves_existing_player_entries() -> None:
    player = KITS["Player"]
    for legacy in ("mm_inventory", "mm_move_to", "mm_check_plausibility", "mm_give_item"):
        assert legacy in player, legacy


# ---------------------------------------------------------------------------
# Part 2 — gateway wiring (import + structural assertions only)
# ---------------------------------------------------------------------------

# The gateway package lives in a sibling source root; add it to the path so
# this engine-side test can import it. No JWT middleware / HTTP path is
# exercised — see the module docstring.
_GATEWAY_SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "gateway", "src")
)
if _GATEWAY_SRC not in sys.path:
    sys.path.insert(0, _GATEWAY_SRC)

# Skip the gateway half cleanly if its runtime dep (FastMCP / mcp) is absent,
# rather than faking behaviour.
mcp_fastmcp = pytest.importorskip("mcp.server.fastmcp")


def test_cxn_tools_imports_cleanly_and_register_is_callable() -> None:
    import gateway.cxn_tools as cxn_tools

    assert hasattr(cxn_tools, "register_cxn_tools")
    assert callable(cxn_tools.register_cxn_tools)


def test_build_mcp_app_still_imports() -> None:
    from gateway.mcp_server import build_mcp_app

    assert callable(build_mcp_app)


def test_register_cxn_tools_registers_three_tools() -> None:
    from gateway.cxn_tools import register_cxn_tools
    from memento.memory.capturing_client import CapturingMemoryClient
    from memento.state.chain_mirror import NoopChainMirror
    from memento.state.in_memory import InMemoryStateRepository

    mcp = mcp_fastmcp.FastMCP("test-cxn")
    register_cxn_tools(
        mcp,
        None,  # ws_hub — broadcast_tool_event no-ops on None
        InMemoryStateRepository(),
        NoopChainMirror(),
        CapturingMemoryClient(),
    )

    registered = set(mcp._tool_manager._tools.keys())
    assert registered == {"mm_move", "mm_attack", "mm_take"}
