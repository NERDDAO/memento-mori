"""Tests for the Portraitist crew."""
import pytest
from memento.crews.portraitist.crew import make_portraitist_crew


def test_make_portraitist_crew_returns_crew():
    crew = make_portraitist_crew(
        entity_name="Gravekeeper Mord",
        entity_type="npc",
        description="A gaunt figure in tattered robes, carrying a rusted lantern.",
        labels=["NPC"],
        biome="crypt",
    )
    assert crew is not None
    assert len(crew.agents) == 2
    assert len(crew.tasks) >= 3


def test_portraitist_crew_artist_has_sprite_tools():
    crew = make_portraitist_crew(
        entity_name="Iron Sword",
        entity_type="item",
        description="A simple iron blade.",
        labels=["Weapon", "Item"],
        biome="default",
    )
    artist = crew.agents[0]
    tool_names = [t.name for t in artist.tools]
    assert "generate_sprite" in tool_names
    assert "validate_sprite" in tool_names


def test_portraitist_crew_icon_mode():
    crew = make_portraitist_crew(
        entity_name="Health Potion",
        entity_type="item",
        description="A small red vial.",
        labels=["Potion", "Item"],
        biome="default",
        icon_mode=True,
    )
    gen_task = crew.tasks[0]
    assert "8" in gen_task.description or "icon" in gen_task.description.lower()
