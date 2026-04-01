"""Tests for deterministic game mechanic tools."""

import pytest
from memento.tools.mechanics import (
    roll_skill_check,
    calculate_damage,
    check_carry_capacity,
    apply_status_effect,
    calculate_xp,
    evaluate_disposition,
    roll_loot_table,
)


def test_skill_check_easy_pass():
    """skill 10 vs difficulty 5 — with a minimum roll of 1, total is at least 11, always passes."""
    result = roll_skill_check.run(skill_level="10", difficulty="5", modifiers="0")
    assert "PASS" in result


def test_skill_check_output_format():
    """Output must contain either PASS or FAIL."""
    result = roll_skill_check.run(skill_level="5", difficulty="15", modifiers="0")
    assert "PASS" in result or "FAIL" in result


def test_calculate_damage():
    """10 weapon + 5 strength - 3 armor = 12."""
    result = calculate_damage.run(weapon_damage="10", attacker_strength="5", defender_armor="3")
    assert "Damage: 12" in result


def test_calculate_damage_minimum_zero():
    """Armor exceeds raw damage — clamped to 0."""
    result = calculate_damage.run(weapon_damage="2", attacker_strength="1", defender_armor="10")
    assert "Damage: 0" in result


def test_carry_capacity_ok():
    """30 + 10 = 40 <= 50 — should be OK."""
    result = check_carry_capacity.run(current_weight="30", max_capacity="50", item_weight="10")
    assert "OK" in result
    assert "40/50" in result


def test_carry_capacity_exceeded():
    """45 + 10 = 55 > 50 — should fail."""
    result = check_carry_capacity.run(current_weight="45", max_capacity="50", item_weight="10")
    assert "Cannot carry" in result
    assert "55/50" in result


def test_calculate_xp_no_levelup():
    """50 + 20 = 70, threshold for level 1 is 100 — no level up."""
    result = calculate_xp.run(current_xp="50", xp_award="20", level="1")
    assert "70/100" in result
    assert "LEVEL UP" not in result


def test_calculate_xp_levelup():
    """90 + 20 = 110 >= 100 — level up."""
    result = calculate_xp.run(current_xp="90", xp_award="20", level="1")
    assert "LEVEL UP" in result
    assert "New level: 2" in result


def test_evaluate_disposition():
    """friendly_conversation should increase friendship by 0.03 and trust by 0.02."""
    result = evaluate_disposition.run(
        current_friendship="0.50", current_trust="0.50", interaction_type="friendly_conversation"
    )
    assert "0.53" in result
    assert "0.52" in result


def test_roll_loot_table():
    """Should return a non-empty result with the budget label."""
    result = roll_loot_table.run(rarity_budget="rare", num_items="3")
    assert "rare" in result
    assert "Item 1" in result
    assert "Item 3" in result
