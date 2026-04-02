"""Quest event detector — identifies quest triggers, progression, and completion."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.kg import search_world


def make_quest_detector_crew(action: str, context: str) -> Crew:
    """Build a crew that detects quest-related events in a player action."""
    model = get_model_for_crew("quest_detector")

    quest_detector = Agent(
        role="Quest Event Detector",
        goal="Identify quest triggers, stage progressions, and completions in player actions",
        backstory=(
            "You monitor quest state in a dark fantasy RPG. You detect: new quest triggers "
            "(NPC conversations that offer quests), stage progressions (completing an objective), "
            "and quest completions or failures. You search the world graph to match actions "
            "against existing active quests and their stage conditions."
        ),
        tools=[search_world],
        llm=LLM(model=model),
    )

    detect_task = Task(
        description=(
            f"Detect quest-related events in this player action.\n\n"
            f"Context:\n{context[:1000]}\n\n"
            f"Action: '{action}'\n\n"
            "Search the world for active quests that might be affected. "
            "Identify quest events:\n"
            "- QUEST_TRIGGER: new quest being offered or started\n"
            "- STAGE_COMPLETE: a quest stage objective fulfilled\n"
            "- QUEST_COMPLETE: entire quest finished\n"
            "- QUEST_FAIL: quest failed or made impossible\n"
            "- QUEST_UPDATE: relevant information discovered\n\n"
            "Return: event type, quest name (if known), stage (if applicable), notes."
        ),
        expected_output=(
            "Quest events detected: [{type, quest_name, stage, notes}]. "
            "Empty list if no quest events found."
        ),
        agent=quest_detector,
    )

    return Crew(
        agents=[quest_detector],
        tasks=[detect_task],
        process=Process.sequential,
    )
