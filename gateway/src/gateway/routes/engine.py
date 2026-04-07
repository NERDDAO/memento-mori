# gateway/src/gateway/routes/engine.py
"""Engine tool endpoints — callable by NPC agents via MCP tools."""

import asyncio
import os
import threading

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from gateway.engine_auth import verify_engine_token, check_tool_access
from gateway.npc_registry import resolve_npc_name, resolve_npc_location

router = APIRouter(dependencies=[Depends(verify_engine_token)])

# ── Logging ──
from gateway.log import get_logger
logger = get_logger(__name__)

# Reuse the turn lock from matrix_listener for crew-powered endpoints
_engine_lock = threading.Lock()


# ── Tool Event Broadcasting ──

async def broadcast_tool_event(
    request: Request,
    tool: str,
    npc_id: str,
    summary: str,
    data: dict | None = None,
) -> None:
    """Push a tool_event to all players at the NPC's location."""
    ws_hub = getattr(request.app.state, "ws_hub", None)
    if not ws_hub:
        return
    npc = resolve_npc_name(npc_id)
    location = resolve_npc_location(npc_id)
    msg = {
        "type": "tool_event",
        "tool": tool,
        "npc": npc,
        "summary": summary,
        "data": data or {},
        "location": location,
        "channel": "narrative",
    }
    if location:
        await ws_hub.broadcast_to_location(location, msg)
    else:
        await ws_hub.broadcast_all(msg)


def push_to_stack(text: str, npc_name: str, location: str, narrator_registry: dict | None = None) -> None:
    """Push NPC dialogue to the narrator agent stack (fire-and-forget).

    Routes to the per-room narrator if available, otherwise falls back to global narrator.
    """
    if not text or not text.strip():
        return
    try:
        from memento.bonfires_client import get_client
        from datetime import datetime, UTC
        client = get_client()

        # Route to per-room narrator if available, else global narrator
        agent_id = client.config.agent_id
        if narrator_registry and location:
            agent_id = narrator_registry.get(location) or agent_id

        from bonfires.sdk.http import _post
        _post(
            client.config,
            f"/agents/{agent_id}/stack/add",
            body={
                "messages": [{
                    "text": f"[{location}] {npc_name}: {text[:2000]}",
                    "userId": npc_name,
                    "chatId": location or "unknown",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "role": "user",
                }],
            },
        )
    except Exception:
        logger.debug("push_to_stack failed for %s", npc_name, exc_info=True)


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

    # Build spatial awareness — find the NPC's location and room positions
    spatial: dict = {}
    try:
        entity_uuid = entity.get("uuid", entity.get("id", ""))
        if entity_uuid:
            # Find LOCATED_IN edge to get current location UUID
            loc_edges = await asyncio.to_thread(
                client.kg.get_edges, entity_uuid,
                direction="outgoing", edge_type="LOCATED_IN",
            )
            if loc_edges:
                loc_target = loc_edges[0].get("target", {})
                loc_uuid = loc_target.get("uuid", loc_target.get("id", ""))
                if loc_uuid:
                    from memento.room_manifest import get_room_manifest
                    room_map = await asyncio.to_thread(get_room_manifest, loc_uuid)

                    # Find this NPC's own position in the room
                    own_x, own_y = 0, 0
                    entity_lower = req.entity_name.lower()
                    for npc in room_map.get("npcs", []):
                        if npc.get("name", "").lower() == entity_lower:
                            own_x, own_y = npc.get("x", 0), npc.get("y", 0)
                            break

                    spatial["room_width"] = room_map.get("width", 35)
                    spatial["room_height"] = room_map.get("height", 18)
                    spatial["own_position"] = {"x": own_x, "y": own_y}

                    # All other entities in the room with positions
                    positions = []
                    for npc in room_map.get("npcs", []):
                        positions.append({
                            "type": "NPC",
                            "name": npc.get("name", "?"),
                            "x": npc.get("x", 0),
                            "y": npc.get("y", 0),
                        })
                    for item in room_map.get("items", []):
                        positions.append({
                            "type": "ITEM",
                            "name": item.get("name", "?"),
                            "x": item.get("x", 0),
                            "y": item.get("y", 0),
                        })
                    for player in room_map.get("players", []):
                        positions.append({
                            "type": "PLAYER",
                            "name": player.get("name", "?"),
                            "x": player.get("x", 0),
                            "y": player.get("y", 0),
                        })
                    spatial["room_entities"] = positions
    except Exception:
        logger.debug("Spatial lookup failed for %s", req.entity_name, exc_info=True)

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
        **spatial,
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
async def skill_check(req: SkillCheckRequest, request: Request):
    """Roll a skill check. Pure math, instant."""
    from memento.tools.mechanics import roll_skill_check as _rsc; roll_skill_check = _rsc.func
    result = roll_skill_check(str(req.skill_level), str(req.difficulty), str(req.modifiers))
    await broadcast_tool_event(
        request, tool="mm_skill_check", npc_id=req.npc_id,
        summary=f"Skill check (DC {req.difficulty}): {result}",
    )
    return {"result": result}


@router.post("/engine/damage")
async def calculate_damage(req: DamageRequest):
    """Calculate damage. Pure math, instant."""
    from memento.tools.mechanics import calculate_damage as _calc; calc = _calc.func
    result = calc(str(req.weapon_damage), str(req.attacker_strength), str(req.defender_armor))
    return {"result": result}


@router.post("/engine/disposition")
async def evaluate_disposition(req: DispositionRequest):
    """Evaluate disposition shift. Pure math, instant."""
    from memento.tools.mechanics import evaluate_disposition as _ed; eval_disp = _ed.func
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
    from memento.tools.kg import remember_event as _remember_tool; _remember = _remember_tool.func
    result = await asyncio.to_thread(_remember, req.summary)
    return {"result": result}


@router.post("/engine/world/update-entity")
async def update_entity(req: UpdateEntityRequest):
    """Update an entity's summary or labels."""
    await check_tool_access(req.npc_id, "mm_update_entity")
    from memento.tools.kg import update_entity as _update_tool; _update = _update_tool.func
    result = await asyncio.to_thread(_update, req.name, req.new_summary, req.new_labels)
    return {"result": result}


@router.post("/engine/world/give-item")
async def give_item(req: GiveItemRequest, request: Request):
    """Transfer item ownership between entities."""
    await check_tool_access(req.npc_id, "mm_give_item")
    from memento.tools.kg import create_edge as _ce_tool; create_edge = _ce_tool.func
    result = await asyncio.to_thread(
        create_edge, req.item_name, req.to_entity, "OWNED_BY",
        f"Transferred from {req.from_entity} to {req.to_entity}",
    )
    await broadcast_tool_event(
        request, tool="mm_give_item", npc_id=req.npc_id,
        summary=f"{req.from_entity} gave {req.item_name} to {req.to_entity}",
    )
    return {"result": result}


@router.post("/engine/world/give-quest")
async def give_quest(req: GiveQuestRequest, request: Request):
    """Create a quest and assign it to a player."""
    await check_tool_access(req.npc_id, "mm_give_quest")
    from memento.tools.kg import create_entity as _cen, create_edge as _ced
    create_entity = _cen.func; create_edge = _ced.func
    uuid = await asyncio.to_thread(create_entity, req.quest_name, "Quest", req.description)
    await asyncio.to_thread(
        create_edge, req.quest_name, req.player_name, "ASSIGNED_TO",
        f"Quest given by {req.giver_name}",
    )
    await asyncio.to_thread(
        create_edge, req.quest_name, req.giver_name, "GIVEN_BY", "",
    )
    await broadcast_tool_event(
        request, tool="mm_give_quest", npc_id=req.npc_id,
        summary=f"{req.giver_name} gave quest '{req.quest_name}' to {req.player_name}",
    )
    return {"uuid": uuid, "quest_name": req.quest_name, "assigned_to": req.player_name}


@router.post("/engine/world/create-npc")
async def create_npc(req: CreateEntityRequest, request: Request):
    """Create a new NPC entity in the KG."""
    await check_tool_access(req.npc_id, "mm_create_npc")
    from memento.tools.kg import create_entity as _cen, create_edge as _ced
    create_entity = _cen.func; create_edge = _ced.func
    uuid = await asyncio.to_thread(create_entity, req.name, "NPC", req.summary)
    if req.location_name:
        await asyncio.to_thread(
            create_edge, req.name, req.location_name, "LOCATED_IN", "",
        )
    await broadcast_tool_event(
        request, tool="mm_create_npc", npc_id=req.npc_id,
        summary=f"New NPC: {req.name}",
    )
    return {"uuid": uuid, "name": req.name, "entity_type": "NPC"}


@router.post("/engine/world/create-item")
async def create_item(req: CreateEntityRequest, request: Request):
    """Create a new item entity in the KG."""
    await check_tool_access(req.npc_id, "mm_create_item")
    from memento.tools.kg import create_entity as _cen, create_edge as _ced
    create_entity = _cen.func; create_edge = _ced.func
    uuid = await asyncio.to_thread(create_entity, req.name, "Item", req.summary)
    if req.location_name:
        await asyncio.to_thread(
            create_edge, req.name, req.location_name, "LOCATED_IN", "",
        )
    await broadcast_tool_event(
        request, tool="mm_create_item", npc_id=req.npc_id,
        summary=f"New item: {req.name}",
    )
    return {"uuid": uuid, "name": req.name, "entity_type": "Item"}


@router.post("/engine/world/create-location")
async def create_location(req: CreateEntityRequest):
    """Create a new location entity in the KG."""
    await check_tool_access(req.npc_id, "mm_create_location")
    from memento.tools.kg import create_entity as _cen
    create_entity = _cen.func
    uuid = await asyncio.to_thread(create_entity, req.name, "Location", req.summary)
    return {"uuid": uuid, "name": req.name, "entity_type": "Location"}


@router.post("/engine/world/move")
async def move_entity(req: MoveRequest, request: Request):
    """Move an NPC to a different location."""
    await check_tool_access(req.npc_id, "mm_move_to")
    from memento.tools.kg import create_edge as _ce_tool; create_edge = _ce_tool.func
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
    await broadcast_tool_event(
        request, tool="mm_move_to", npc_id=req.npc_id,
        summary=f"{req.entity_name} moved to {req.destination}",
    )
    return {"result": result, "entity": req.entity_name, "destination": req.destination}


@router.post("/engine/world/gossip")
async def send_gossip(req: GossipRequest):
    """Send a message to another NPC via Matrix."""
    # This could post to the target NPC's Matrix room
    # For now, just record it as an event
    from memento.tools.kg import remember_event as _remember_tool; _remember = _remember_tool.func
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

class NarrateRequest(BaseModel):
    action: str = Field(..., max_length=2000, description="Player action(s) to narrate")
    context: str = Field("", max_length=4000, description="Scene context from world search")
    events: str = Field("", max_length=2000, description="Detected events summary")
    mode: str = Field("action", max_length=20, description="Narration mode: action, intro, rejection")
    npc_id: str = Field("", max_length=64)


def _locked(fn):
    """Run a function inside the engine lock."""
    def wrapper(*args, **kwargs):
        with _engine_lock:
            return fn(*args, **kwargs)
    return wrapper


@router.post("/engine/combat/resolve")
async def resolve_combat(req: CombatResolveRequest, request: Request):
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
    summary = f"{req.attacker} vs {req.target}: {state.resolution or state.action_type}"
    if state.target_dead:
        summary += f" — {req.target} slain!"
    await broadcast_tool_event(
        request, tool="mm_resolve_combat", npc_id=req.npc_id,
        summary=summary,
    )
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


@router.post("/engine/narrate")
async def narrate(req: NarrateRequest, request: Request):
    """Run the narration crew, broadcast the result, and enrich episode lore stubs.

    The room narrator agent calls this after gathering context via mm_search_world.
    After narration, enriches entities at the agent's location so lore stubs from
    the latest episode become full KG entities with attributes and art.
    """
    await check_tool_access(req.npc_id, "mm_narrate")

    def _run():
        from memento.crews.narrative.narration import make_narration_crew
        with _engine_lock:
            crew = make_narration_crew(
                action=req.action,
                context=req.context,
                events=req.events,
                mode=req.mode,
            )
            return crew.kickoff().raw

    narrative = await asyncio.to_thread(_run)

    # Broadcast as narrative channel event
    await broadcast_tool_event(
        request,
        tool="mm_narrate",
        npc_id=req.npc_id,
        summary=narrative,
    )

    # Enrich lore stubs from the latest episode — runs in background thread
    # Pulls the specific episode entities that match our game ontology types
    # (NewEntitySeed, QuestSeed, LocationChange, LoreSeed) and enriches those.
    if req.npc_id:
        import threading

        def _enrich_episode_stubs():
            try:
                from memento.bonfires_client import get_client
                from memento.rpg_types import RPG_ENTITY_TYPES
                from memento.flows.enrichment import enrich_entity
                from memento.models.attributes import needs_enrichment
                import json
                import logging
                _log = logging.getLogger(__name__)

                client = get_client()

                # Resolve the Room NPC's agent_id to get its latest episode
                agent_id = req.npc_id
                episode = client.kg.get_latest_episode(agent_id)
                if not episode:
                    return

                # Extract entities from episode that match our ontology
                stubs: list[dict] = []
                for entity in episode.get("entities", []):
                    labels = entity.get("labels", [])
                    for label in labels:
                        if label in RPG_ENTITY_TYPES:
                            stubs.append(entity)
                            break

                # Also check edges for typed targets
                for edge in episode.get("edges", []):
                    node = edge.get("target", {})
                    labels = node.get("labels", [])
                    for label in labels:
                        if label in RPG_ENTITY_TYPES:
                            stubs.append(node)
                            break

                if not stubs:
                    return

                _log.info("Enriching %d episode stubs after narration", len(stubs))
                for stub in stubs:
                    entity_uuid = stub.get("uuid", "")
                    if not entity_uuid:
                        continue
                    try:
                        entity = client.kg.get_entity(entity_uuid)
                        attrs = entity.get("attributes", {})
                        if isinstance(attrs, str):
                            attrs = json.loads(attrs) if attrs else {}
                        summary = entity.get("summary", "")
                        entity_name = entity.get("name", "")
                        entity_labels = entity.get("labels", [])

                        # Determine entity type for enrichment
                        entity_type = "npc"
                        for label in entity_labels:
                            if label in ("Item",):
                                entity_type = "item"
                            elif label in ("Location",):
                                entity_type = "location"
                            elif label in ("Quest",):
                                entity_type = "quest"

                        missing = needs_enrichment(entity_type, attrs)
                        if missing:
                            enrich_entity(entity_uuid, entity_name, entity_type, summary, attrs, missing)
                    except Exception:
                        _log.debug("Enrichment skipped for stub %s", entity_uuid, exc_info=True)

            except Exception:
                import logging
                logging.getLogger(__name__).warning("Episode stub enrichment failed", exc_info=True)

        threading.Thread(target=_enrich_episode_stubs, daemon=True).start()

    return {"narrative": narrative}


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
    from memento.tools.kg import remember_event as _remember_tool; _remember = _remember_tool.func
    result = await asyncio.to_thread(_remember, req.summary)
    return {"result": result}


# ── NPC Response (tool-first dialogue) ──

class NpcResponseRequest(BaseModel):
    dialogue: str = Field(..., max_length=2000)
    emotion: str = Field("", max_length=50)
    target: str = Field("", max_length=200)
    npc_id: str = Field("", max_length=64)


@router.post("/engine/npc-response")
async def npc_response(req: NpcResponseRequest, request: Request):
    """NPC speaks in-character — broadcasts to WS hub + pushes to Delve stack."""
    npc_name = resolve_npc_name(req.npc_id)
    location = resolve_npc_location(req.npc_id)

    await broadcast_tool_event(
        request,
        tool="mm_npc_response",
        npc_id=req.npc_id,
        summary=req.dialogue,
        data={"emotion": req.emotion, "target": req.target},
    )

    # Push to narrator stack so heartbeat/narrator see the dialogue
    narrator_registry = getattr(request.app.state, "narrator_registry", None)
    push_to_stack(req.dialogue, npc_name, location, narrator_registry)

    return {"status": "ok"}


# ── NPC Intra-Room Movement ──

class MoveWithinRequest(BaseModel):
    target_x: int = Field(..., ge=0, description="Target x coordinate in the room grid")
    target_y: int = Field(..., ge=0, description="Target y coordinate in the room grid")
    npc_id: str = Field("", max_length=64)


@router.post("/engine/move-within")
async def move_within(req: MoveWithinRequest, request: Request):
    """Move an NPC to a different position within the current room.

    Validates walkability, updates KG position, and broadcasts position_update to clients.
    """
    from gateway.npc_registry import resolve_npc_kg_uuid

    npc_name = resolve_npc_name(req.npc_id)
    location = resolve_npc_location(req.npc_id)
    npc_uuid = resolve_npc_kg_uuid(req.npc_id)

    if not npc_uuid:
        return {"success": False, "error": "Cannot resolve NPC UUID"}

    # Get current position + room map
    from memento.bonfires_client import get_client
    client = await asyncio.to_thread(get_client)

    entity = await asyncio.to_thread(client.kg.get_entity, npc_uuid)
    if isinstance(entity, dict) and "entity" in entity:
        entity = entity["entity"]

    # Find location UUID from edges
    location_uuid = ""
    try:
        edges = await asyncio.to_thread(
            client.kg.get_edges, npc_uuid,
            direction="outgoing", edge_type="LOCATED_IN",
        )
        if edges:
            target = edges[0].get("target", {})
            location_uuid = target.get("uuid", target.get("id", ""))
    except Exception:
        pass

    # Get current position from room manifest
    current_x, current_y = 0, 0
    room_width, room_height = 35, 18
    tiles = []
    if location_uuid:
        try:
            from memento.room_manifest import get_room_manifest
            manifest = await asyncio.to_thread(get_room_manifest, location_uuid)
            room_width = manifest.get("width", 35)
            room_height = manifest.get("height", 18)
            tiles = manifest.get("tiles", [])
            npc_lower = npc_name.lower()
            for npc in manifest.get("npcs", []):
                if npc.get("name", "").lower() == npc_lower:
                    current_x, current_y = npc.get("x", 0), npc.get("y", 0)
                    break
        except Exception:
            pass

    # Validate range (Manhattan distance <= 5)
    distance = abs(req.target_x - current_x) + abs(req.target_y - current_y)
    if distance > 5:
        return {"success": False, "error": f"Too far: {distance} tiles (max 5)"}

    # Validate bounds
    if req.target_x >= room_width or req.target_y >= room_height:
        return {"success": False, "error": f"Out of bounds ({room_width}x{room_height})"}

    # Validate walkability
    if tiles:
        idx = req.target_y * room_width + req.target_x
        tile = tiles[idx] if idx < len(tiles) else "#"
        if tile in ("#", " "):
            return {"success": False, "error": f"Tile ({req.target_x},{req.target_y}) is blocked"}

    # Broadcast position_update to clients
    ws_hub = getattr(request.app.state, "ws_hub", None)
    if ws_hub and location:
        await ws_hub.broadcast_to_location(location, {
            "type": "position_update",
            "entity_id": npc_uuid,
            "x": req.target_x,
            "y": req.target_y,
        })

    # Also broadcast as tool_event badge
    await broadcast_tool_event(
        request, tool="mm_move_within", npc_id=req.npc_id,
        summary=f"{npc_name} moved to ({req.target_x},{req.target_y})",
    )

    return {
        "success": True,
        "from": {"x": current_x, "y": current_y},
        "to": {"x": req.target_x, "y": req.target_y},
        "distance": distance,
    }


class RoomManifestRequest(BaseModel):
    location_uuid: str


@router.post("/engine/room-manifest")
async def room_manifest(req: RoomManifestRequest):
    """Get complete room manifest — all NPCs, items, players, exits, tile map."""
    from memento.room_manifest import get_room_manifest
    result = await asyncio.to_thread(get_room_manifest, req.location_uuid)
    return result


# ── Inventory Tools (NPC agents use these for trade, loot inspection) ──

class InventoryQueryRequest(BaseModel):
    entity_id: str = Field(..., max_length=64, description="Player or NPC UUID")
    npc_id: str = Field("", max_length=64)


class InventoryTransferRequest(BaseModel):
    item_id: str = Field(..., max_length=64)
    from_entity: str = Field(..., max_length=64, description="Current owner UUID")
    to_entity: str = Field(..., max_length=64, description="New owner UUID")
    quantity: int = Field(1, ge=1)
    npc_id: str = Field("", max_length=64)


@router.post("/engine/inventory")
async def get_entity_inventory(req: InventoryQueryRequest):
    """Get inventory for any entity (player or NPC). Used by merchant NPCs."""
    await check_tool_access(req.npc_id, "mm_inventory")
    from memento.inventory_manifest import get_inventory_manifest
    manifest = await asyncio.to_thread(get_inventory_manifest, req.entity_id)
    return manifest


@router.post("/engine/inventory/transfer")
async def transfer_item(req: InventoryTransferRequest, request: Request):
    """Transfer an item between entities. Used for NPC trade resolution."""
    await check_tool_access(req.npc_id, "mm_inventory_transfer")

    from memento.bonfires_client import get_client
    from memento.tools import chain as _chain

    client = await asyncio.to_thread(get_client)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    # Expire CARRIES from old owner
    try:
        edges = await asyncio.to_thread(
            client.kg.get_edges, req.from_entity,
            direction="outgoing", edge_type="CARRIES",
        )
        for edge in edges:
            target = edge.get("target", {})
            tid = target.get("uuid", target.get("id", ""))
            if tid == req.item_id and not (edge.get("expired_at") or edge.get("invalid_at")):
                edge_uuid = edge.get("uuid", edge.get("id", ""))
                if edge_uuid:
                    await asyncio.to_thread(
                        client.kg.update_edge, edge_uuid, {"expired_at": now},
                    )
                    break
    except Exception:
        pass

    # Create CARRIES to new owner
    await asyncio.to_thread(
        client.kg.create_edge,
        req.to_entity, req.item_id, "CARRIES",
        f"Traded item",
    )

    # Chain update
    _chain.transfer_item(req.item_id, req.to_entity)

    await broadcast_tool_event(
        request, tool="mm_inventory_transfer", npc_id=req.npc_id,
        summary=f"Item traded (id: {req.item_id[:8]}...)",
    )
    return {"status": "ok", "item_id": req.item_id,
            "from": req.from_entity, "to": req.to_entity}


# ── World Heartbeat ──

class HeartbeatRequest(BaseModel):
    npc_id: str = Field("", max_length=64)

@router.post("/engine/heartbeat")
async def trigger_heartbeat(req: HeartbeatRequest):
    """Trigger world evolution — processes stack and generates new content.

    Callable by NPC agents when something significant happens.
    Skips if the stack is empty or already processing.
    """
    def _run():
        from memento.heartbeat import HeartbeatRunner
        return HeartbeatRunner().run()

    result = await asyncio.to_thread(_run)
    return result


# ── World Reaction ──

class WorldReactionRequest(BaseModel):
    npc_id: str = Field("", max_length=64)
    entities_json: str = Field(..., description="JSON array of entity seeds")
    location: str = Field(..., max_length=200)
    location_uuid: str = Field(..., max_length=64)
    episode_summary: str = Field("", max_length=5000)

@router.post("/engine/world/react")
async def trigger_world_reaction(req: WorldReactionRequest):
    """Process world seeds and spawn entities."""
    await check_tool_access(req.npc_id, "mm_world_reaction")
    def _run():
        from memento.tools.world_reaction_tool import mm_world_reaction
        return mm_world_reaction(
            entities_json=req.entities_json,
            location=req.location,
            location_uuid=req.location_uuid,
            episode_summary=req.episode_summary,
        )
    result = await asyncio.to_thread(_run)
    return {"result": result}
