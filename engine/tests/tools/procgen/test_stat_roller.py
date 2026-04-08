"""Tests for NPC stat roller and item loot roller."""
import pytest
from memento.tools.procgen.stat_roller import (
    roll_npc_stats,
    roll_loot,
    load_archetypes,
    load_loot_tables,
)


def test_load_archetypes():
    archetypes = load_archetypes()
    assert "warrior" in archetypes
    assert "scholar" in archetypes
    assert "default" in archetypes


def test_load_loot_tables():
    tables = load_loot_tables()
    assert "rarity_weights" in tables
    assert "stat_budgets" in tables


def test_roll_npc_stats_warrior():
    stats = roll_npc_stats("warrior", seed=42)
    assert "STR" in stats
    assert "DEX" in stats
    assert "CON" in stats
    assert "INT" in stats
    assert "WIS" in stats
    assert "CHA" in stats
    assert 14 <= stats["STR"] <= 18
    assert "skills" in stats
    assert "abilities" in stats
    assert len(stats["abilities"]) >= 1
    assert len(stats["abilities"]) <= 3


def test_roll_npc_stats_unknown_archetype_uses_default():
    stats = roll_npc_stats("nonexistent_role", seed=42)
    default_stats = roll_npc_stats("default", seed=42)
    assert stats["skills"] == default_stats["skills"]


def test_roll_npc_stats_deterministic():
    s1 = roll_npc_stats("warrior", seed=42)
    s2 = roll_npc_stats("warrior", seed=42)
    assert s1 == s2


def test_roll_npc_stats_different_seeds():
    s1 = roll_npc_stats("warrior", seed=42)
    s2 = roll_npc_stats("warrior", seed=99)
    assert s1 != s2


def test_roll_loot_returns_correct_count():
    items = roll_loot("common", num_items=3, seed=42)
    assert len(items) == 3


def test_roll_loot_item_has_required_fields():
    items = roll_loot("common", num_items=1, seed=42)
    item = items[0]
    assert "name" in item
    assert "rarity" in item
    assert "slot" in item
    assert "damage" in item
    assert "defense" in item
    assert "weight" in item


def test_roll_loot_rarity_respects_budget():
    items = roll_loot("common", num_items=20, seed=42)
    rarities = [i["rarity"] for i in items]
    common_count = rarities.count("common")
    assert common_count >= 10


def test_roll_loot_deterministic():
    l1 = roll_loot("uncommon", num_items=3, seed=42)
    l2 = roll_loot("uncommon", num_items=3, seed=42)
    assert l1 == l2


def test_roll_loot_stats_within_budget():
    items = roll_loot("rare", num_items=5, seed=42)
    for item in items:
        rarity = item["rarity"]
        max_budgets = {"common": 5, "uncommon": 10, "rare": 18, "epic": 28, "legendary": 40}
        budget = max_budgets.get(rarity, 40)
        total_stats = item["damage"] + item["defense"]
        assert total_stats <= budget, f"{item['name']} total stats {total_stats} exceeds budget {budget}"
