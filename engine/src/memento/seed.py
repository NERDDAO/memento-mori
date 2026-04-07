"""Seed the world — create The Threshold as the starting location with a tile grid."""

from __future__ import annotations

import json
from pathlib import Path
from memento.bonfires_client import get_client
from memento.log import get_logger

logger = get_logger(__name__)

# World manifest — stores known entity UUIDs so we never need text search
_WORLD_FILE = Path(__file__).parent.parent.parent.parent / "world.json"


def _load_world() -> dict:
    """Load world manifest from world.json."""
    try:
        if _WORLD_FILE.exists():
            return json.loads(_WORLD_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_world(data: dict) -> None:
    """Save world manifest to world.json."""
    try:
        _WORLD_FILE.write_text(json.dumps(data, indent=2) + "\n")
    except Exception as e:
        logger.warning("Failed to save world.json: %s", e)


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
    """Create The Threshold in the KG if it doesn't exist. Returns the entity UUID.

    Uses world.json to cache the UUID — no text search needed after first creation.
    """
    client = get_client()

    # 1. Check world.json for cached UUID
    world = _load_world()
    uuid = world.get("threshold_uuid", "")

    # 2. If cached, verify it still exists in KG
    if uuid:
        try:
            entity = client.kg.get_entity(uuid)
            if entity and entity.get("name"):
                logger.info("The Threshold (cached): %s", uuid)
                THRESHOLD_MAP["id"] = uuid
                # Still need to populate NPC/item entries below
            else:
                uuid = ""  # Entity gone, recreate
        except Exception:
            uuid = ""  # Entity not found, recreate

    # 3. If not cached or gone, search KG as fallback
    if not uuid:
        try:
            result = client.kg.search("The Threshold Location", num_results=5)
            for entity in result.get("entities", result.get("nodes", [])):
                if entity.get("name") == "The Threshold" and "Location" in entity.get("labels", []):
                    uuid = entity.get("uuid", "")
                    logger.info("The Threshold (found via search): %s", uuid)
                    break
        except Exception:
            pass

    # 4. Create if still not found
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

    # Merge cached NPC/item UUIDs for lookup
    cached_npcs = world.get("npcs", {})
    cached_items = world.get("items", {})
    cached_entities = {**cached_npcs, **cached_items}

    def find_or_create(name: str, labels: list, summary: str) -> str:
        """Find entity by cached UUID, verify it exists, or create. Returns UUID."""
        # 1. Check world.json cache
        cached_uuid = cached_entities.get(name, "")
        if cached_uuid:
            try:
                entity = client.kg.get_entity(cached_uuid)
                if entity and entity.get("name"):
                    logger.info("Found existing: %s (%s)", name, cached_uuid)
                    return cached_uuid
            except Exception:
                pass  # Cached UUID stale, fall through

        # 2. Text search fallback (first time only)
        try:
            result = client.kg.search(name, num_results=3)
            for e in result.get("entities", result.get("nodes", [])):
                if e.get("name") == name:
                    found_uuid = str(e["uuid"])
                    logger.info("Found existing: %s (%s)", name, found_uuid)
                    return found_uuid
        except Exception:
            pass

        # 3. Create new
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
            try:
                import asyncio
                from gateway.chain_client import write_position
                loop = asyncio.new_event_loop()
                loop.run_until_complete(write_position(npc_uuid, uuid, npc["x"], npc["y"]))
                loop.close()
            except Exception:
                pass
        except Exception:
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
            try:
                import asyncio
                from gateway.chain_client import write_position
                loop = asyncio.new_event_loop()
                loop.run_until_complete(write_position(item_uuid, uuid, item["x"], item["y"]))
                loop.close()
            except Exception:
                pass
        except Exception:
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

    # Update the entity with the complete map — store room_map in summary as JSON.
    # Pass labels=None so the CRUD service uses direct Cypher SET (not node.save()
    # which mangles JSON strings in Kuzu).
    summary_data = {
        "summary": "A vast stone chamber at the boundary between worlds. The air hums with residual energy.",
        "room_map": THRESHOLD_MAP,
    }
    client.kg.update_entity(uuid, "The Threshold", None, json.dumps(summary_data))

    # Pack terrain bytes for future onchain storage
    room_map = THRESHOLD_MAP
    try:
        from memento.terrain import pack_terrain
        tiles = room_map.get("tiles", []) if isinstance(room_map, dict) else []
        width = room_map.get("width", 35) if isinstance(room_map, dict) else 35
        height = room_map.get("height", 18) if isinstance(room_map, dict) else 18
        if tiles:
            terrain_bytes = pack_terrain(tiles, width, height)
            logger.info("Packed Threshold terrain: %dx%d (%d bytes)", width, height, len(terrain_bytes))
            import asyncio
            try:
                from gateway.chain_client import write_terrain, write_position
                loop = asyncio.new_event_loop()
                loop.run_until_complete(write_terrain(uuid, width, height, terrain_bytes))
                loop.close()
                logger.info("Wrote Threshold terrain onchain")
            except Exception:
                logger.debug("Terrain chain write skipped", exc_info=True)
    except Exception:
        logger.debug("Terrain packing failed for Threshold", exc_info=True)

    # Fix any edges with null episodes (Neo4j sometimes drops empty lists)
    try:
        from neo4j import GraphDatabase as _Neo4jDriver
        import os
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_pass = os.getenv("NEO4J_PASSWORD", "")
        if neo4j_pass:
            _driver = _Neo4jDriver.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
            with _driver.session() as _sess:
                result = _sess.run(
                    "MATCH ()-[r]->() WHERE r.episodes IS NULL SET r.episodes = [] RETURN count(r) as cnt"
                )
                fixed = result.single()["cnt"]
                if fixed:
                    logger.info("Fixed %d edges with null episodes", fixed)
            _driver.close()
    except Exception:
        logger.debug("Neo4j episodes fix skipped", exc_info=True)

    # Save all UUIDs to world.json for future lookups
    world["threshold_uuid"] = uuid
    world["npcs"] = {n["name"]: n["id"] for n in npc_entries}
    world["items"] = {i["name"]: i["id"] for i in item_entries}

    # Spawn room narrator for The Threshold + master narrator
    from memento.agent_controller import get_agent_controller
    ctrl = get_agent_controller()

    master_id = world.get("master_narrator_agent_id", "")
    if not master_id:
        master_id = ctrl.spawn_master_narrator()
        if master_id:
            world["master_narrator_agent_id"] = master_id

    narrator_id = world.get("threshold_narrator_agent_id", "")
    if not narrator_id:
        narrator_id = ctrl.spawn_room_narrator(
            location_name="The Threshold",
            location_uuid=uuid,
            location_description=(
                "A desolate crossroads tavern at the edge of the known world. "
                "The Bleeding Lantern serves as a waypoint for weary travelers."
            ),
            master_narrator_agent_id=master_id,
        )
        if narrator_id:
            world["threshold_narrator_agent_id"] = narrator_id

    _save_world(world)

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
