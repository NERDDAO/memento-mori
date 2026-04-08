"""Tests for Tracery text generation."""
import pytest
from memento.tools.procgen.text_gen import (
    generate_text,
    generate_npc_name,
    generate_npc_scaffold,
    generate_item_name,
    generate_narration_scaffold,
    generate_location_scaffold,
)


def test_generate_text_narration():
    result = generate_text("narration", seed=42)
    assert isinstance(result, str)
    assert len(result) > 10
    assert "." in result


def test_generate_text_deterministic():
    r1 = generate_text("narration", seed=42)
    r2 = generate_text("narration", seed=42)
    assert r1 == r2


def test_generate_text_different_seeds():
    r1 = generate_text("narration", seed=42)
    r2 = generate_text("narration", seed=99)
    assert r1 != r2


def test_generate_npc_name():
    name = generate_npc_name(seed=42)
    assert isinstance(name, str)
    parts = name.split()
    assert len(parts) == 2


def test_generate_npc_scaffold():
    scaffold = generate_npc_scaffold(role="tavern keeper", location="The Rusty Nail", seed=42)
    assert "Name:" in scaffold
    assert "Appearance:" in scaffold
    assert "Personality:" in scaffold


def test_generate_item_name_with_rarity():
    name = generate_item_name(slot="weapon", rarity="rare", seed=42)
    assert isinstance(name, str)
    assert len(name) > 3


def test_generate_narration_scaffold():
    scaffold = generate_narration_scaffold(seed=42)
    assert isinstance(scaffold, str)
    assert len(scaffold) > 10


def test_generate_location_scaffold():
    scaffold = generate_location_scaffold(seed=42)
    assert isinstance(scaffold, str)
    assert len(scaffold) > 10


def test_unknown_grammar_returns_empty():
    result = generate_text("nonexistent_grammar", seed=42)
    assert result == ""
