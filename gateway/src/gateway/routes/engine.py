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


# ── Tier 2: World Mutation (KG writes, 1-2s) ──

class RememberRequest(BaseModel):
    summary: str = Field(..., max_length=1000)
    npc_id: str = Field("", max_length=64)

class UpdateEntityRequest(BaseModel):
    name: str = Field(..., max_length=200)
    new_summary: str = Field("", max_length=2000)
    new_labels: str = Field("", max_length=500)
    npc_id: str = Field("", max_length=64)

class GiveItemRequest(BaseModel):
    item_name: str = Field(..., max_length=200)
    from_entity: str = Field(..., max_length=200)
    to_entity: str = Field(..., max_length=200)
    npc_id: str = Field("", max_length=64)

class GiveQuestRequest(BaseModel):
    quest_name: str = Field(..., max_length=200)
    description: str = Field(..., max_length=2000)
    giver_name: str = Field(..., max_length=200)
    player_name: str = Field(..., max_length=200)
    npc_id: str = Field("", max_length=64)

class CreateEntityRequest(BaseModel):
    name: str = Field(..., max_length=200)
    entity_type: str = Field(..., max_length=50)
    summary: str = Field("", max_length=2000)
    location_name: str = Field("", max_length=200)
    npc_id: str = Field("", max_length=64)

class MoveRequest(BaseModel):
    entity_name: str = Field(..., max_length=200)
    destination: str = Field(..., max_length=200)
    npc_id: str = Field("", max_length=64)

class GossipRequest(BaseModel):
    from_npc: str = Field(..., max_length=200)
    to_npc: str = Field(..., max_length=200)
    message: str = Field(..., max_length=1000)
    npc_id: str = Field("", max_length=64)


@router.post("/engine/world/remember")
async def remember_event(req: RememberRequest):
    """Record a significant event to episodic memory."""
    await check_tool_access(req.npc_id, "mm_remember_event")
    from memento.tools.kg import remember_event as _remember
    result = await asyncio.to_thread(_remember, req.summary)
    return {"result": result}


@router.post("/engine/world/update-entity")
async def update_entity(req: UpdateEntityRequest):
    """Update an entity's summary or labels."""
    await check_tool_access(req.npc_id, "mm_update_entity")
    from memento.tools.kg import update_entity as _update
    result = await asyncio.to_thread(_update, req.name, req.new_summary, req.new_labels)
    return {"result": result}


@router.post("/engine/world/give-item")
async def give_item(req: GiveItemRequest):
    """Transfer item ownership between entities."""
    await check_tool_access(req.npc_id, "mm_give_item")
    from memento.tools.kg import create_edge
    result = await asyncio.to_thread(
        create_edge, req.item_name, req.to_entity, "OWNED_BY",
        f"Transferred from {req.from_entity} to {req.to_entity}",
    )
    return {"result": result}


@router.post("/engine/world/give-quest")
async def give_quest(req: GiveQuestRequest):
    """Create a quest and assign it to a player."""
    await check_tool_access(req.npc_id, "mm_give_quest")
    from memento.tools.kg import create_entity, create_edge
    uuid = await asyncio.to_thread(create_entity, req.quest_name, "Quest", req.description)
    await asyncio.to_thread(
        create_edge, req.quest_name, req.player_name, "ASSIGNED_TO",
        f"Quest given by {req.giver_name}",
    )
    await asyncio.to_thread(
        create_edge, req.quest_name, req.giver_name, "GIVEN_BY", "",
    )
    return {"uuid": uuid, "quest_name": req.quest_name, "assigned_to": req.player_name}


@router.post("/engine/world/create-npc")
async def create_npc(req: CreateEntityRequest):
    """Create a new NPC entity in the KG."""
    await check_tool_access(req.npc_id, "mm_create_npc")
    from memento.tools.kg import create_entity, create_edge
    uuid = await asyncio.to_thread(create_entity, req.name, "NPC", req.summary)
    if req.location_name:
        await asyncio.to_thread(
            create_edge, req.name, req.location_name, "LOCATED_IN", "",
        )
    return {"uuid": uuid, "name": req.name, "entity_type": "NPC"}


@router.post("/engine/world/create-item")
async def create_item(req: CreateEntityRequest):
    """Create a new item entity in the KG."""
    await check_tool_access(req.npc_id, "mm_create_item")
    from memento.tools.kg import create_entity, create_edge
    uuid = await asyncio.to_thread(create_entity, req.name, "Item", req.summary)
    if req.location_name:
        await asyncio.to_thread(
            create_edge, req.name, req.location_name, "LOCATED_IN", "",
        )
    return {"uuid": uuid, "name": req.name, "entity_type": "Item"}


@router.post("/engine/world/create-location")
async def create_location(req: CreateEntityRequest):
    """Create a new location entity in the KG."""
    await check_tool_access(req.npc_id, "mm_create_location")
    from memento.tools.kg import create_entity
    uuid = await asyncio.to_thread(create_entity, req.name, "Location", req.summary)
    return {"uuid": uuid, "name": req.name, "entity_type": "Location"}


@router.post("/engine/world/move")
async def move_entity(req: MoveRequest):
    """Move an NPC to a different location."""
    await check_tool_access(req.npc_id, "mm_move_to")
    from memento.tools.kg import create_edge
    result = await asyncio.to_thread(
        create_edge, req.entity_name, req.destination, "LOCATED_IN",
        f"{req.entity_name} moved to {req.destination}",
    )
    # Update agent controller tracking
    try:
        from memento.agent_controller import get_agent_controller
        controller = get_agent_controller()
        controller.move_npc_agent(req.entity_name, to_location=req.destination)
    except Exception:
        pass  # Non-fatal — agent may not exist
    return {"result": result, "entity": req.entity_name, "destination": req.destination}


@router.post("/engine/world/gossip")
async def send_gossip(req: GossipRequest):
    """Send a message to another NPC via Matrix."""
    # This could post to the target NPC's Matrix room
    # For now, just record it as an event
    from memento.tools.kg import remember_event as _remember
    summary = f"{req.from_npc} told {req.to_npc}: {req.message}"
    result = await asyncio.to_thread(_remember, summary)
    return {"result": result, "from": req.from_npc, "to": req.to_npc}


# ── Tier 3: Crew-Powered (LLM calls, 2-30s) ──

class CombatResolveRequest(BaseModel):
    action: str = Field(..., max_length=500)
    attacker: str = Field(..., max_length=200)
    target: str = Field(..., max_length=200)
    location: str = Field(..., max_length=200)
    context: str = Field("", max_length=2000)
    attacker_stats: str = Field("", max_length=1000)
    target_stats: str = Field("", max_length=1000)
    npc_id: str = Field("", max_length=64)

class CombatAssessRequest(BaseModel):
    action: str = Field(..., max_length=500)
    attacker: str = Field(..., max_length=200)
    target: str = Field(..., max_length=200)
    location: str = Field(..., max_length=200)
    npc_id: str = Field("", max_length=64)

class PlausibilityRequest(BaseModel):
    action: str = Field(..., max_length=500)
    context: str = Field(..., max_length=2000)
    npc_id: str = Field("", max_length=64)

class DesignQuestRequest(BaseModel):
    location: str = Field(..., max_length=200)
    npc_name: str = Field(..., max_length=200)
    player_level: int = Field(1, ge=1, le=50)
    active_quests: str = Field("", max_length=1000)
    faction_context: str = Field("", max_length=1000)
    npc_id: str = Field("", max_length=64)

class DesignItemRequest(BaseModel):
    location_name: str = Field(..., max_length=200)
    rarity_budget: str = Field("common", max_length=20)
    num_items: int = Field(1, ge=1, le=5)
    npc_id: str = Field("", max_length=64)

class DesignNPCRequest(BaseModel):
    role: str = Field(..., max_length=200)
    location_name: str = Field(..., max_length=200)
    region_context: str = Field("", max_length=1000)
    npc_id: str = Field("", max_length=64)

class DesignLocationRequest(BaseModel):
    location_plan: str = Field(..., max_length=2000)
    region_name: str = Field(..., max_length=200)
    npc_id: str = Field("", max_length=64)

class DesignRegionRequest(BaseModel):
    theme: str = Field(..., max_length=500)
    adjacent_regions: str = Field("", max_length=500)
    player_level: int = Field(1, ge=1, le=50)
    npc_id: str = Field("", max_length=64)


def _locked(fn):
    """Run a function inside the engine lock."""
    def wrapper(*args, **kwargs):
        with _engine_lock:
            return fn(*args, **kwargs)
    return wrapper


@router.post("/engine/combat/resolve")
async def resolve_combat(req: CombatResolveRequest):
    """Full combat pipeline: assess -> resolve -> consequences -> death check."""
    await check_tool_access(req.npc_id, "mm_resolve_combat")

    def _run():
        from memento.flows.combat import CombatFlow, CombatState
        with _engine_lock:
            flow = CombatFlow()
            flow.state = CombatState(
                action=req.action, attacker=req.attacker, target=req.target,
                location=req.location, context=req.context,
                attacker_stats=req.attacker_stats, target_stats=req.target_stats,
            )
            flow.kickoff()
            return flow.state

    state = await asyncio.to_thread(_run)
    return {
        "outcome": {
            "action_type": state.action_type,
            "assessment": state.assessment,
            "resolution": state.resolution,
            "consequences": state.consequences,
            "target_dead": state.target_dead,
        },
    }


@router.post("/engine/combat/assess")
async def assess_combat(req: CombatAssessRequest):
    """Assess a combat situation without resolving."""
    await check_tool_access(req.npc_id, "mm_assess_combat")

    def _run():
        from memento.crews.combat.assessment import make_combat_assessment_crew
        with _engine_lock:
            crew = make_combat_assessment_crew(
                action=req.action, attacker=req.attacker,
                target=req.target, location=req.location,
            )
            return crew.kickoff().raw

    result = await asyncio.to_thread(_run)
    return {"assessment": result}


@router.post("/engine/plausibility")
async def check_plausibility(req: PlausibilityRequest):
    """Check if an action is plausible in the current scene."""
    await check_tool_access(req.npc_id, "mm_check_plausibility")

    def _run():
        from memento.config import load_config, get_model_for_crew
        from crewai import LLM
        with _engine_lock:
            model = get_model_for_crew("plausibility")
            llm = LLM(model=model, **load_config().get("llm", {}).get("params", {}))
            prompt = f"Is this action plausible given the context? Action: {req.action}\nContext: {req.context}\nRespond with PLAUSIBLE or IMPLAUSIBLE and a brief reason."
            response = llm.call([{"role": "user", "content": prompt}])
            plausible = "PLAUSIBLE" in response.upper() and "IMPLAUSIBLE" not in response.upper()
            return plausible, response

    plausible, reason = await asyncio.to_thread(_run)
    return {"plausible": plausible, "reason": reason}


@router.post("/engine/design/quest")
async def design_quest(req: DesignQuestRequest):
    """Design a morally complex quest using the quest design crew."""
    await check_tool_access(req.npc_id, "mm_design_quest")

    def _run():
        from memento.crews.quest.design import make_quest_design_crew
        with _engine_lock:
            crew = make_quest_design_crew(
                location=req.location, npc=req.npc_name,
                player_level=req.player_level, active_quests=req.active_quests,
                faction_context=req.faction_context,
            )
            return crew.kickoff().raw

    result = await asyncio.to_thread(_run)
    return {"quest_design": result}


@router.post("/engine/design/item")
async def design_item(req: DesignItemRequest):
    """Design thematically appropriate items using item concept crew."""
    await check_tool_access(req.npc_id, "mm_design_item")

    def _run():
        from memento.crews.item_gen.concept import make_item_concept_crew
        with _engine_lock:
            crew = make_item_concept_crew(
                location_name=req.location_name,
                rarity_budget=req.rarity_budget,
                num_items=req.num_items,
            )
            return crew.kickoff().raw

    result = await asyncio.to_thread(_run)
    return {"items": result}


@router.post("/engine/design/npc")
async def design_npc(req: DesignNPCRequest):
    """Design a full NPC with personality, stats, backstory."""
    await check_tool_access(req.npc_id, "mm_design_npc")

    def _run():
        from memento.crews.npc_gen.concept import make_concept_crew
        with _engine_lock:
            crew = make_concept_crew(
                npc_role=req.role, location_name=req.location_name,
                region_context=req.region_context,
            )
            return crew.kickoff().raw

    result = await asyncio.to_thread(_run)
    return {"npc_design": result}


@router.post("/engine/design/location")
async def design_location(req: DesignLocationRequest):
    """Design a full location with tile map using location crew."""
    await check_tool_access(req.npc_id, "mm_design_location")

    def _run():
        from memento.crews.world_gen.location import make_location_crew
        with _engine_lock:
            crew = make_location_crew(
                location_plan=req.location_plan, region_name=req.region_name,
            )
            return crew.kickoff().raw

    result = await asyncio.to_thread(_run)
    return {"location_design": result}


@router.post("/engine/design/region")
async def design_region(req: DesignRegionRequest):
    """Design an entire region with biome, culture, threats."""
    await check_tool_access(req.npc_id, "mm_design_region")

    def _run():
        from memento.crews.world_gen.region_design import make_region_design_crew
        with _engine_lock:
            crew = make_region_design_crew(
                theme=req.theme, adjacent_regions=req.adjacent_regions,
                player_level=req.player_level,
            )
            return crew.kickoff().raw

    result = await asyncio.to_thread(_run)
    return {"region_design": result}


@router.post("/engine/reputation")
async def check_reputation(req: BaseModel):
    """Check how an action affects faction reputation."""
    # Simplified — full implementation would use make_reputation_crew
    return {"result": "reputation check not yet implemented"}


@router.post("/engine/detect-events")
async def detect_events(req: BaseModel):
    """Detect event types in a scene."""
    # Simplified — full implementation would use EventDetectionFlow
    return {"result": "event detection not yet implemented"}


@router.post("/engine/npc-memory")
async def npc_memory(req: RememberRequest):
    """Record an NPC's first-person memory of a scene."""
    await check_tool_access(req.npc_id, "mm_npc_memory")
    from memento.tools.kg import remember_event as _remember
    result = await asyncio.to_thread(_remember, req.summary)
    return {"result": result}
