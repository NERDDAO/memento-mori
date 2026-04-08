"""Portraitist crew — cellular automata pixel sprites for entities."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.art_tools import generate_sprite_tool, select_palette_tool
from memento.tools.sprite_validation import validate_sprite


def make_portraitist_crew(
    entity_name: str,
    entity_type: str,
    description: str,
    labels: list[str],
    biome: str = "default",
    mood: str = "dark",
    icon_mode: bool = False,
) -> Crew:
    """Build a crew that generates pixel sprite art for entities."""
    model = get_model_for_crew("ascii_art")
    labels_json = str(labels).replace("'", '"')

    if icon_mode:
        size_desc = "8x8 pixel icon"
        size_px = 8
    elif entity_type == "npc" or "NPC" in labels or "Player" in labels:
        size_desc = "32x32 pixel portrait"
        size_px = 32
    else:
        size_desc = "16x16 pixel sprite"
        size_px = 16

    artist = Agent(
        role="Sprite Artist",
        goal=f"Generate a {size_desc} for a dark fantasy entity",
        backstory=(
            f"You create pixel sprites for a dark-fantasy permadeath MUD.\n\n"
            f"WORKFLOW:\n"
            f"1. Use select_palette tool with biome='{biome}' and mood='{mood}' to get colors\n"
            f"2. Use generate_sprite tool with entity_labels='{labels_json}' and biome='{biome}' "
            f"to generate a sprite candidate\n"
            f"3. Evaluate if the sprite's template and colors fit the entity description\n"
            f"4. If not satisfied, re-generate with a different seed\n"
            f"5. Use validate_sprite tool to check dimensions (expected_w={size_px}, expected_h={size_px})\n"
            f"6. Output the final sprite_b64 string and dimensions\n\n"
            f"Generate up to 4 candidates (seeds 1-4) and pick the best one.\n"
            f"Output format: JSON with keys sprite_b64, width, height"
        ),
        tools=[generate_sprite_tool, select_palette_tool, validate_sprite],
        llm=LLM(model=model),
    )

    critic = Agent(
        role="Style Critic",
        goal="Ensure sprite quality and consistency with entity description",
        backstory=(
            "You evaluate pixel sprites for a dark-fantasy MUD. Your criteria:\n\n"
            "1. DIMENSION COMPLIANCE — correct pixel size\n"
            "2. SILHOUETTE READABILITY — can you tell what the entity is at a glance?\n"
            "3. PALETTE CONSISTENCY — colors match the biome/mood\n"
            "4. DESCRIPTION MATCH — sprite template fits the entity type\n\n"
            "If the sprite meets all criteria, respond with exactly 'APPROVED'.\n"
            "Otherwise, suggest re-generation with different seed or template."
        ),
        tools=[],
        llm=LLM(model=model),
    )

    generate_task = Task(
        description=(
            f"Generate a {size_desc} for '{entity_name}' ({entity_type}).\n\n"
            f"Description: {description}\n"
            f"Labels: {labels_json}\n"
            f"Biome: {biome}\n\n"
            f"Use the generate_sprite tool to create candidates. Pick the best one.\n"
            f"Validate with validate_sprite (expected_w={size_px}, expected_h={size_px}).\n"
            f'Output JSON: {{"sprite_b64": "...", "width": {size_px}, "height": {size_px}}}'
        ),
        expected_output=f"JSON with sprite_b64, width={size_px}, height={size_px}",
        agent=artist,
    )

    critique_task = Task(
        description=(
            f"Evaluate the sprite for '{entity_name}'. Check that the template "
            f"choice fits a {entity_type}, the palette matches {biome}/{mood}, "
            f"and the silhouette is readable at {size_px}x{size_px}.\n\n"
            "If it meets all criteria, respond with exactly: APPROVED\n"
            "Otherwise, suggest re-generation with a different seed."
        ),
        expected_output="Either 'APPROVED' or specific feedback",
        agent=critic,
        context=[generate_task],
    )

    revise_task = Task(
        description=(
            "If the critic approved, output the same sprite JSON unchanged.\n"
            "If the critic suggested changes, re-generate with a different seed "
            "and validate again.\n\n"
            f'Output JSON: {{"sprite_b64": "...", "width": {size_px}, "height": {size_px}}}'
        ),
        expected_output=f"JSON with sprite_b64, width={size_px}, height={size_px}",
        agent=artist,
        context=[generate_task, critique_task],
    )

    return Crew(
        agents=[artist, critic],
        tasks=[generate_task, critique_task, revise_task],
        process=Process.sequential,
    )
