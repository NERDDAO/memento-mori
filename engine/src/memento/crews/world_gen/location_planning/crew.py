"""Location planning crew — converts a region concept into a concrete location list."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew


def make_location_planning_crew(region_concept: str, scaffold: str = "") -> Crew:
    """Build a crew that plans specific locations for a region."""
    model = get_model_for_crew("location_planning")

    location_planner = Agent(
        role="Location Planner",
        goal="Plan a set of specific, varied locations that bring a region concept to life",
        backstory=(
            "You are a level designer and narrative planner who translates high-level region "
            "concepts into concrete, memorable locations. You ensure each location serves a "
            "distinct purpose — refuge, danger, mystery, commerce — and that the set as a whole "
            "creates a satisfying exploration loop."
        ),
        llm=LLM(model=model),
    )

    planning_task = Task(
        description=(
            f"Given this region concept:\n\n{region_concept}\n\n"
            "Plan 3-5 specific locations with names and types. For each location provide: "
            "name, type (town, dungeon, landmark, wilderness, etc.), one-sentence purpose, "
            "and a brief note on how it connects spatially or narratively to the others."
        ),
        expected_output=(
            "A structured list of 3-5 locations, each with: name, type, purpose, and "
            "spatial/narrative connection to the region. Formatted clearly so each location "
            "can be handed off for detailed design."
        ),
        agent=location_planner,
    )
    if scaffold:
        planning_task.description += (
            "\n\nSCAFFOLD (use as starting point, modify freely, or discard if it doesn't fit):\n"
            + scaffold
        )

    return Crew(
        agents=[location_planner],
        tasks=[planning_task],
        process=Process.sequential,
    )
