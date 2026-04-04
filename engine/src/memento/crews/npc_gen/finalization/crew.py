"""NPC finalization crew — persists the NPC to the knowledge graph with structured attributes."""

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
            f"edge connecting them to '{location_name}'. Return the NPC's UUID and name.\n\n"
            f"IMPORTANT: After confirming the entity was created, output a structured JSON block "
            f"containing the NPC's attributes extracted from the profile above. The JSON must "
            f"include these fields:\n"
            f"- personality: 2-3 sentence personality description\n"
            f"- backstory: 2-3 sentence backstory\n"
            f"- speech_pattern: how they talk\n"
            f"- motivation: what drives them\n"
            f"- traits: array of 3-5 personality trait words\n"
            f"- stats: object with STR, DEX, CON, INT, WIS, CHA (values 3-18)\n"
            f"- skills: object with skill_name: level (1-10)\n"
            f"- abilities: array of objects with name and description\n"
            f"- disposition: one of hostile/unfriendly/neutral/friendly/allied\n"
            f"- secret: a hidden fact\n\n"
            f"Format the JSON block on its own line, wrapped in ```json ... ``` markers."
        ),
        expected_output=(
            "A confirmation message containing the NPC's UUID and name, confirming that "
            "the entity was created and a LOCATED_IN edge was established to the location, "
            "followed by a ```json``` block with the NPC's structured attributes."
        ),
        agent=finalizer,
    )

    return Crew(
        agents=[finalizer],
        tasks=[finalize_task],
        process=Process.sequential,
    )
