"""Entity routes — fetch entity details from KG. No LLM calls."""

import asyncio
from fastapi import APIRouter, Path

router = APIRouter()


@router.get("/entity/{entity_id}")
async def get_entity(entity_id: str = Path(...)):
    """Fetch entity details from KG by UUID. No LLM — instant response."""
    try:
        from memento.bonfires_client import get_client
        client = await asyncio.to_thread(get_client)
        entity = await asyncio.to_thread(client.kg.get_entity, entity_id)
        if isinstance(entity, dict) and "entity" in entity:
            entity = entity["entity"]
        return {
            "id": entity_id,
            "name": entity.get("name", "Unknown"),
            "labels": entity.get("labels", []),
            "summary": entity.get("summary", ""),
        }
    except Exception:
        return {"id": entity_id, "name": "Unknown", "labels": [], "summary": ""}


@router.get("/entity/search/{name}")
async def search_entity(name: str = Path(...)):
    """Search for entity by name. No LLM — instant KG search."""
    try:
        from memento.bonfires_client import get_client
        client = await asyncio.to_thread(get_client)
        result = await asyncio.to_thread(client.kg.search, name, 1)
        entities = result.get("entities", result.get("nodes", []))
        if entities:
            e = entities[0]
            return {
                "id": str(e.get("uuid", "")),
                "name": e.get("name", ""),
                "labels": e.get("labels", []),
                "summary": e.get("summary", ""),
            }
        return {"error": "not found"}
    except Exception:
        return {"error": "search failed"}
