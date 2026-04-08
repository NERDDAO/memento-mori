"""Tests for CrewAI-accessible art tools."""
import json
import pytest

from memento.tools.art_tools import (
    generate_terrain_tool,
    generate_sprite_tool,
    select_palette_tool,
)


def test_generate_terrain_tool_returns_ascii():
    result = generate_terrain_tool.run(biome="default", width=20, height=10, seed=42)
    lines = result.strip().split("\n")
    assert len(lines) == 10
    assert all(len(l) == 20 for l in lines)


def test_generate_sprite_tool_returns_base64():
    result = generate_sprite_tool.run(
        entity_labels='["NPC"]', biome="crypt", seed=42
    )
    parsed = json.loads(result)
    assert "sprite_b64" in parsed
    assert "width" in parsed
    assert "height" in parsed
    assert parsed["width"] in (16, 32)


def test_select_palette_tool_returns_colors():
    result = select_palette_tool.run(biome="forest", mood="dark")
    parsed = json.loads(result)
    assert "primary" in parsed
    assert "accent" in parsed
    assert len(parsed["primary"]) == 3
