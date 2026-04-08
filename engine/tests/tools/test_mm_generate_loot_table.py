"""Tests for mm_generate_loot_table tool."""
import json
import pytest
from unittest.mock import patch, MagicMock
from memento.tools.mm_generate_loot_table import mm_generate_loot_table


@patch("memento.tools.mm_generate_loot_table._get_loot_designer_crew")
def test_mm_generate_loot_table_returns_json(mock_crew_fn):
    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = MagicMock(raw=json.dumps([
        {"name": "Crypt Blade", "rarity": "uncommon", "slot": "weapon",
         "damage": 6, "defense": 0, "weight": 5, "lore": "Forged in darkness", "effects": []}
    ]))
    mock_crew_fn.return_value = mock_crew

    result = mm_generate_loot_table.run(
        location_name="Crypt of Shadows",
        theme="undead",
        num_items=3,
        rarity_budget="uncommon",
    )
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert len(parsed) >= 1
    assert "name" in parsed[0]


@patch("memento.tools.mm_generate_loot_table._get_loot_designer_crew")
def test_mm_generate_loot_table_fallback_on_error(mock_crew_fn):
    mock_crew_fn.side_effect = Exception("crew failed")

    result = mm_generate_loot_table.run(
        location_name="Test",
        num_items=2,
        rarity_budget="common",
    )
    # Should fall back to table-rolled items
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
