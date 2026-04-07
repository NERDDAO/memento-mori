"""In-memory NPC registry — maps agent_id → display name + location.

Populated by the engine's AgentController on spawn/move/kill.
Used by engine tool endpoints to resolve NPC identity for WS broadcasts.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NpcEntry:
    name: str
    location: str
    kg_uuid: str = ""


_registry: dict[str, NpcEntry] = {}


def register_npc(agent_id: str, name: str, location: str, kg_uuid: str = "") -> None:
    """Register or update an NPC in the registry."""
    _registry[agent_id] = NpcEntry(name=name, location=location, kg_uuid=kg_uuid)


def update_npc_location(agent_id: str, location: str) -> None:
    """Update an NPC's location."""
    entry = _registry.get(agent_id)
    if entry:
        entry.location = location


def unregister_npc(agent_id: str) -> None:
    """Remove an NPC from the registry."""
    _registry.pop(agent_id, None)


def resolve_npc_name(agent_id: str) -> str:
    """Resolve agent_id to display name."""
    entry = _registry.get(agent_id)
    return entry.name if entry else "Unknown NPC"


def resolve_npc_location(agent_id: str) -> str:
    """Resolve agent_id to current location."""
    entry = _registry.get(agent_id)
    return entry.location if entry else ""


def resolve_npc_kg_uuid(agent_id: str) -> str:
    """Resolve agent_id to KG entity UUID (for label-based tool access)."""
    entry = _registry.get(agent_id)
    return entry.kg_uuid if entry else ""


def get_npc_names_at_location(location: str) -> set[str]:
    """Return lowercase NPC names at a location (excludes Engine/Narrator agents)."""
    names: set[str] = set()
    for entry in _registry.values():
        if entry.location == location and not entry.name.startswith(("Engine:", "Narrator:")):
            names.add(entry.name.lower())
    return names


def seed_from_db() -> int:
    """Populate registry from MongoDB agentconfigs + world.json on startup.

    Reads bonfires-*/narrator_* agents from MongoDB, then resolves their KG UUIDs
    from world.json (which maps NPC names → KG UUIDs).
    Returns count of agents registered.
    """
    import json
    import os
    from pathlib import Path
    try:
        from pymongo import MongoClient
        mongo_uri = os.getenv("MONGO_URI", os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
        db_name = os.getenv("MONGO_DB_NAME", os.getenv("MONGODB_NAME", "cannitos"))
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
        db = client[db_name]

        # Load world.json for NPC name → KG UUID mapping
        npc_uuids: dict[str, str] = {}
        location_name = ""
        world_path = Path(__file__).parent.parent.parent.parent / "world.json"
        try:
            with open(world_path) as f:
                world = json.load(f)
            npc_uuids = world.get("npcs", {})
            # All NPCs start at The Threshold
            if world.get("threshold_uuid"):
                location_name = "The Threshold"
        except Exception:
            pass

        count = 0
        for doc in db["agentconfigs"].find({}, {"_id": 1, "name": 1, "username": 1}):
            agent_id = str(doc["_id"])
            username = doc.get("username", "")
            name = doc.get("name", "")
            if username.startswith("bonfires-") or username.startswith("narrator_"):
                kg_uuid = npc_uuids.get(name, "")
                register_npc(agent_id, name, location_name, kg_uuid)
                count += 1
        client.close()
        return count
    except Exception:
        return 0
