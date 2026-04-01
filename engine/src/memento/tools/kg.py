"""KG tools for CrewAI agents — wrap Bonfires SDK."""

from __future__ import annotations

from crewai.tools import tool
from memento.bonfires_client import get_client


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
            parts.append(f"- Fact: {fact}")
    if not parts:
        return "No results found."
    return "\n".join(parts)


@tool("Create Game Entity")
def create_entity(name: str, entity_type: str, summary: str) -> str:
    """Create a new entity in the game world (NPC, Location, Item, Region, Faction, Quest).
    Returns the UUID of the created entity."""
    client = get_client()
    labels = [entity_type]
    uuid = client.kg.create_entity(name, labels, {"summary": summary})
    return f"Created {entity_type} '{name}' with UUID: {uuid}"


@tool("Search World Knowledge")
def search_world(query: str, center_entity: str = "") -> str:
    """Search the game world's knowledge graph for information.
    Use center_entity to search from a specific character or location's perspective."""
    client = get_client()
    result = client.kg.search(query, num_results=10)
    return _format_search_results(result)
