"""Reputation crew — tracks how player actions affect faction standing."""

from crewai import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.kg import update_entity
from memento.tools.mechanics import evaluate_disposition


def make_reputation_crew(player: str, faction: str, action: str) -> Crew:
    """Build a crew that assesses how a player action affects faction reputation."""
    model = get_model_for_crew("reputation")

    reputation_tracker = Agent(
        role="Faction Reputation Tracker",
        goal="Assess how a player action shifts their standing with a faction and update records",
        backstory=(
            "You track faction reputation in a dark fantasy RPG. You understand that factions "
            "care about their interests, not abstract morality. An action that helps one faction "
            "may hurt another. You evaluate the player's action in terms of the faction's values "
            "and power, calculate the disposition shift, then update the faction's world record."
        ),
        tools=[update_entity, evaluate_disposition],
        llm=LLM(model=model),
    )

    reputation_task = Task(
        description=(
            f"Assess how this action affects the player's standing with a faction.\n\n"
            f"Player: {player}\n"
            f"Faction: {faction}\n"
            f"Action taken: {action}\n\n"
            "Steps:\n"
            "1. Determine what interaction type this represents "
            "(friendly_conversation, hostile_action, gift, betrayal, help_in_combat, theft, trade)\n"
            "2. Use Evaluate Disposition to calculate the shift (use current values 0.0 if unknown)\n"
            "3. Update the faction entity with the new reputation standing\n"
            "4. Explain in 1-2 sentences how this action was perceived"
        ),
        expected_output=(
            "Reputation assessment: the interaction type, disposition shift values, "
            "updated faction record, and a brief explanation of how the faction perceives this action."
        ),
        agent=reputation_tracker,
    )

    return Crew(
        agents=[reputation_tracker],
        tasks=[reputation_task],
        process=Process.sequential,
    )
