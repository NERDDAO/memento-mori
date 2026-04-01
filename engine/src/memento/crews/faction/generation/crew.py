"""Faction generation crew — creates factions and maps their relationships."""

from crewai import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.kg import search_world, create_entity, create_edge


def make_faction_generation_crew(region: str, num_factions: int = 2) -> Crew:
    """Build a crew that generates factions for a region and maps their relationships."""
    model = get_model_for_crew("faction_generation")

    faction_designer = Agent(
        role="Faction Designer",
        goal="Create distinct, believable factions with clear goals, culture, and power base",
        backstory=(
            "You design political factions for a dark fantasy RPG. Each faction you create "
            "has a reason to exist — a resource they control, a belief they defend, a wound "
            "that drives them. You search the world for context, then create faction entities "
            "in the knowledge graph. Factions are not monolithic; they have internal tensions."
        ),
        tools=[search_world, create_entity],
        llm=LLM(model=model),
    )

    relationship_mapper = Agent(
        role="Faction Relationship Mapper",
        goal="Define the web of alliances, rivalries, and uneasy truces between factions",
        backstory=(
            "You map inter-faction relationships for a living political world. You take "
            "faction concepts and determine how they relate — who trades with whom, who "
            "despises whom, who is playing both sides. You record these relationships as "
            "edges in the knowledge graph. History matters: old grievances, broken treaties, "
            "and shared enemies shape every interaction."
        ),
        tools=[create_edge],
        llm=LLM(model=model),
    )

    faction_task = Task(
        description=(
            f"Create {num_factions} distinct factions for the region '{region}'.\n\n"
            "Search the world for existing lore and regional context first. "
            "For each faction provide:\n"
            "- Name\n"
            "- Power base (what they control or represent)\n"
            "- Core motivation\n"
            "- Leadership structure\n"
            "- Public face vs. hidden agenda\n\n"
            "Create each faction as an entity in the knowledge graph."
        ),
        expected_output=(
            f"{num_factions} faction profiles, each with: name, power base, "
            "motivation, leadership, and public vs. hidden agenda. "
            "Confirmation of entity creation for each."
        ),
        agent=faction_designer,
    )

    relationship_task = Task(
        description=(
            "Map the relationships between all generated factions. "
            "For each pair of factions, define their relationship and record it as an edge.\n\n"
            "Use relationship types such as: ALLIED_WITH, HOSTILE_TO, TRADES_WITH, "
            "COMPETES_WITH, SECRETLY_ALLIED_WITH, CONTROLS.\n\n"
            "Include a brief fact explaining the history or reason for each relationship."
        ),
        expected_output=(
            "A relationship map showing how each faction pair relates, "
            "with confirmation of each edge created in the knowledge graph."
        ),
        agent=relationship_mapper,
        context=[faction_task],
    )

    return Crew(
        agents=[faction_designer, relationship_mapper],
        tasks=[faction_task, relationship_task],
        process=Process.sequential,
    )
