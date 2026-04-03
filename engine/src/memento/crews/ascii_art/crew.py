"""ASCII art crews — adversarial artist + critic pairs for scene and entity art."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.art_validation import validate_art

_SCENE_EXAMPLES = r"""
Example 1 — Ruined Tavern:
╔══════════════════════════════════╗
║     .  *  .      .    *   .     ║
║  .    ___________     .         ║
║      /           \        *     ║
║     |  TAVERN     |    .       ║
║     |  ___   ___  |            ║
║     | |   | |   | |   .        ║
║     | |___| |___| |            ║
║ ~~~~|_____________|~~~~         ║
║ ~~~~~~~~~~~~~~~~~~~~~~~~~~      ║
╚══════════════════════════════════╝

Example 2 — Dark Forest:
╔══════════════════════════════════╗
║  /\  .  *    /\     . *  /\    ║
║ /  \   /\   /  \  .    /  \   ║
║/    \_/  \_/    \_    /    \  ║
║ |  |  |  |  |  |  \__/  |  | ║
║ |  |  |  |  |  |  |  |  |  | ║
║~.|..|..|..|..|..|..|..|..|.~  ║
║.::.. .  .. ..::.  ..  .::.    ║
║ ~~ ^^^  ~~ path ~~  ^^^  ~~   ║
║....:::::......:::::......:::.. ║
║________________________________║
╚══════════════════════════════════╝

Example 3 — Dungeon Corridor:
╔══════════════════════════════════╗
║##############################  ║
║#............................#  ║
║#..╔════╗..........╔════╗...#  ║
║#..║    ║..........║    ║...#  ║
║#..║CELL║..........║CELL║...#  ║
║#..╚══╦═╝..........╚═╦══╝...#  ║
║#.....║..   ....   ..║......#  ║
║#.....║.. *torch*  ..║......#  ║
║#............................#  ║
║##############################  ║
╚══════════════════════════════════╝
""".strip()

_ENTITY_EXAMPLES = r"""
Example — Hooded Figure:
    .---.
   / o o \
   | --- |
   /|   |\
  / |   | \
 /__|   |__\
    |   |
    |___|
   /     \
  '-------'

Example — Skeletal Warrior:
   _____
  / x x \
  \_---_/
   |   |
  /|###|\
 / |###| \
   |   |
  /|   |\
 | |   | |
 |_|   |_|
""".strip()


def _make_artist(model: str, width: int, height: int, art_type: str) -> Agent:
    """Create the ASCII Artist agent."""
    if art_type == "scene":
        examples = _SCENE_EXAMPLES
        composition = (
            "Include environmental elements: buildings, trees, terrain features, "
            "water, paths, sky details. Frame scenes with box-drawing borders."
        )
    else:
        examples = _ENTITY_EXAMPLES
        composition = (
            "Create character silhouettes/portraits. Show distinguishing features "
            "(weapons, armor, cloaks, creature features). Center the figure."
        )

    return Agent(
        role="ASCII Artist",
        goal="Create atmospheric ASCII art for a dark fantasy MUD",
        backstory=(
            f"You create {width}x{height} ASCII art for a dark-fantasy permadeath MUD.\n\n"
            f"DIMENSION RULES (strict):\n"
            f"- Exactly {height} lines of output\n"
            f"- Each line exactly {width} characters wide (pad with spaces)\n"
            f"- No extra blank lines, no markdown fences, no commentary\n\n"
            f"CHARACTER PALETTE:\n"
            f"- Standard ASCII: # . : | / \\ - _ ~ ^ * @ ' \" and spaces\n"
            f"- Box-drawing: ═ ║ ╔ ╗ ╚ ╝ ╦ ╩ ╠ ╣ ╬ ─ │ ┌ ┐ └ ┘\n"
            f"- Block elements: ░ ▒ ▓ █ ▄ ▀\n"
            f"- NO tabs, NO emoji, NO characters outside this set\n\n"
            f"COMPOSITION:\n{composition}\n\n"
            f"REFERENCE EXAMPLES:\n{examples}\n\n"
            f"After generating art, use the validate_art tool to check dimensions "
            f"with expected_width={width} and expected_height={height}. "
            f"Fix any issues before submitting."
        ),
        tools=[validate_art],
        llm=LLM(model=model),
    )


def _make_critic(model: str) -> Agent:
    """Create the Art Critic agent."""
    return Agent(
        role="Art Critic",
        goal="Evaluate ASCII art quality and provide actionable revision feedback",
        backstory=(
            "You evaluate ASCII art for a dark-fantasy MUD game. Your criteria:\n\n"
            "1. DIMENSIONAL COMPLIANCE — correct width and height, no ragged lines\n"
            "2. ATMOSPHERIC QUALITY — does it evoke dark fantasy mood?\n"
            "3. READABILITY — can you tell what it depicts at a glance?\n"
            "4. PALETTE DISCIPLINE — only approved ASCII/box-drawing chars used\n"
            "5. COMPOSITION — good use of space, visual balance, no large empty areas\n\n"
            "If the art meets all criteria, respond with exactly 'APPROVED'.\n"
            "Otherwise, provide specific, actionable feedback — cite line numbers, "
            "describe what to add/remove/change, suggest specific characters to use."
        ),
        tools=[],
        llm=LLM(model=model),
    )


def make_scene_art_crew(
    location_name: str,
    description: str,
    mood: str,
    width: int = 35,
    height: int = 20,
) -> Crew:
    """Build an adversarial crew for location scene ASCII art."""
    model = get_model_for_crew("ascii_art")
    artist = _make_artist(model, width, height, "scene")
    critic = _make_critic(model)

    generate_task = Task(
        description=(
            f"Create ASCII art for the location '{location_name}'.\n\n"
            f"Description: {description}\n"
            f"Mood: {mood}\n\n"
            f"Output ONLY the raw ASCII art — exactly {height} lines, "
            f"each exactly {width} characters. No commentary, no fences."
        ),
        expected_output=f"Exactly {height} lines of ASCII art, each exactly {width} characters wide",
        agent=artist,
    )

    critique_task = Task(
        description=(
            "Evaluate the ASCII art above. Check dimensional compliance, "
            "atmospheric quality, readability, and palette discipline.\n\n"
            "If it meets all criteria, respond with exactly: APPROVED\n"
            "Otherwise, provide specific revision feedback with line numbers."
        ),
        expected_output="Either 'APPROVED' or specific revision feedback",
        agent=critic,
        context=[generate_task],
    )

    revise_task = Task(
        description=(
            "Revise the ASCII art based on the critic's feedback. "
            "If the critique was 'APPROVED', reproduce the art unchanged.\n\n"
            f"Output ONLY the raw ASCII art — exactly {height} lines, "
            f"each exactly {width} characters. No commentary."
        ),
        expected_output=f"Exactly {height} lines of revised ASCII art, each exactly {width} characters wide",
        agent=artist,
        context=[generate_task, critique_task],
    )

    final_review_task = Task(
        description=(
            "Run the validate_art tool on the revised art with "
            f"expected_width={width} and expected_height={height}. "
            "If validation fails, fix the issues and re-validate. "
            "Output ONLY the final validated ASCII art."
        ),
        expected_output="Final ASCII art that passes dimensional validation",
        agent=artist,
        context=[revise_task],
    )

    return Crew(
        agents=[artist, critic],
        tasks=[generate_task, critique_task, revise_task, final_review_task],
        process=Process.sequential,
    )


def make_entity_art_crew(
    entity_name: str,
    entity_type: str,
    description: str,
    width: int = 20,
    height: int = 12,
) -> Crew:
    """Build an adversarial crew for entity portrait ASCII art."""
    model = get_model_for_crew("ascii_art")
    artist = _make_artist(model, width, height, "entity")
    critic = _make_critic(model)

    generate_task = Task(
        description=(
            f"Create ASCII art portrait of '{entity_name}' ({entity_type}).\n\n"
            f"Description: {description}\n\n"
            f"Output ONLY the raw ASCII art — exactly {height} lines, "
            f"each exactly {width} characters. No commentary, no fences."
        ),
        expected_output=f"Exactly {height} lines of ASCII art, each exactly {width} characters wide",
        agent=artist,
    )

    critique_task = Task(
        description=(
            "Evaluate the ASCII art portrait above. Check dimensional compliance, "
            "recognizability, atmospheric quality, and palette discipline.\n\n"
            "If it meets all criteria, respond with exactly: APPROVED\n"
            "Otherwise, provide specific revision feedback with line numbers."
        ),
        expected_output="Either 'APPROVED' or specific revision feedback",
        agent=critic,
        context=[generate_task],
    )

    revise_task = Task(
        description=(
            "Revise the ASCII art based on the critic's feedback. "
            "If the critique was 'APPROVED', reproduce the art unchanged.\n\n"
            f"Output ONLY the raw ASCII art — exactly {height} lines, "
            f"each exactly {width} characters. No commentary."
        ),
        expected_output=f"Exactly {height} lines of revised ASCII art, each exactly {width} characters wide",
        agent=artist,
        context=[generate_task, critique_task],
    )

    final_review_task = Task(
        description=(
            "Run the validate_art tool on the revised art with "
            f"expected_width={width} and expected_height={height}. "
            "If validation fails, fix the issues and re-validate. "
            "Output ONLY the final validated ASCII art."
        ),
        expected_output="Final ASCII art that passes dimensional validation",
        agent=artist,
        context=[revise_task],
    )

    return Crew(
        agents=[artist, critic],
        tasks=[generate_task, critique_task, revise_task, final_review_task],
        process=Process.sequential,
    )
