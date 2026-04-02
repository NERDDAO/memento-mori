"""Room map extraction — parse JSON tile grids from LLM crew output."""

from __future__ import annotations

import json
import re
from typing import Any

from memento.log import get_logger

logger = get_logger(__name__)


def extract_room_map(crew_output: str, location_name: str = "") -> dict[str, Any] | None:
    """Extract a room_map JSON block from crew output text.

    Looks for ```json ... ``` code fences containing tile grid data.
    Returns the parsed dict or None if extraction fails.
    """
    # Try to find JSON code blocks
    matches = re.findall(r'```(?:json)?\s*\n?(.*?)```', crew_output, re.DOTALL)

    for match in matches:
        try:
            data = json.loads(match.strip())
            if _validate_room_map(data):
                if location_name and not data.get("name"):
                    data["name"] = location_name
                return data
        except json.JSONDecodeError:
            continue

    # Fallback: try to find a JSON object with "tiles" key anywhere in the text
    try:
        # Look for { ... "tiles" ... } pattern
        brace_match = re.search(r'\{[^{}]*"tiles"[^{}]*\[.*?\][^{}]*\}', crew_output, re.DOTALL)
        if brace_match:
            data = json.loads(brace_match.group())
            if _validate_room_map(data):
                if location_name and not data.get("name"):
                    data["name"] = location_name
                return data
    except (json.JSONDecodeError, re.error):
        pass

    logger.warning("Failed to extract room_map from crew output for: %s", location_name)
    return None


def _validate_room_map(data: dict) -> bool:
    """Check that a parsed dict looks like a valid room_map."""
    if not isinstance(data, dict):
        return False
    if "tiles" not in data:
        return False
    tiles = data.get("tiles", [])
    if not isinstance(tiles, list) or len(tiles) < 100:
        return False
    width = data.get("width", 0)
    height = data.get("height", 0)
    if width <= 0 or height <= 0:
        return False
    return True


def generate_fallback_map(
    location_name: str,
    width: int = 35,
    height: int = 18,
) -> dict[str, Any]:
    """Generate a simple fallback room map for locations where LLM extraction failed."""
    tiles: list[str] = []
    for y in range(height):
        for x in range(width):
            if y == 0 or y == height - 1 or x == 0 or x == width - 1:
                tiles.append("#")
            else:
                tiles.append(".")

    # Place exits at cardinal points
    tiles[0 * width + width // 2] = "+"  # north
    tiles[(height - 1) * width + width // 2] = "+"  # south
    tiles[height // 2 * width + width - 1] = "+"  # east
    tiles[height // 2 * width + 0] = "+"  # west

    return {
        "id": "",
        "name": location_name,
        "width": width,
        "height": height,
        "tiles": tiles,
        "npcs": [],
        "items": [],
        "exits": [
            {"x": width // 2, "y": 0, "ch": "+", "direction": "north", "target": "unknown"},
            {"x": width // 2, "y": height - 1, "ch": "+", "direction": "south", "target": "unknown"},
            {"x": width - 1, "y": height // 2, "ch": "+", "direction": "east", "target": "unknown"},
            {"x": 0, "y": height // 2, "ch": "+", "direction": "west", "target": "unknown"},
        ],
        "spawn": {"x": width // 2, "y": height // 2},
    }
