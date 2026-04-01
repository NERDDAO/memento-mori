"""Balance review crew — reviews a set of items for game balance."""

from crewai import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew


def make_balance_review_crew(items: str) -> Crew:
    """Build a balance review crew for a set of items."""
    model = get_model_for_crew("item_balance")

    balance_reviewer = Agent(
        role="Balance Reviewer",
        goal="Ensure item sets are balanced and internally consistent for a dark fantasy RPG",
        backstory=(
            "You review item sets for game balance in a dark fantasy RPG. You check that rarities "
            "match power levels, that no single item dominates its slot, and that consumables are "
            "appropriately scarce. You suggest concrete adjustments rather than vague critique, "
            "keeping the game fair and engaging."
        ),
        tools=[],
        llm=LLM(model=model),
    )

    balance_task = Task(
        description=(
            f"Review these items for balance:\n\n{items}\n\n"
            "Check that: rarities match power levels, no item is strictly better than all others "
            "of the same type, consumables have appropriate scarcity. Suggest adjustments if needed."
        ),
        expected_output=(
            "A balance review with: overall assessment, any flagged imbalances, and specific "
            "adjustment suggestions for each flagged item (or confirmation that the set is balanced)."
        ),
        agent=balance_reviewer,
    )

    return Crew(
        agents=[balance_reviewer],
        tasks=[balance_task],
        process=Process.sequential,
    )
