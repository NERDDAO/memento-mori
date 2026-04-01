"""Context gathering crew — assembles KG context before narration."""

from crewai import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.kg import search_world, get_entity, get_neighbors


def make_context_crew(player_name: str, location_name: str, action: str) -> Crew:
    """Build a context gathering crew for the current scene."""
    model = get_model_for_crew("context")

    context_assembler = Agent(
        role="Scene Context Assembler",
        goal="Gather all relevant world knowledge for the current scene",
        backstory=(
            "You assemble context for a dark fantasy RPG narrator. Search the knowledge "
            "graph for information about the current location, NPCs present, items visible, "
            "and any recent events. Be thorough but concise."
        ),
        tools=[search_world, get_entity, get_neighbors],
        llm=LLM(model=model),
    )

    gather_task = Task(
        description=(
            f"The player '{player_name}' is at '{location_name}' and performed this action: "
            f"'{action}'\n\n"
            "Gather scene context by:\n"
            "1. Get details about the current location\n"
            "2. Search for NPCs at this location\n"
            "3. Search for items at this location\n"
            "4. Search for recent events in this area\n\n"
            "Compile a structured context summary."
        ),
        expected_output=(
            "A structured context block with sections: Location, NPCs Present, "
            "Items Visible, Recent Events, Exits Available."
        ),
        agent=context_assembler,
    )

    return Crew(
        agents=[context_assembler],
        tasks=[gather_task],
        process=Process.sequential,
    )
