"""Permadeath crew — narrates death and creates a memorial in the knowledge graph."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.kg import search_world, mark_status, create_edge, remember_event, pin_entity


def make_permadeath_crew(
    player_name: str, cause: str, location: str, context: str
) -> Crew:
    """Build a permadeath crew to narrate death and memorialize the player."""
    model = get_model_for_crew("permadeath")

    death_narrator = Agent(
        role="Death Narrator",
        goal="Narrate the player's death with dramatic weight and finality",
        backstory=(
            "You write death sequences for a dark fantasy permadeath RPG. "
            "When a player dies, it is permanent. The narrative must honor that weight — "
            "this character's story ends here. Search the world for context about who "
            "this player was, what they had done, and where they fell. "
            "Make the death feel earned and final, not arbitrary."
        ),
        tools=[search_world],
        llm=LLM(model=model),
    )

    memorial_writer = Agent(
        role="Memorial Writer",
        goal="Immortalize the fallen player in the knowledge graph as a permanent memorial",
        backstory=(
            "You create memorials for fallen players in a dark fantasy permadeath RPG. "
            "Once a player dies, their story must be preserved — marked dead, linked to "
            "their place of death, their final moments recorded as a memory. "
            "Other players may one day find traces of those who came before. "
            "Permanence is the point."
        ),
        tools=[mark_status, create_edge, remember_event, pin_entity],
        llm=LLM(model=model),
    )

    narrate_death_task = Task(
        description=(
            f"Write the death narrative for this fallen player:\n\n"
            f"Player: {player_name}\n"
            f"Cause of death: {cause}\n"
            f"Location: {location}\n"
            f"Context:\n{context}\n\n"
            "Search the world for information about this player and location. "
            "Write a death sequence of 2-4 paragraphs that:\n"
            "1. Describes the moment of death with visceral specificity\n"
            "2. Acknowledges what this character meant to the world\n"
            "3. Conveys the permanence and finality — this is over\n"
            "4. Ends with an epitaph-like closing line\n\n"
            "Do not soften it. Death is the point of this game."
        ),
        expected_output=(
            "2-4 paragraphs of death narrative, ending with a one-line epitaph. "
            "Specific to this player, this cause, this location."
        ),
        agent=death_narrator,
    )

    memorialize_task = Task(
        description=(
            f"Create a permanent memorial for {player_name} in the knowledge graph:\n\n"
            "Using the death narrative provided:\n"
            f"1. Mark {player_name}'s status as 'dead'\n"
            f"2. Pin {player_name} as a notable entity (fallen heroes persist)\n"
            f"3. Create an edge linking {player_name} to {location} with type DIED_AT\n"
            "4. Record the death as a world event using remember_event "
            f"   — include player name, cause, location, and epitaph\n\n"
            "This memorial is permanent. Future players may encounter evidence of this death."
        ),
        expected_output=(
            "Memorial confirmation: status marked dead, entity pinned, "
            "DIED_AT edge created, death event recorded in memory."
        ),
        agent=memorial_writer,
        context=[narrate_death_task],
    )

    return Crew(
        agents=[death_narrator, memorial_writer],
        tasks=[narrate_death_task, memorialize_task],
        process=Process.sequential,
    )
