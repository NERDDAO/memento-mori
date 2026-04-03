# gateway/src/gateway/routes/engine.py
"""Engine tool endpoints — callable by NPC agents via MCP tools."""

import asyncio
import os
import threading

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from gateway.engine_auth import verify_engine_token, check_tool_access

router = APIRouter(dependencies=[Depends(verify_engine_token)])

# Reuse the turn lock from matrix_listener for crew-powered endpoints
_engine_lock = threading.Lock()


# ── Request/Response Models ──

class StateRequest(BaseModel):
    entity_name: str = Field(..., max_length=200)
    npc_id: str = Field("", max_length=64)

class SkillCheckRequest(BaseModel):
    skill_level: int = Field(..., ge=0, le=30)
    difficulty: int = Field(..., ge=1, le=40)
    modifiers: int = Field(0, ge=-20, le=20)
    npc_id: str = Field("", max_length=64)

class DamageRequest(BaseModel):
    weapon_damage: int = Field(..., ge=0)
    attacker_strength: int = Field(..., ge=0)
    defender_armor: int = Field(..., ge=0)
    npc_id: str = Field("", max_length=64)

class DispositionRequest(BaseModel):
    current_friendship: float = Field(..., ge=-1.0, le=1.0)
    current_trust: float = Field(..., ge=-1.0, le=1.0)
    interaction_type: str = Field(..., max_length=50)
    npc_id: str = Field("", max_length=64)

class SearchRequest(BaseModel):
    query: str = Field(..., max_length=500)
    npc_id: str = Field("", max_length=64)

class EntityRequest(BaseModel):
    name: str = Field(..., max_length=200)
    npc_id: str = Field("", max_length=64)


# ── Tier 1: State & Knowledge (instant or 1-2s) ──

@router.post("/engine/state")
async def get_state(req: StateRequest):
    """Get an entity's current state from KG."""
    from memento.bonfires_client import get_client
    client = await asyncio.to_thread(get_client)

    # Search for entity
    result = await asyncio.to_thread(client.kg.search, req.entity_name, 5)
    entities = result.get("entities", result.get("nodes", []))
    edges = result.get("edges", [])

    entity = entities[0] if entities else {"name": req.entity_name, "labels": [], "summary": ""}

    # Extract recent events mentioning this entity
    episodes = result.get("episodes", [])
    recent = []
    for ep in episodes[:5]:
        content = ep.get("content", {})
        summary = content.get("content", "") if isinstance(content, dict) else str(content)
        if req.entity_name.lower() in summary.lower():
            recent.append(summary[:200])

    return {
        "name": entity.get("name", req.entity_name),
        "labels": entity.get("labels", []),
        "summary": entity.get("summary", ""),
        "edges": [
            {"source": e.get("source_node_name", ""), "target": e.get("target_node_name", ""),
             "relationship": e.get("name", ""), "fact": e.get("fact", "")}
            for e in edges[:10]
        ],
        "recent_events": recent,
    }


@router.get("/engine/world/time")
async def get_world_time():
    """Get current in-game time."""
    from memento.tools.time import get_current_time
    t = get_current_time()
    return t.to_display()


@router.post("/engine/world/search")
async def search_world(req: SearchRequest):
    """Search the knowledge graph."""
    from memento.bonfires_client import get_client
    client = await asyncio.to_thread(get_client)
    result = await asyncio.to_thread(client.kg.search, req.query, 10)
    entities = result.get("entities", result.get("nodes", []))
    edges = result.get("edges", [])
    return {
        "entities": [
            {"uuid": e.get("uuid", ""), "name": e.get("name", ""), "labels": e.get("labels", []),
             "summary": e.get("summary", "")}
            for e in entities
        ],
        "edges": [
            {"source": e.get("source_node_name", ""), "target": e.get("target_node_name", ""),
             "relationship": e.get("name", ""), "fact": e.get("fact", "")}
            for e in edges
        ],
    }


@router.post("/engine/world/entity")
async def get_entity(req: EntityRequest):
    """Get entity details by name."""
    from memento.bonfires_client import get_client
    from memento.tools.kg import _resolve_entity_uuid
    client = await asyncio.to_thread(get_client)
    uuid = await asyncio.to_thread(_resolve_entity_uuid, req.name)
    if not uuid:
        return {"error": "not_found", "name": req.name}
    entity = await asyncio.to_thread(client.kg.get_entity, uuid)
    if isinstance(entity, dict) and "entity" in entity:
        entity = entity["entity"]
    return {
        "uuid": uuid,
        "name": entity.get("name", req.name),
        "labels": entity.get("labels", []),
        "summary": entity.get("summary", ""),
    }


@router.post("/engine/skill-check")
async def skill_check(req: SkillCheckRequest):
    """Roll a skill check. Pure math, instant."""
    from memento.tools.mechanics import roll_skill_check
    result = roll_skill_check(str(req.skill_level), str(req.difficulty), str(req.modifiers))
    return {"result": result}


@router.post("/engine/damage")
async def calculate_damage(req: DamageRequest):
    """Calculate damage. Pure math, instant."""
    from memento.tools.mechanics import calculate_damage as calc
    result = calc(str(req.weapon_damage), str(req.attacker_strength), str(req.defender_armor))
    return {"result": result}


@router.post("/engine/disposition")
async def evaluate_disposition(req: DispositionRequest):
    """Evaluate disposition shift. Pure math, instant."""
    from memento.tools.mechanics import evaluate_disposition as eval_disp
    result = eval_disp(str(req.current_friendship), str(req.current_trust), req.interaction_type)
    return {"result": result}
