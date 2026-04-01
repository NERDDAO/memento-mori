"""World change event detector — identifies changes to world state."""

from crewai import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.kg import search_world


def make_world_change_detector_crew(action: str, context: str) -> Crew:
    """Build a crew that detects world state changes in a player action."""
    model = get_model_for_crew("world_change_detector")

    world_change_detector = Agent(
        role="World Change Detector",
        goal="Identify persistent changes to world state caused by player actions",
        backstory=(
            "You track world state changes in a dark fantasy RPG. You detect: doors opened "
            "or locked, items crafted or destroyed, structures built or damaged, levers pulled, "
            "locks picked, fires started, and any other durable change to the physical world. "
            "You search the world graph to understand the current state of affected entities "
            "before flagging what changed."
        ),
        tools=[search_world],
        llm=LLM(model=model),
    )

    detect_task = Task(
        description=(
            f"Detect world state changes caused by this player action.\n\n"
            f"Context:\n{context[:1000]}\n\n"
            f"Action: '{action}'\n\n"
            "Search the world for relevant entities. Identify world changes:\n"
            "- DOOR_STATE: door opened, closed, locked, or broken\n"
            "- ITEM_CRAFTED: new item created\n"
            "- ITEM_DESTROYED: item permanently removed\n"
            "- STRUCTURE_CHANGED: building, bridge, or structure modified\n"
            "- MECHANISM_TRIGGERED: lever, switch, trap activated\n"
            "- ENVIRONMENT_CHANGED: fire, flood, other environmental change\n\n"
            "For each change: event type, entity name, old state, new state."
        ),
        expected_output=(
            "World change events: [{type, entity, old_state, new_state}]. "
            "Empty list if no world state changed."
        ),
        agent=world_change_detector,
    )

    return Crew(
        agents=[world_change_detector],
        tasks=[detect_task],
        process=Process.sequential,
    )
