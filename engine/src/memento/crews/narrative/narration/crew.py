"""Narration crew — generates game narrative from context and events."""

from crewai import Agent, Crew, Task, Process, LLM
from memento.config import load_config, get_model_for_crew
from memento.sanitize import sanitize_for_prompt
from memento.tools.kg import search_world


def make_narration_crew(
    action: str, context: str, events: str, mode: str = "action"
) -> Crew:
    """Build a narration crew.

    mode: 'action' (normal turn), 'intro' (game start), 'rejection' (implausible action)
    """
    config = load_config()
    tone = config["game"]["tone"]
    model = get_model_for_crew("narration")
    action = sanitize_for_prompt(action, max_length=500)

    narrator = Agent(
        role="Master Narrator",
        goal="Deliver immersive, consequential narrative for a permadeath MUD",
        backstory=(
            f"You write in the style of: {tone}. You never override player intent. "
            "You describe consequences, not dictate actions. Every word matters — "
            "this is a permadeath game. Death is permanent. Make players feel the weight."
        ),
        tools=[search_world],
        llm=LLM(model=model),
    )

    npc_voice = Agent(
        role="NPC Voice Actor",
        goal="Give each NPC a distinct voice consistent with their personality",
        backstory=(
            "You specialize in NPC dialogue. Each NPC should sound different — "
            "a gruff dwarf, a sly merchant, a nervous guard. Match their personality "
            "and disposition toward the player."
        ),
        tools=[],
        llm=LLM(model=model),
    )

    slopword_filter = Agent(
        role="Prose Quality Editor",
        goal="Remove AI-isms, purple prose, and generic filler from narrative text",
        backstory=(
            "You edit RPG narrative text. Remove phrases like 'certainly', 'indeed', "
            "'it's worth noting', 'a sense of', 'tapestry'. Cut unnecessary adverbs. "
            "Keep the prose tight, specific, and atmospheric. Never add content — only cut."
        ),
        tools=[],
        llm=LLM(model=model),
    )

    narrate_task = Task(
        description=(
            f"Write the narrative response for this game turn.\n\n"
            f"Player action: {action}\n\n"
            f"Scene context:\n{context[:2000]}\n\n"
            f"Detected events:\n{events}\n\n"
            f"Mode: {mode}\n\n"
            "Write 2-4 paragraphs of immersive narrative. Include NPC dialogue if "
            "NPCs are involved. Describe what the player sees, hears, and feels."
        ),
        expected_output="2-4 paragraphs of immersive RPG narrative prose",
        agent=narrator,
    )

    voice_task = Task(
        description=(
            "Review the narrative and ensure all NPC dialogue is distinctive. "
            "Each NPC should have a unique voice. Rewrite any generic dialogue."
        ),
        expected_output="Narrative with distinctive NPC voices",
        agent=npc_voice,
        context=[narrate_task],
    )

    filter_task = Task(
        description=(
            "Edit the narrative text. Remove any AI-isms, purple prose, or generic "
            "filler. Keep the prose tight and atmospheric. Do not add content."
        ),
        expected_output="Clean, polished narrative prose",
        agent=slopword_filter,
        context=[voice_task],
    )

    return Crew(
        agents=[narrator, npc_voice, slopword_filter],
        tasks=[narrate_task, voice_task, filter_task],
        process=Process.sequential,
    )
