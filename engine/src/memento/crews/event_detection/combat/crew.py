"""Combat event detector — identifies combat triggers in player actions."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew


def make_combat_detector_crew(action: str, context: str) -> Crew:
    """Build a crew that detects combat triggers in a player action."""
    model = get_model_for_crew("combat_detector")

    combat_detector = Agent(
        role="Combat Event Detector",
        goal="Identify whether a player action triggers, escalates, or resolves combat",
        backstory=(
            "You analyze player actions for combat implications. You detect: attacks, "
            "threats, hostile NPC responses, fleeing, weapon draws, and ambushes. "
            "You are inclusive — flag anything that MIGHT trigger combat. Better to "
            "check and find nothing than miss a violent escalation."
        ),
        tools=[],
        llm=LLM(model=model),
    )

    detect_task = Task(
        description=(
            f"Analyze this player action for combat triggers.\n\n"
            f"Context:\n{context[:1000]}\n\n"
            f"Action: '{action}'\n\n"
            "Identify any of these combat events:\n"
            "- ATTACK: direct physical assault\n"
            "- THREATEN: threatening an NPC\n"
            "- HOSTILE_NPC: NPC becoming hostile\n"
            "- AMBUSH: surprise attack\n"
            "- FLEE: player or NPC fleeing combat\n"
            "- COMBAT_END: combat concluding\n\n"
            "Return a JSON object with: "
            "{\"detected\": true/false, \"events\": [list of event types], \"notes\": \"brief explanation\"}"
        ),
        expected_output=(
            "JSON: {\"detected\": bool, \"events\": [str], \"notes\": str}"
        ),
        agent=combat_detector,
    )

    return Crew(
        agents=[combat_detector],
        tasks=[detect_task],
        process=Process.sequential,
    )
