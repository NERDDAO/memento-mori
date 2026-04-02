"""Seed the world — create The Threshold as the starting location with a tile grid."""

from __future__ import annotations

import json
from memento.bonfires_client import get_client
from memento.log import get_logger

logger = get_logger(__name__)


# The Threshold — the one predefined room every player starts in
THRESHOLD_MAP = {
    "id": "",  # filled after KG creation
    "name": "The Threshold",
    "width": 35,
    "height": 18,
    "tiles": [],  # built below
    "npcs": [],
    "items": [],
    "exits": [],
    "spawn": {"x": 17, "y": 15},
}

# Build the tile grid
_W, _H = 35, 18
_tiles = []
for y in range(_H):
    for x in range(_W):
        if y == 0 or y == _H - 1 or x == 0 or x == _W - 1:
            _tiles.append("#")
        elif x >= 5 and x <= 7 and y >= 3 and y <= 7:
            _tiles.append("B")  # bar counter
        elif (x == 12 and y in (4, 5)) or (x == 20 and y in (4, 5)):
            _tiles.append("T")  # tables
        elif (x == 12 and y in (9, 10)) or (x == 20 and y in (9, 10)):
            _tiles.append("T")  # more tables
        elif x == _W - 1 and y == 9:
            _tiles.append("+")  # east exit (overwrite wall)
        elif x == 17 and y == 0:
            _tiles.append("+")  # north exit (overwrite wall)
        elif y == 14 and x >= 14 and x <= 20:
            _tiles.append(":")  # gravel path to entrance
        elif y == _H - 1 and x == 17:
            _tiles.append("+")  # south entrance
        else:
            _tiles.append(".")

THRESHOLD_MAP["tiles"] = _tiles
# Fix the wall overwrites
THRESHOLD_MAP["tiles"][9 * _W + (_W - 1)] = "+"  # east exit
THRESHOLD_MAP["tiles"][0 * _W + 17] = "+"  # north exit
THRESHOLD_MAP["tiles"][(_H - 1) * _W + 17] = "+"  # south entrance


def seed_threshold() -> dict:
    """Create The Threshold in the KG if it doesn't exist. Returns the entity UUID."""
    client = get_client()

    # Check if it already exists
    uuid = ""
    result = client.kg.search("The Threshold Location", num_results=5)
    entities = result.get("entities", result.get("nodes", []))
    for entity in entities:
        if entity.get("name") == "The Threshold" and "Location" in entity.get("labels", []):
            uuid = entity.get("uuid", "")
            logger.info("The Threshold already exists: %s", uuid)
            break

    # Create if not found
    if not uuid:
        uuid = client.kg.create_entity(
            "The Threshold",
            ["Location"],
            {
                "summary": (
                    "A desolate crossroads at the edge of the known world. "
                    "Cracked flagstones stretch beneath a bruised sky. "
                    "A weathered tavern — The Bleeding Lantern — squats at the center, "
                    "its crimson-lit windows the only warmth against the encroaching dark. "
                    "To the north, skeletal woods whisper. To the east, the road fades into fog."
                ),
                "room_map": json.dumps(THRESHOLD_MAP),
            },
        )
        logger.info("Created The Threshold: %s", uuid)

    THRESHOLD_MAP["id"] = uuid

    # Create NPCs
    npcs = [
        {
            "name": "Grumlock Stonebrow",
            "labels": ["NPC", "Barkeeper"],
            "summary": (
                "A squat, broad-shouldered dwarf with a face weathered like ancient stone. "
                "His thick greying beard could hide a small family of mice. "
                "He watches every patron with eyes that have seen too much. "
                "His voice is like rocks tumbling down a mountain path."
            ),
            "x": 6, "y": 5, "ch": "G",
        },
        {
            "name": "Roric the Sly",
            "labels": ["NPC", "Merchant", "InformationBroker"],
            "summary": (
                "A lean, wiry man in clean dark clothes. His eyes carry a perpetual gleam "
                "of calculation. A faint smile plays on his thin lips. An information broker "
                "and purveyor of rare, ill-gotten goods. Every word is precisely enunciated."
            ),
            "x": 22, "y": 6, "ch": "R",
        },
        {
            "name": "Elara Brightwood",
            "labels": ["NPC", "Guard", "Nervous"],
            "summary": (
                "A young woman barely out of her teens, clad in ill-fitting stained leather armor. "
                "A rusty sword clanks awkwardly at her side. Sent on a reconnaissance mission "
                "she clearly despises. Her discomfort is palpable."
            ),
            "x": 15, "y": 10, "ch": "E",
        },
    ]

    import time

    def find_or_create(name: str, labels: list, summary: str) -> str:
        """Find entity by name or create it. Returns UUID."""
        result = client.kg.search(name, num_results=3)
        for e in result.get("entities", result.get("nodes", [])):
            if e.get("name") == name:
                logger.info("Found existing: %s (%s)", name, e["uuid"])
                return str(e["uuid"])
        time.sleep(1)
        new_uuid = client.kg.create_entity(name, labels, {"summary": summary})
        logger.info("Created: %s (%s)", name, new_uuid)
        return str(new_uuid)

    npc_entries = []
    for npc in npcs:
        try:
            npc_uuid = find_or_create(npc["name"], npc["labels"], npc["summary"])
            try:
                client.kg.create_edge(npc_uuid, uuid, "LOCATED_IN", "")
            except Exception:
                pass
            npc_entries.append({
                "x": npc["x"], "y": npc["y"],
                "ch": npc["ch"], "name": npc["name"],
                "id": npc_uuid,
            })
        except Exception as e:
            logger.warning("NPC creation failed: %s", npc["name"], exc_info=True)
            npc_entries.append({
                "x": npc["x"], "y": npc["y"],
                "ch": npc["ch"], "name": npc["name"],
                "id": npc["name"],
            })

    THRESHOLD_MAP["npcs"] = npc_entries

    # Create items
    items = [
        {
            "name": "Tattered Journal",
            "labels": ["Item", "Readable"],
            "summary": "A water-stained journal with frantic handwriting. The last entry reads: 'They come from the north. Do not trust the fog.'",
            "x": 13, "y": 9, "ch": "?",
        },
        {
            "name": "Dull Iron Dagger",
            "labels": ["Item", "Weapon"],
            "summary": "A simple iron dagger, its edge dulled by time. Better than nothing.",
            "x": 28, "y": 3, "ch": "!",
        },
    ]

    item_entries = []
    for item in items:
        try:
            item_uuid = find_or_create(item["name"], item["labels"], item["summary"])
            try:
                client.kg.create_edge(item_uuid, uuid, "LOCATED_IN", "")
            except Exception:
                pass
            item_entries.append({
                "x": item["x"], "y": item["y"],
                "ch": item["ch"], "name": item["name"],
                "id": item_uuid,
            })
        except Exception as e:
            logger.warning("Item creation failed: %s", item["name"], exc_info=True)
            item_entries.append({
                "x": item["x"], "y": item["y"],
                "ch": item["ch"], "name": item["name"],
                "id": item["name"],
            })

    THRESHOLD_MAP["items"] = item_entries

    # Exits
    THRESHOLD_MAP["exits"] = [
        {"x": 34, "y": 9, "ch": "+", "direction": "east", "target": "The Fog Road"},
        {"x": 17, "y": 0, "ch": "+", "direction": "north", "target": "The Skeletal Woods"},
        {"x": 17, "y": 17, "ch": "+", "direction": "south", "target": "The Wastes"},
    ]

    # Update the entity with the complete map
    client.kg.update_entity(uuid, "The Threshold", ["Location"], json.dumps({
        "summary": THRESHOLD_MAP["npcs"][0]["name"] if THRESHOLD_MAP["npcs"] else "",
        "room_map": json.dumps(THRESHOLD_MAP),
    }))

    return {"uuid": uuid, "map": THRESHOLD_MAP, "created": True}


def get_threshold_map() -> dict | None:
    """Get The Threshold's room map, creating it if needed."""
    result = seed_threshold()
    return result["map"]


def seed_world(theme: str = "dark fantasy crossroads", player_level: int = 1, num_locations: int = 5) -> dict:
    """Seed a complete world: Threshold + generated region with interconnected locations.

    This is the main entry point for world initialization. It:
    1. Ensures The Threshold exists (the starting tavern)
    2. Runs WorldGenFlow to generate a region with locations, NPCs, and items
    3. Returns a summary of what was created

    This is expensive (many LLM calls). Run once per world, not per player.
    """
    logger.info("Seeding world: theme=%s, level=%d, locations=%d", theme, player_level, num_locations)

    # 1. Ensure The Threshold exists
    threshold = seed_threshold()
    logger.info("Threshold ready: %s", threshold["uuid"])

    # 2. Generate region with locations
    from memento.flows.world_gen import WorldGenFlow
    flow = WorldGenFlow()
    flow.state.theme = theme
    flow.state.player_level = player_level
    flow.state.num_locations = num_locations
    flow.kickoff()

    locations_created = [loc.name for loc in flow.state.locations]
    logger.info("World seeded: region=%s, locations=%s", flow.state.region_name, locations_created)

    return {
        "threshold_uuid": threshold["uuid"],
        "region_name": flow.state.region_name,
        "locations": locations_created,
        "num_locations": len(locations_created),
    }


if __name__ == "__main__":
    import sys

    if "--world" in sys.argv:
        # Full world seed
        theme = "dark fantasy crossroads"
        for i, arg in enumerate(sys.argv):
            if arg == "--theme" and i + 1 < len(sys.argv):
                theme = sys.argv[i + 1]
        result = seed_world(theme=theme)
        logger.info("World seed complete: %s", result)
    else:
        # Just The Threshold
        result = seed_threshold()
        logger.info("Result: created=%s, uuid=%s", result["created"], result["uuid"])
        logger.info("NPCs: %d", len(result["map"]["npcs"]))
        logger.info("Items: %d", len(result["map"]["items"]))
        logger.info("Exits: %d", len(result["map"]["exits"]))
