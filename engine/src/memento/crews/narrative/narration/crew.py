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
            "- DO tag NPCs with @username when they would notice or react to something.\n"
            "- Example good output: 'The tavern falls silent as blood drips on the floorboards. "
            "@roric sets down the glass he was cleaning. @elara's hand moves to her blade.'\n"
            "- Example bad output: 'Roric says \\'What have you done?\\' as he steps back in horror.' "
            "(NEVER write NPC speech)\n"
            "- The @tags tell the NPC agents to respond. You provide the environmental context, "
            "they provide their own reactions."
        ),
        tools=[search_world],
        llm=LLM(model=model),
    )

    npc_cue = Agent(
        role="NPC Cue Writer",
        goal="Ensure all NPCs in the scene are properly tagged with @username cues, never writing their dialogue",
        backstory=(
            "You review environment narration and verify that every NPC who would notice or react "
            "to the scene is tagged with @username. You NEVER write NPC dialogue or NPC actions. "
            "Your only job is to ensure the environmental narration contains the correct @tags so "
            "the NPC agents know to respond. If an NPC is missing a tag, add an environmental cue "
            "that includes the tag (e.g., '@mira's eyes widen at the smoke'). Never put words in "
            "an NPC's mouth."
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
            f"Write the environment narration for this game turn.\n\n"
            f"Player action: {action}\n\n"
            f"Scene context:\n{context[:2000]}\n\n"
            f"Detected events:\n{events}\n\n"
            f"Mode: {mode}\n\n"
            "Write 2-4 paragraphs of immersive environment narration. Describe what the player "
            "sees, hears, smells, and feels. Tag NPCs with @username when they would notice or "
            "react to something. NEVER write NPC dialogue or NPC actions — they respond themselves."
        ),
        expected_output=(
            "2-4 paragraphs of environment-only RPG narrative prose with @username tags for NPCs"
        ),
        agent=narrator,
    )

    npc_cue_task = Task(
        description=(
            "Review the environment narration. Verify every NPC present in the scene is tagged "
            "with @username. If any NPC who would notice the events is missing a tag, add a brief "
            "environmental cue that includes the tag. NEVER write NPC dialogue or NPC actions. "
            "Only add or adjust environmental @tag lines."
        ),
        expected_output=(
            "Environment narration with complete @username tags for all relevant NPCs, "
            "no NPC dialogue or NPC actions"
        ),
        agent=npc_cue,
        context=[narrate_task],
    )

    filter_task = Task(
        description=(
            "Edit the narrative text. Remove any AI-isms, purple prose, or generic "
            "filler. Keep the prose tight and atmospheric. Do not add content."
        ),
        expected_output="Clean, polished narrative prose",
        agent=slopword_filter,
        context=[npc_cue_task],
    )

    return Crew(
        agents=[narrator, npc_cue, slopword_filter],
        tasks=[narrate_task, npc_cue_task, filter_task],
        process=Process.sequential,
    )
