"""Art generation dispatcher.

Single entry point for all art generation. Routes to the appropriate crew
(cartographer for locations, portraitist for NPCs/items) and persists
results as entity attributes on the KG.
"""

import json
import logging
import re
from datetime import datetime, timezone

from memento.crews.cartographer.crew import make_cartographer_crew
from memento.crews.portraitist.crew import make_portraitist_crew

logger = logging.getLogger(__name__)


def _get_kg_client():
    """Get the KG client. Separated for test mocking."""
    from memento.client import get_client
    return get_client()


def _parse_scene_art(raw: str, expected_w: int, expected_h: int) -> tuple[str, int, int]:
    """Extract ASCII art from crew output, stripping commentary and fences."""
    lines = raw.strip().split("\n")

    # If there's a fenced block, extract only the content inside it
    fence_start = None
    for i, line in enumerate(lines):
        if line.startswith("```"):
            fence_start = i
            break
    if fence_start is not None:
        inner = lines[fence_start + 1:]
        fence_end = None
        for i, line in enumerate(inner):
            if line.startswith("```"):
                fence_end = i
                break
        lines = inner[:fence_end] if fence_end is not None else inner

    # Filter out lines that look like commentary
    art_chars = set("#.:|/\\-_~^*@'\" ═║╔╗╚╝╦╩╠╣╬─│┌┐└┘░▒▓█▄▀+◊†↑♣T=")
    art_lines: list[str] = []
    for line in lines:
        if not line:
            continue
        if all(c in art_chars for c in line):
            art_lines.append(line)
        elif len(line) >= expected_w * 0.8:
            art_lines.append(line[:expected_w])

    # Pad/trim to expected dimensions
    while len(art_lines) < expected_h:
        art_lines.append(" " * expected_w)
    art_lines = art_lines[:expected_h]
    art_lines = [l.ljust(expected_w)[:expected_w] for l in art_lines]

    art_str = "\n".join(art_lines)
    return art_str, expected_w, len(art_lines)


def _parse_sprite_result(raw: str) -> dict:
    """Extract sprite JSON from crew output."""
    match = re.search(r'\{[^}]*"sprite_b64"[^}]*\}', raw, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(raw)


def generate_entity_art(
    entity_uid: str,
    name: str,
    entity_type: str,
    description: str,
    labels: list[str],
    biome: str = "default",
    mood: str = "dark",
) -> None:
    """Generate all art for an entity and persist to KG.

    Called from NPC/item/world gen flows as a background thread target.
    """
    try:
        client = _get_kg_client()
        attrs: dict = {}
        now = datetime.now(timezone.utc).isoformat()

        if entity_type == "location":
            crew = make_cartographer_crew(
                location_name=name,
                description=description,
                mood=mood,
                biome=biome,
                width=35,
                height=20,
            )
            result = crew.kickoff()
            art_str, w, h = _parse_scene_art(result.raw, 35, 20)
            attrs["scene_art"] = art_str
            attrs["scene_art_w"] = w
            attrs["scene_art_h"] = h
            glyph_map = {
                "crypt": ("†", "#8b0000"),
                "forest": ("♣", "#2d5a2d"),
                "village": ("⌂", "#cd853f"),
                "ruins": ("Ω", "#6b6b6b"),
                "default": ("·", "#4a4a5e"),
            }
            glyph, fg = glyph_map.get(biome, glyph_map["default"])
            attrs["tile_glyph"] = glyph
            attrs["tile_fg"] = fg

        elif entity_type == "npc":
            crew = make_portraitist_crew(
                entity_name=name,
                entity_type="npc",
                description=description,
                labels=labels,
                biome=biome,
                mood=mood,
            )
            result = crew.kickoff()
            sprite_data = _parse_sprite_result(result.raw)
            attrs["portrait_sprite"] = sprite_data["sprite_b64"]
            attrs["portrait_w"] = sprite_data["width"]
            attrs["portrait_h"] = sprite_data["height"]
            attrs["tile_glyph"] = "@"
            attrs["tile_fg"] = "#d4a574"

        elif entity_type == "item":
            crew = make_portraitist_crew(
                entity_name=name,
                entity_type="item",
                description=description,
                labels=labels,
                biome=biome,
                mood=mood,
                icon_mode=True,
            )
            result = crew.kickoff()
            sprite_data = _parse_sprite_result(result.raw)
            attrs["icon_sprite"] = sprite_data["sprite_b64"]
            attrs["icon_w"] = sprite_data["width"]
            attrs["icon_h"] = sprite_data["height"]
            attrs["tile_glyph"] = "!"
            attrs["tile_fg"] = "#daa520"

        else:
            logger.warning(f"Unknown entity_type '{entity_type}' for art generation")
            return

        attrs["art_style"] = "dark_fantasy"
        attrs["art_generated_at"] = now

        client.kg.update_entity(
            entity_uid, name, labels, None,
            attributes=attrs,
        )
        logger.info(f"Art generated for {entity_type} '{name}' ({entity_uid})")

    except Exception:
        logger.exception(f"Art generation failed for {entity_type} '{name}' ({entity_uid})")
