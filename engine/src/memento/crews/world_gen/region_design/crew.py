"""Region design crew — generates biome, culture, and threat profile for a region."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.kg import search_world, create_entity


def make_region_design_crew(
    theme: str,
    adjacent_regions: str = "",
    player_level: int = 1,
    scaffold: str = "",
) -> Crew:
    """Build a crew that designs a full region and persists it to the KG."""
    model = get_model_for_crew("region_design")

    geographer = Agent(
        role="Geographer",
        goal="Design a compelling biome, terrain, and spatial logic for the region",
        backstory=(
            "You are a world-builder specialising in geography and spatial design for dark "
            "fantasy settings. You create regions with distinct terrain features, environmental "
            "storytelling, and logical layouts that reward exploration."
        ),
        tools=[search_world, create_entity],
        llm=LLM(model=model),
    )

    cultural_designer = Agent(
        role="Cultural Designer",
        goal="Define the cultures, conflicts, and history that shape this region",
        backstory=(
            "You are a lore architect who breathes life into fantasy regions through culture, "
            "faction tensions, and historical weight. You ground every location in believable "
            "human (and inhuman) drama."
        ),
        tools=[search_world],
        llm=LLM(model=model),
    )

    threat_designer = Agent(
        role="Threat Designer",
        goal="Design a danger profile — monsters, hazards, and political tensions — appropriate for the region",
        backstory=(
            "You are a game designer focused on creating meaningful threats that serve the "
            "narrative. You balance monster ecology, environmental hazards, and faction danger "
            "to produce a coherent and fair challenge landscape."
        ),
        tools=[search_world],
        llm=LLM(model=model),
    )

    geographer_task = Task(
        description=(
            f"Design a region with theme '{theme}'. "
            f"Player level: {player_level}. "
            + (f"Adjacent regions: {adjacent_regions}. " if adjacent_regions else "")
            + "Create it as a Region entity in the KG using the create_entity tool. "
            "Define its name, biome, terrain features, and propose 3-5 location names/types "
            "that would logically exist here."
        ),
        expected_output=(
            "Region concept including: name, biome, terrain description, spatial logic, "
            "and a list of 3-5 location names with their types (town, dungeon, landmark, etc.)."
        ),
        agent=geographer,
    )
    if scaffold:
        geographer_task.description += (
            "\n\nSCAFFOLD (use as starting point, modify freely, or discard if it doesn't fit):\n"
            + scaffold
        )

    cultural_designer_task = Task(
        description=(
            "Using the region defined by the geographer, define the cultures, factions, "
            "historical events, and ongoing conflicts that give this region its identity. "
            "Consider how the terrain and biome shaped the people and societies here."
        ),
        expected_output=(
            "Cultural overview including: dominant cultures or factions, key historical events, "
            "current conflicts or tensions, and how culture intersects with the region's geography."
        ),
        agent=cultural_designer,
        context=[geographer_task],
    )

    threat_designer_task = Task(
        description=(
            "Using the region, terrain, and cultural context established so far, design the "
            "threat landscape for this region. Define monster types and their ecological roles, "
            "environmental hazards, and any political dangers from the factions present."
        ),
        expected_output=(
            "Threat profile including: primary monster types with ecological justification, "
            "environmental hazards, political/faction dangers, and overall danger rating "
            f"appropriate for player level {player_level}."
        ),
        agent=threat_designer,
        context=[cultural_designer_task],
    )

    return Crew(
        agents=[geographer, cultural_designer, threat_designer],
        tasks=[geographer_task, cultural_designer_task, threat_designer_task],
        process=Process.sequential,
    )
