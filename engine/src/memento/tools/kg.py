"""KG tools for CrewAI agents — wrap Bonfires SDK."""

from __future__ import annotations

from memento.core import tool
from memento.bonfires_client import get_client
from memento.tools import chain as _chain


def _resolve_entity_uuid(name: str) -> str | None:
    """Search KG for an entity by name, return its UUID or None."""
    client = get_client()
    result = client.kg.search(name, num_results=1)
    entities = result.get("entities", result.get("nodes", []))
    if entities:
        return str(entities[0].get("uuid", ""))
    return None


def _format_search_results(result: dict) -> str:
    """Format KG search results as a readable string for agents."""
    parts = []
    for entity in result.get("entities", result.get("nodes", [])):
        name = entity.get("name", "?")
        summary = entity.get("summary", "")
        labels = entity.get("labels", [])
        parts.append(f"- {name} [{', '.join(labels)}]: {summary}")
    for edge in result.get("edges", []):
        fact = edge.get("fact", "")
        if fact:
            src = edge.get("source_name", "?")
            tgt = edge.get("target_name", "?")
            parts.append(f"- {src} -> {tgt}: {fact}")
    if not parts:
        return "No results found."
    return "\n".join(parts)


def _sanitize_label(label: str) -> str:
    """Sanitize a label for Neo4j — no spaces, hyphens, or special chars."""
    return label.replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "")


@tool("Create Game Entity")
def create_entity(name: str, entity_type: str, summary: str) -> str:
    """Create a new entity in the game world (NPC, Location, Item, Region, Faction, Quest).
    Returns the UUID of the created entity."""
    client = get_client()
    labels = [_sanitize_label(entity_type)]
    uuid = client.kg.create_entity(name, labels, {"summary": summary})
    # Chain dual-write (Characters + Items only — locations/events are offchain)
    if _chain.is_enabled():
        entity_type_lower = entity_type.lower()
        if entity_type_lower in ("character", "player", "npc"):
            _chain.register_character(uuid, name, "")
        elif entity_type_lower in ("item", "weapon", "armor", "consumable"):
            _chain.register_item(uuid, name, summary[:50], "", "")
    return f"Created {entity_type} '{name}' with UUID: {uuid}"


@tool("Search World Knowledge")
def search_world(query: str, center_entity: str = "") -> str:
    """Search the game world's knowledge graph for information.
    Use center_entity to search from a specific character or location's perspective."""
    client = get_client()
    result = client.kg.search(query, num_results=10)
    return _format_search_results(result)


@tool("Create Relationship")
def create_edge(source_name: str, target_name: str, relationship: str, fact: str = "") -> str:
    """Create a relationship between two game entities.
    Common relationships: LOCATED_IN, CARRIES, MEMBER_OF, EXIT_TO, ALLIED_WITH, HOSTILE_TO."""
    client = get_client()
    src_uuid = _resolve_entity_uuid(source_name)
    tgt_uuid = _resolve_entity_uuid(target_name)
    if not src_uuid:
        return f"Error: could not find entity '{source_name}'"
    if not tgt_uuid:
        return f"Error: could not find entity '{target_name}'"
    client.kg.create_edge(src_uuid, tgt_uuid, relationship, fact)
    # Chain dual-write for death edges
    if _chain.is_enabled() and relationship.upper() in ("DIED_AT", "KILLED_BY"):
        source_uuid = _resolve_entity_uuid(source_name)
        _chain.record_death(source_uuid or "", fact, target_name, 0)
    return f"{source_name} --[{relationship}]--> {target_name}"


@tool("Update Entity")
def update_entity(name: str, new_summary: str = "", new_labels: str = "") -> str:
    """Update an existing entity's summary or labels.
    new_labels should be comma-separated, e.g. 'NPC,Merchant'."""
    client = get_client()
    uuid = _resolve_entity_uuid(name)
    if not uuid:
        return f"Error: could not find entity '{name}'"
    labels = [l.strip() for l in new_labels.split(",") if l.strip()] if new_labels else []
    client.kg.update_entity(uuid, name, labels, new_summary)
    return f"Updated '{name}'"


@tool("Mark Entity Status")
def mark_status(entity_name: str, status: str, cause: str = "") -> str:
    """Mark an entity with a status (DEAD, DESTROYED, CONSUMED, etc.).
    This is append-only — the entity is never deleted from the world."""
    client = get_client()
    uuid = _resolve_entity_uuid(entity_name)
    if not uuid:
        return f"Error: could not find entity '{entity_name}'"
    fact = f"{entity_name} {status}. {cause}".strip()
    client.kg.create_edge(uuid, uuid, "HAS_STATUS", fact)
    # Chain dual-write for death status
    if _chain.is_enabled() and status.lower() == "dead":
        entity_uuid = _resolve_entity_uuid(entity_name)
        _chain.record_death(entity_uuid or "", cause, "", 0)
    return f"Marked '{entity_name}' as {status}"


@tool("Get Recent Episodes")
def get_episodes(limit: int = 10) -> str:
    """Get recent game episodes — summarized memories of what happened in the world."""
    client = get_client()
    result = client.kg.search("recent events episodes", num_results=limit)
    return _format_search_results(result)


@tool("Remember Event")
def remember_event(summary: str) -> str:
    """Record a significant event as an episode in the world's memory.
    Use this for important moments: deaths, discoveries, betrayals, victories."""
    client = get_client()
    client.agents.sync(summary, chat_id="rpg:game-session")
    # Events are offchain-only — no chain write needed
    return f"Recorded: {summary}"


@tool("Pin to Session")
def pin_entity(entity_name: str) -> str:
    """Pin an entity to the current game session's kEngram for tracking."""
    client = get_client()
    uuid = _resolve_entity_uuid(entity_name)
    if not uuid:
        return f"Error: could not find entity '{entity_name}'"
    kengram = client.kengrams.get_active()
    client.kengrams.pin(kengram.id, uuid)
    return f"Pinned '{entity_name}' to session"


@tool("Get Entity Details")
def get_entity(name: str) -> str:
    """Get detailed information about a specific entity by name."""
    client = get_client()
    uuid = _resolve_entity_uuid(name)
    if not uuid:
        return f"Entity '{name}' not found."
    entity = client.kg.get_entity(uuid)
    if isinstance(entity, dict) and "entity" in entity:
        entity = entity["entity"]
    ename = entity.get("name", name)
    summary = entity.get("summary", "No description.")
    labels = entity.get("labels", [])
    return f"{ename} [{', '.join(labels)}]: {summary}"


@tool("Get Connected Entities")
def get_neighbors(entity_name: str) -> str:
    """Get entities connected to a given entity — NPCs at a location,
    items carried by a character, factions in a region, etc."""
    client = get_client()
    result = client.kg.search(entity_name, num_results=15)
    return _format_search_results(result)
