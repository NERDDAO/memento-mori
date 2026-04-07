# engine/tests/test_engine_routes.py
"""Tests for engine tool endpoints and NPC capability gating."""

import os
import pytest


def test_tool_labels_barkeep():
    """Barkeep with Combat, Trade, Memory labels gets expected tools."""
    from memento.tools.tool_labels import get_allowed_tools
    tools = get_allowed_tools(["NPC", "Combat", "Trade", "Memory"])
    assert "mm_get_state" in tools  # innate
    assert "mm_resolve_combat" in tools  # Combat label
    assert "mm_give_item" in tools  # Trade label
    assert "mm_remember_event" in tools  # Memory label
    assert "mm_design_region" not in tools  # no Cartography label


def test_tool_labels_empty():
    """Empty labels only get innate tools."""
    from memento.tools.tool_labels import get_allowed_tools
    tools = get_allowed_tools([])
    assert "mm_get_state" in tools  # innate always
    assert "mm_resolve_combat" not in tools  # no Combat label


def test_tool_labels_all():
    """All labels grant all tools."""
    from memento.tools.tool_labels import get_allowed_tools, LABEL_TOOLS, INNATE_TOOLS
    all_labels = list(LABEL_TOOLS.keys())
    tools = get_allowed_tools(all_labels)
    expected = set(INNATE_TOOLS)
    for label_tools in LABEL_TOOLS.values():
        expected |= label_tools
    assert tools == expected


def test_tool_labels_innate_count():
    """Innate tools count should match INNATE_TOOLS definition."""
    from memento.tools.tool_labels import INNATE_TOOLS
    assert len(INNATE_TOOLS) == 10


def test_tool_labels_all_labels_defined():
    """Every label in LABEL_TOOLS maps to at least one tool."""
    from memento.tools.tool_labels import LABEL_TOOLS
    for label, tools in LABEL_TOOLS.items():
        assert len(tools) > 0, f"Label '{label}' has no tools"


def test_seed_script_parses():
    """Verify the seed script is valid Python."""
    import ast
    seed_path = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "seed_engine_tools.py")
    seed_path = os.path.normpath(seed_path)
    if not os.path.exists(seed_path):
        pytest.skip("seed script not found")
    with open(seed_path) as f:
        ast.parse(f.read())
