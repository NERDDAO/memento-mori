"""NPC planning crew — decides what NPC roles a location needs."""

from crewai import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.kg import search_world


def make_npc_planning_crew(
    location_name: str,
    location_description: str,
    existing_npcs: str = "",
) -> Crew:
    """Build a crew that plans which NPC roles a location needs."""
    model = get_model_for_crew("npc_planning")

    npc_planner = Agent(
        role="NPC Role Planner",
        goal="Determine what NPC roles would make a location feel alive and story-rich",
        backstory=(
            "You are a world-builder for a dark fantasy RPG. Given a location, you analyse "
            "its purpose, atmosphere, and narrative potential to decide which NPCs should "
            "inhabit it. You avoid redundancy and strive for a cast that offers services, "
            "conflict, and story hooks."
        ),
        tools=[search_world],
        llm=LLM(model=model),
    )

    plan_task = Task(
        description=(
            f"Location: '{location_name}'\n"
            f"Description: {location_description}\n\n"
            "Decide what NPC roles this location needs. Consider: what services are available, "
            "what conflicts exist, what stories could unfold. Suggest 2-4 NPCs with roles "
            "(barkeep, guard, merchant, quest-giver, etc.). "
            f"Avoid duplicating roles already filled by: {existing_npcs}"
        ),
        expected_output=(
            "A list of 2-4 NPC roles with a one-sentence rationale for each, explaining "
            "how they serve the location's function and narrative potential."
        ),
        agent=npc_planner,
    )

    return Crew(
        agents=[npc_planner],
        tasks=[plan_task],
        process=Process.sequential,
    )
