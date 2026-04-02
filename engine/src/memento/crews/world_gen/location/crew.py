"""Location crew — builds out a single location with layout, description, and secrets."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.kg import search_world, create_entity, create_edge


def make_location_crew(location_plan: str, region_name: str) -> Crew:
    """Build a crew that fully designs a location and persists it to the KG."""
    model = get_model_for_crew("location")

    architect = Agent(
        role="Architect",
        goal="Design the layout, structure, and points of interest for the location",
        backstory=(
            "You are a dungeon architect and level designer for a dark fantasy RPG. You create "
            "locations with clear spatial logic, meaningful points of interest, and layouts that "
            "reward careful exploration. Every room and area serves a narrative or gameplay purpose."
        ),
        tools=[create_entity, create_edge],
        llm=LLM(model=model),
    )

    scene_painter = Agent(
        role="Scene Painter",
        goal="Write evocative arrival and exploration text that immerses the player in the location",
        backstory=(
            "You are a prose stylist specialising in atmospheric description for interactive "
            "fiction. You write vivid, sensory-rich text that establishes mood immediately, "
            "rewards close reading, and never wastes a word."
        ),
        tools=[search_world],
        llm=LLM(model=model),
    )

    secret_keeper = Agent(
        role="Secret Keeper",
        goal="Plant hidden content, discoverable secrets, and lore fragments throughout the location",
        backstory=(
            "You are a lore designer who hides layers of meaning beneath the surface of every "
            "location. You create secrets that reward curious players — hidden passages, "
            "cryptic inscriptions, buried history — and ensure each one connects to the larger world."
        ),
        tools=[search_world],
        llm=LLM(model=model),
    )

    architect_task = Task(
        description=(
            f"Design location '{location_plan}' in region '{region_name}'. "
            "Create it as a Location entity in the KG using create_entity, then use create_edge "
            "to link it to the region with a LOCATED_IN relationship. "
            "Define the layout: key areas, points of interest, NPCs present, items found, "
            "and any sub-areas worth exploring.\n\n"
            "ALSO generate a 2D ASCII tile grid for this location as JSON. "
            "The grid must be exactly 40 columns wide by 20 rows tall (width*height = 800 tiles). "
            "Use these tile characters:\n"
            "  # = wall      . = floor     + = door/exit  T = table\n"
            "  B = bar/counter  ~ = water  , = grass      : = gravel\n"
            "  = = road      ^ = stairs\n"
            "Place walls (#) around the entire perimeter. Fill the interior with floor tiles (.) "
            "and thematic features that match the location description. Include NPC spawn points, "
            "item locations, and exit positions that match the location's key areas.\n\n"
            "Output the tile grid as a JSON block at the very end of your response, "
            "wrapped in ```json code fences, matching this exact schema:\n"
            "{\n"
            '  "width": 40,\n'
            '  "height": 20,\n'
            '  "tiles": ["#", ".", "+", ...],  // flat string array, row-major, length = width*height\n'
            '  "npcs": [{"x": 5, "y": 3, "ch": "K", "name": "Barkeeper"}],\n'
            '  "items": [{"x": 10, "y": 7, "ch": "!", "name": "Health Potion"}],\n'
            '  "exits": [{"x": 39, "y": 10, "ch": "+", "direction": "east", "target": "unknown"}],\n'
            '  "spawn": {"x": 20, "y": 18}\n'
            "}"
        ),
        expected_output=(
            "Location design including: name, type, key areas/rooms, points of interest, "
            "notable NPCs, items, and the KG entity ID after creation. "
            "Followed by a ```json code block containing the RoomMap tile grid with fields: "
            "width (40), height (20), tiles (flat array of 800 single-char strings), "
            "npcs (array of {x,y,ch,name}), items (array of {x,y,ch,name}), "
            "exits (array of {x,y,ch,direction,target}), and spawn ({x,y})."
        ),
        agent=architect,
    )

    scene_painter_task = Task(
        description=(
            "Using the architectural design, write a vivid description for this location. "
            "Include: an arrival description (what the player first sees/smells/hears), "
            "exploration text for 2-3 key areas, and atmospheric details that establish tone."
        ),
        expected_output=(
            "Descriptive text including: arrival description (2-3 sentences), "
            "exploration text for key areas, and atmospheric/sensory details."
        ),
        agent=scene_painter,
        context=[architect_task],
    )

    secret_keeper_task = Task(
        description=(
            "Add hidden content and discoverable secrets to this location. "
            "Design: 1-2 hidden passages or concealed areas, at least one piece of discoverable "
            "lore (inscription, journal entry, environmental storytelling), and one secret that "
            "connects to the wider region or world lore."
        ),
        expected_output=(
            "Secrets manifest including: hidden areas with discovery conditions, "
            "lore fragments with their in-world presentation, and connection to broader world lore."
        ),
        agent=secret_keeper,
        context=[scene_painter_task],
    )

    return Crew(
        agents=[architect, scene_painter, secret_keeper],
        tasks=[architect_task, scene_painter_task, secret_keeper_task],
        process=Process.sequential,
    )
