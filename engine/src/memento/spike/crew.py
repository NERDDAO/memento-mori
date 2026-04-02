"""Spike crew — validates CrewAI + Bonfires KG integration."""

from memento.core import Agent, Crew, Task, Process
from memento.core import LLM
from memento.tools.kg import create_entity, search_world


def make_spike_crew() -> Crew:
    """Build the spike crew programmatically."""
    world_painter = Agent(
        role="World Painter",
        goal="Create vivid, atmospheric locations for a dark fantasy RPG",
        backstory=(
            "You are a world-builder for a permadeath MUD. Every location you create "
            "should feel lived-in, dangerous, and full of story hooks. Use the tools "
            "to create entities in the knowledge graph and search for existing lore."
        ),
        tools=[create_entity, search_world],
        llm=LLM(model="openrouter/anthropic/claude-sonnet-4"),
        verbose=True,
    )

    create_location = Task(
        description=(
            "Create a tavern at the edge of a dark forest. First, use the Create Game Entity "
            "tool to register it in the knowledge graph as a Location with a compelling name. "
            "Then search for any existing lore about dark forests or taverns. Finally, write "
            "a vivid 2-3 paragraph description of what a traveler sees when they first enter."
        ),
        expected_output=(
            "A rich description of the tavern including its name, atmosphere, notable "
            "features, and any hints of danger. The location must be registered in the KG."
        ),
        agent=world_painter,
    )

    return Crew(
        agents=[world_painter],
        tasks=[create_location],
        process=Process.sequential,
        verbose=True,
    )
