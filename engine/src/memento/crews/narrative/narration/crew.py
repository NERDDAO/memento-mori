"""Narration crew — generates game narrative from context and events."""

from memento.core import Agent, Crew, Task, Process, LLM
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
        goal="Deliver immersive, consequential environment narration for a permadeath MUD",
        backstory=(
            f"You write in the style of: {tone}. You never override player intent. "
            "You describe consequences, not dictate actions. Every word matters — "
            "this is a permadeath game. Death is permanent. Make players feel the weight.\n\n"
            "CRITICAL RULES FOR ENVIRONMENT NARRATION:\n"
            "- NEVER write dialogue for NPCs. They will speak for themselves.\n"
            "- NEVER write actions for NPCs (e.g., 'Roric reaches for his hammer'). They decide their own actions.\n"
            "- DO describe the environment, atmosphere, sounds, smells, weather, lighting.\n"
            "- Do NOT use @tags or mention NPC names directly — NPC triggering is handled separately.\n"
            "- Refer to NPCs by description, not name (e.g., 'the barkeep' not 'Roric')."
        ),
        tools=[search_world],
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
            f"Write the environment narration for this game turn.\n\n"
            f"Player action: {action}\n\n"
            f"Scene context:\n{context[:2000]}\n\n"
            f"Detected events:\n{events}\n\n"
            f"Mode: {mode}\n\n"
            "Write 1-2 sentences of ambient environment narration. Describe what the player "
            "senses — sounds, smells, atmosphere, weather. Keep it tight and evocative. "
            "Do NOT mention NPC names or use @tags — NPC triggering is handled separately."
        ),
        expected_output=(
            "1-2 sentences of ambient environment narration, no NPC names or @tags"
        ),
        agent=narrator,
    )

    filter_task = Task(
        description=(
            "Edit the narrative text. Remove any AI-isms, purple prose, or generic "
            "filler. Keep the prose tight and atmospheric. Do not add content. "
            "Do NOT add @username tags or NPC names — NPC triggering is handled separately."
        ),
        expected_output="Clean, polished narrative prose without @tags",
        agent=slopword_filter,
        context=[narrate_task],
    )

    return Crew(
        agents=[narrator, slopword_filter],
        tasks=[narrate_task, filter_task],
        process=Process.sequential,
    )
