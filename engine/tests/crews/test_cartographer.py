"""Tests for the Cartographer crew."""
import pytest
from memento.crews.cartographer.crew import make_cartographer_crew


def test_make_cartographer_crew_returns_crew():
    crew = make_cartographer_crew(
        location_name="Ruined Chapel",
        description="A crumbling stone chapel overtaken by dark vines.",
        mood="eerie",
        biome="ruins",
        width=35,
        height=20,
    )
    assert crew is not None
    assert len(crew.agents) == 2
    assert len(crew.tasks) >= 3


def test_cartographer_crew_artist_has_scaffold_tool():
    crew = make_cartographer_crew(
        location_name="Dark Forest",
        description="Ancient trees block all light.",
        mood="dark",
        biome="forest",
    )
    artist = crew.agents[0]
    tool_names = [t.name for t in artist.tools]
    assert "generate_terrain" in tool_names
    assert "validate_art" in tool_names


def test_cartographer_crew_uses_biome_in_scaffold_task():
    crew = make_cartographer_crew(
        location_name="Village Square",
        description="A busy market square.",
        mood="peaceful",
        biome="village",
    )
    scaffold_task = crew.tasks[0]
    assert "village" in scaffold_task.description.lower()
