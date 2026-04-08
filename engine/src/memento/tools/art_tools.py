"""CrewAI-accessible art generation tools.

These wrap the procgen toolkit as @tool functions that crew agents can invoke.
"""

import json

from crewai.tools import tool

from memento.tools.procgen.wfc import generate_terrain_scaffold
from memento.tools.procgen.sprite_gen import generate_sprite
from memento.tools.procgen.palette import select_palette as _select_palette
from memento.tools.procgen.templates import select_template


@tool("generate_terrain")
def generate_terrain_tool(biome: str, width: int = 35, height: int = 20, seed: int = 0) -> str:
    """Generate an ASCII terrain scaffold using Wave Function Collapse.

    Args:
        biome: Biome name (crypt, forest, village, ruins, default).
        width: Grid width in characters.
        height: Grid height in characters.
        seed: Random seed (0 for random).

    Returns:
        Multi-line ASCII string of the terrain scaffold.
    """
    actual_seed = seed if seed != 0 else None
    return generate_terrain_scaffold(biome, width=width, height=height, seed=actual_seed)


@tool("generate_sprite")
def generate_sprite_tool(entity_labels: str, biome: str = "default", seed: int = 0) -> str:
    """Generate a pixel sprite silhouette for an entity.

    Args:
        entity_labels: JSON array of entity labels, e.g. '["NPC"]' or '["Weapon", "Item"]'.
        biome: Biome name for palette selection.
        seed: Random seed (0 for random).

    Returns:
        JSON with sprite_b64, width, height.
    """
    labels = json.loads(entity_labels)
    template = select_template(labels)
    palette = _select_palette(biome)
    actual_seed = seed if seed != 0 else None
    sprite_b64 = generate_sprite(template, palette, seed=actual_seed)
    return json.dumps({
        "sprite_b64": sprite_b64,
        "width": template.size,
        "height": template.size,
        "template": template.name,
    })


@tool("select_palette")
def select_palette_tool(biome: str, mood: str = "") -> str:
    """Get the color palette for a biome/mood combination.

    Args:
        biome: Biome name (crypt, forest, village, ruins, default).
        mood: Optional mood modifier (dark, eerie, peaceful, hostile).

    Returns:
        JSON with primary, accent, light color arrays and wall/floor/water colors.
    """
    palette = _select_palette(biome, mood)
    return json.dumps({
        "primary": palette.primary,
        "accent": palette.accent,
        "light": palette.light,
        "wall": palette.wall,
        "floor": palette.floor,
        "water": palette.water,
    })
