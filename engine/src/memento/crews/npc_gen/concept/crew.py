"""NPC concept crew — creates name, appearance, backstory, and personality."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.kg import search_world


def make_concept_crew(
    npc_role: str,
    location_name: str,
    region_context: str = "",
    scaffold: str = "",
) -> Crew:
    """Build a crew that fleshes out an NPC's concept and personality."""
    model = get_model_for_crew("npc_concept")

    concept_artist = Agent(
        role="NPC Concept Artist",
        goal="Create a vivid, believable NPC with a compelling name, appearance, and backstory",
        backstory=(
            "You craft the physical and historical identity of NPCs for a dark fantasy RPG. "
            "You draw on world lore to root characters in the setting, giving them names that "
            "fit the region and histories that explain their current role."
        ),
        tools=[search_world],
        llm=LLM(model=model),
    )

    personality_writer = Agent(
        role="NPC Personality Writer",
        goal="Define an NPC's inner life: traits, speech, secrets, and motivations",
        backstory=(
            "You give NPCs their voice and soul. You take a physical concept and add the "
            "psychological layers that make encounters memorable — quirks, hidden agendas, "
            "and the driving desire that shapes every interaction."
        ),
        tools=[],
        llm=LLM(model=model),
    )

    concept_task = Task(
        description=(
            f"Create an NPC who fills the role of '{npc_role}' at '{location_name}'. "
            f"Regional context: {region_context}\n\n"
            "Give them a name, physical description, and backstory."
        ),
        expected_output=(
            "An NPC concept with: full name, physical description (3-5 sentences), "
            "and a backstory (2-3 sentences) explaining how they came to hold this role."
        ),
        agent=concept_artist,
    )
    if scaffold:
        concept_task.description += (
            "\n\nSCAFFOLD (use as starting point, modify freely, or discard if it doesn't fit):\n"
            + scaffold
        )

    personality_task = Task(
        description=(
            "Define this NPC's personality: traits, speech patterns, a secret, "
            "and their primary motivation.\n\n"
            "Output as a JSON object with these keys:\n"
            '- "personality": 2-3 sentence personality description\n'
            '- "traits": array of 3-5 personality trait words\n'
            '- "speech_pattern": how they talk (accent, vocabulary, mannerisms)\n'
            '- "secret": one hidden fact they keep\n'
            '- "motivation": their primary motivation\n'
            '- "disposition": one of hostile/unfriendly/neutral/friendly/allied\n'
            "Include any additional color after the JSON."
        ),
        expected_output=(
            "A JSON object with personality, traits, speech_pattern, secret, motivation, "
            "and disposition fields, followed by optional additional flavor text."
        ),
        agent=personality_writer,
        context=[concept_task],
    )

    return Crew(
        agents=[concept_artist, personality_writer],
        tasks=[concept_task, personality_task],
        process=Process.sequential,
    )
