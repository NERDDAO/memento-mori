"""Exit connection crew — wires locations together with EXIT_TO edges."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.kg import create_edge, search_world


def make_exit_connection_crew(locations: str, region_name: str, scaffold: str = "") -> Crew:
    """Build a crew that connects locations with EXIT_TO edges in the KG."""
    model = get_model_for_crew("exit_connection")

    exit_connector = Agent(
        role="Exit Connector",
        goal="Connect locations with logical EXIT_TO edges based on spatial and narrative logic",
        backstory=(
            "You are a world cartographer who understands how spaces relate to one another. "
            "You create connections between locations that make geographic sense, provide "
            "meaningful player choices, and avoid creating isolated dead-ends. Every exit "
            "should feel earned and purposeful."
        ),
        tools=[create_edge, search_world],
        llm=LLM(model=model),
    )

    connection_task = Task(
        description=(
            f"Connect these locations in region '{region_name}' with EXIT_TO edges:\n\n"
            f"{locations}\n\n"
            "Use search_world to look up each location, then use create_edge to create "
            "EXIT_TO relationships between locations that should logically connect. "
            "Consider: spatial proximity, narrative flow, player progression, and avoid "
            "creating isolated nodes. Each location should have at least one exit."
        ),
        expected_output=(
            "A summary of all EXIT_TO connections created, listing each pair as "
            "'LocationA -> LocationB' with a brief rationale for why they connect. "
            "Confirm all locations have at least one exit."
        ),
        agent=exit_connector,
    )
    if scaffold:
        connection_task.description += (
            "\n\nSCAFFOLD (use as starting point, modify freely, or discard if it doesn't fit):\n"
            + scaffold
        )

    return Crew(
        agents=[exit_connector],
        tasks=[connection_task],
        process=Process.sequential,
    )
