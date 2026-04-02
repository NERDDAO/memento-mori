"""Quest stages crew — breaks a quest into discrete stages with completion conditions."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew


def make_quest_stage_crew(quest_concept: str) -> Crew:
    """Build a crew that structures a quest concept into 3-5 stages."""
    model = get_model_for_crew("quest_stages")

    stage_builder = Agent(
        role="Quest Stage Builder",
        goal="Break a quest into 3-5 clear stages with concrete completion conditions",
        backstory=(
            "You structure quests for a dark fantasy RPG. You take a quest concept and "
            "break it into discrete stages that guide the player without hand-holding. "
            "Each stage has a clear objective and measurable completion condition. "
            "Stages should feel like natural story beats, not arbitrary checkboxes."
        ),
        tools=[],
        llm=LLM(model=model),
    )

    stages_task = Task(
        description=(
            f"Break this quest concept into 3-5 stages:\n\n{quest_concept}\n\n"
            "For each stage provide:\n"
            "- Stage name\n"
            "- Objective (what the player must do)\n"
            "- Completion condition (how the game knows it's done)\n"
            "- Optional: hints or failure states"
        ),
        expected_output=(
            "3-5 quest stages, each with: stage name, objective, "
            "and completion condition. Optional hints or failure states."
        ),
        agent=stage_builder,
    )

    return Crew(
        agents=[stage_builder],
        tasks=[stages_task],
        process=Process.sequential,
    )
