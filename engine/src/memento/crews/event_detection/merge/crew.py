"""Event merge crew — deduplicates, resolves conflicts, and orders events by priority."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew


def make_event_merge_crew(detected_events: str) -> Crew:
    """Build a crew that merges events from multiple detectors into a clean ordered list."""
    model = get_model_for_crew("event_merge")

    event_merger = Agent(
        role="Event Merger",
        goal="Consolidate events from multiple detectors into a clean, prioritized, deduplicated list",
        backstory=(
            "You merge and reconcile events detected by multiple specialized detectors. "
            "You remove duplicates (same event flagged by two detectors), resolve conflicts "
            "(contradictory events like ATTACK and FRIENDLY_CONVERSATION), and order events "
            "by priority: combat > death > world_change > quest > inventory > social. "
            "Your output feeds the game engine — it must be clean and unambiguous."
        ),
        tools=[],
        llm=LLM(model=model),
    )

    merge_task = Task(
        description=(
            f"Merge, deduplicate, and prioritize these detected events:\n\n"
            f"{detected_events}\n\n"
            "Steps:\n"
            "1. Remove exact duplicates\n"
            "2. Resolve conflicts (keep the higher-priority event)\n"
            "3. Order by priority: combat > death > world_change > quest > inventory > social\n"
            "4. Output a clean ordered list\n\n"
            "Priority order: ATTACK/THREATEN/HOSTILE_NPC > DEATH > DOOR_STATE/STRUCTURE_CHANGED "
            "> QUEST_TRIGGER/STAGE_COMPLETE/QUEST_COMPLETE > PICKUP/DROP/USE > social events"
        ),
        expected_output=(
            "Clean ordered list of events, deduplicated and prioritized. "
            "Format: numbered list with event type, entity/subject, and brief description."
        ),
        agent=event_merger,
    )

    return Crew(
        agents=[event_merger],
        tasks=[merge_task],
        process=Process.sequential,
    )
