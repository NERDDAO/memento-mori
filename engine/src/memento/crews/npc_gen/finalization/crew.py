"""NPC finalization crew — persists the NPC to the knowledge graph."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.kg import create_entity, create_edge


def make_finalization_crew(npc_full: str, location_name: str) -> Crew:
    """Build a crew that writes a completed NPC into the knowledge graph."""
    model = get_model_for_crew("npc_finalization")

    finalizer = Agent(
        role="NPC Knowledge Graph Finalizer",
        goal="Persist a fully specified NPC into the knowledge graph and link them to their location",
        backstory=(
            "You are the archivist of the world's knowledge graph. When an NPC has been fully "
            "designed — concept, personality, and mechanics — you create their entity record "
            "and establish the relationships that place them in the world."
        ),
        tools=[create_entity, create_edge],
        llm=LLM(model=model),
    )

    finalize_task = Task(
        description=(
            f"NPC full profile:\n{npc_full}\n\n"
            f"Create this NPC as an entity in the knowledge graph. Then create a LOCATED_IN "
            f"edge connecting them to '{location_name}'. Return the NPC's UUID and name."
        ),
        expected_output=(
            "A confirmation message containing the NPC's UUID and name, confirming that "
            "the entity was created and a LOCATED_IN edge was established to the location."
        ),
        agent=finalizer,
    )

    return Crew(
        agents=[finalizer],
        tasks=[finalize_task],
        process=Process.sequential,
    )
