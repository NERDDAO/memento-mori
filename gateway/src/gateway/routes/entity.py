"""Entity routes — fetch entity details from KG. Non-canonical entities filtered via MUD indexer."""

import asyncio
from fastapi import APIRouter, Path

from gateway.chain_client import entity_exists_onchain

try:
    from memento.bonfires_client import get_client
except ImportError:
    get_client = None  # type: ignore[assignment]

router = APIRouter()


async def _filter_canonical(entities: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Remove entities not found onchain and edges referencing them."""
    checks = await asyncio.gather(*(
        entity_exists_onchain(str(e.get("uuid", e.get("id", ""))), e.get("labels", []))
        for e in entities
    ))
    canonical_names: set[str] = set()
    filtered_entities = []
    for e, is_canonical in zip(entities, checks):
        if is_canonical:
            filtered_entities.append(e)
            canonical_names.add(e.get("name", ""))

    filtered_edges = [
        edge for edge in edges
        if edge.get("source", edge.get("source_name", "")) in canonical_names
        and edge.get("target", edge.get("target_name", "")) in canonical_names
    ]
    return filtered_entities, filtered_edges


@router.get("/entity/{entity_id}/neighbors")
async def get_neighbors(entity_id: str = Path(...)):
    """Get entity details + connected entities and edges from KG, filtered for canonical entities."""
    try:
        _get_client = get_client
        if _get_client is None:
            from memento.bonfires_client import get_client as _get_client
        client = await asyncio.to_thread(_get_client)

        entity = await asyncio.to_thread(client.kg.get_entity, entity_id)
        if isinstance(entity, dict) and "entity" in entity:
            entity = entity["entity"]
        name = entity.get("name", "Unknown")
        labels = entity.get("labels", [])

        # Check if primary entity is canonical
        if not await entity_exists_onchain(entity_id, labels):
            return {"entity": {"id": entity_id, "name": "Unknown", "labels": [], "summary": ""}, "neighbors": [], "edges": []}

        result = await asyncio.to_thread(client.kg.search, name, 15)
        raw_entities = result.get("entities", result.get("nodes", []))
        raw_edges = result.get("edges", [])

        # Build neighbor list and edges
        neighbors_raw = [
            {
                "id": str(e.get("uuid", "")),
                "name": e.get("name", ""),
                "labels": e.get("labels", []),
                "summary": e.get("summary", ""),
                "uuid": str(e.get("uuid", "")),
            }
            for e in raw_entities
            if str(e.get("uuid", "")) != entity_id
        ]
        edges_raw = [
            {
                "source": e.get("source_name", ""),
                "target": e.get("target_name", ""),
                "relationship": e.get("relationship", e.get("name", "")),
                "fact": e.get("fact", ""),
            }
            for e in raw_edges
        ]

        # Filter neighbors for canonical entities, then filter edges using full canonical set
        neighbors_filtered, _ = await _filter_canonical(neighbors_raw, edges_raw)

        # Build canonical name set including primary entity, then filter edges once
        canonical_names = {n["name"] for n in neighbors_filtered}
        canonical_names.add(name)
        edges_filtered = [e for e in edges_raw if e["source"] in canonical_names and e["target"] in canonical_names]

        return {
            "entity": {
                "id": entity_id,
                "name": name,
                "labels": labels,
                "summary": entity.get("summary", ""),
            },
            "neighbors": [{k: v for k, v in n.items() if k != "uuid"} for n in neighbors_filtered],
            "edges": edges_filtered,
        }
    except Exception:
        return {"entity": {"id": entity_id, "name": "Unknown", "labels": [], "summary": ""}, "neighbors": [], "edges": []}


@router.get("/entity/{entity_id}")
async def get_entity(entity_id: str = Path(...)):
    """Fetch entity details from KG by UUID, verified canonical."""
    try:
        _get_client = get_client
        if _get_client is None:
            from memento.bonfires_client import get_client as _get_client
        client = await asyncio.to_thread(_get_client)
        entity = await asyncio.to_thread(client.kg.get_entity, entity_id)
        if isinstance(entity, dict) and "entity" in entity:
            entity = entity["entity"]

        labels = entity.get("labels", [])
        if not await entity_exists_onchain(entity_id, labels):
            return {"id": entity_id, "name": "Unknown", "labels": [], "summary": ""}

        return {
            "id": entity_id,
            "name": entity.get("name", "Unknown"),
            "labels": labels,
            "summary": entity.get("summary", ""),
        }
    except Exception:
        return {"id": entity_id, "name": "Unknown", "labels": [], "summary": ""}


@router.get("/entity/search/{name}")
async def search_entity(name: str = Path(...)):
    """Search for entity by name, verified canonical."""
    try:
        _get_client = get_client
        if _get_client is None:
            from memento.bonfires_client import get_client as _get_client
        client = await asyncio.to_thread(_get_client)
        result = await asyncio.to_thread(client.kg.search, name, 1)
        entities = result.get("entities", result.get("nodes", []))
        if entities:
            e = entities[0]
            entity_id = str(e.get("uuid", ""))
            labels = e.get("labels", [])
            if not await entity_exists_onchain(entity_id, labels):
                return {"error": "not found"}
            return {
                "id": entity_id,
                "name": e.get("name", ""),
                "labels": labels,
                "summary": e.get("summary", ""),
            }
        return {"error": "not found"}
    except Exception:
        return {"error": "search failed"}
