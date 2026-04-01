"""Quest dialogue crew — writes NPC dialogue for quest acceptance, hints, and completion."""

from crewai import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew


def make_quest_dialogue_crew(quest: str, npc_name: str) -> Crew:
    """Build a crew that writes quest-giver dialogue for a quest."""
    model = get_model_for_crew("quest_dialogue")

    dialogue_writer = Agent(
        role="Quest Dialogue Writer",
        goal="Write authentic, character-specific NPC dialogue for quest interactions",
        backstory=(
            "You write NPC dialogue for a dark fantasy RPG. Your dialogue reveals character "
            "through word choice, not description. Quest-givers have their own voices shaped "
            "by their desperation, greed, grief, or pride. You write three dialogue sets: "
            "acceptance (how they give the quest), hints (what they say when asked for help), "
            "and completion (what they say when the quest is done, for different outcomes)."
        ),
        tools=[],
        llm=LLM(model=model),
    )

    dialogue_task = Task(
        description=(
            f"Write quest-giver dialogue for '{npc_name}'.\n\n"
            f"Quest details:\n{quest}\n\n"
            "Write three dialogue sets:\n"
            "1. ACCEPTANCE: What they say when offering the quest (2-4 lines)\n"
            "2. HINTS: 2-3 different hint lines when the player asks for help\n"
            "3. COMPLETION: One line each for different completion outcomes "
            "(e.g., success, failure, unexpected resolution)"
        ),
        expected_output=(
            "Three dialogue sets — ACCEPTANCE (2-4 lines), HINTS (2-3 lines), "
            "and COMPLETION (one line per outcome) — all in the NPC's voice."
        ),
        agent=dialogue_writer,
    )

    return Crew(
        agents=[dialogue_writer],
        tasks=[dialogue_task],
        process=Process.sequential,
    )
