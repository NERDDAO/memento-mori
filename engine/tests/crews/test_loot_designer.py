"""Tests for the Loot Designer crew."""
import pytest
from memento.crews.loot_designer.crew import make_loot_designer_crew


def test_make_loot_designer_crew_returns_crew():
    crew = make_loot_designer_crew(
        location_name="Crypt of Shadows",
        theme="undead",
        num_items=3,
        rarity_budget="uncommon",
    )
    assert crew is not None
    assert len(crew.agents) >= 1
    assert len(crew.tasks) >= 1


def test_loot_designer_crew_has_scaffold():
    crew = make_loot_designer_crew(
        location_name="Forest Clearing",
        theme="nature",
        num_items=5,
        rarity_budget="rare",
    )
    first_task = crew.tasks[0]
    assert "SCAFFOLD" in first_task.description or "Pre-rolled" in first_task.description


def test_loot_designer_has_update_grammar_tool():
    crew = make_loot_designer_crew(
        location_name="Test",
        num_items=1,
    )
    tool_names = [t.name for t in crew.agents[0].tools]
    assert "update_grammar" in tool_names
