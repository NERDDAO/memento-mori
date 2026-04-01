"""Action classification crew — categorizes player actions into event types."""

from crewai import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew


CATEGORIES = [
    "movement", "combat", "social", "inventory",
    "quest", "world_change", "other",
]


def make_classification_crew(action: str, context: str) -> Crew:
    """Build a classification crew for a player action."""
    model = get_model_for_crew("classification")

    classifier = Agent(
        role="Action Classifier",
        goal="Quickly categorize a player action into event domains",
        backstory=(
            "You triage player actions into categories. Be inclusive — flag any "
            "category that MIGHT apply. Categories: "
            + ", ".join(CATEGORIES)
        ),
        tools=[],
        llm=LLM(model=model),
    )

    classify_task = Task(
        description=(
            f"Given this context:\n{context[:1000]}\n\n"
            f"Classify this player action: '{action}'\n\n"
            f"Return ONLY a comma-separated list of applicable categories from: "
            f"{', '.join(CATEGORIES)}\n"
            f"Example: 'movement, social' or 'combat' or 'inventory, quest'"
        ),
        expected_output="Comma-separated list of event categories",
        agent=classifier,
    )

    return Crew(
        agents=[classifier],
        tasks=[classify_task],
        process=Process.sequential,
    )
