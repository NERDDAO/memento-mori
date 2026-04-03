# NPC Agents MCP Tools — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose engine crews and tools as HTTP endpoints that Bonfires AI NPC agents call via MCP tools. NPCs become autonomous actors; the engine becomes an environment narrator and mechanics toolbox.

**Architecture:** 30 FastAPI endpoints on the gateway wrap engine crews, KG tools, and mechanics functions. A single `memento-engine` HttpToolProvider in MongoDB makes them available to all NPC agents. Tool access is gated by the NPC's KG entity labels — gateway fetches labels and maps them to allowed tools. The engine's narrator crew switches to environment-only output with NPC @tags for cues.

**Tech Stack:** FastAPI (gateway routes), CrewAI (crew execution), Bonfires SDK (KG reads), MongoDB (HttpToolProvider), Matrix (NPC communication)

---

## File Structure

| File | Responsibility |
|------|---------------|
| `gateway/src/gateway/routes/engine.py` | NEW — all 30 engine tool endpoints |
| `gateway/src/gateway/engine_auth.py` | NEW — token auth + KG label-based tool gating |
| `gateway/src/gateway/app.py` | MODIFY — register engine router |
| `scripts/seed_engine_tools.py` | NEW — seed HttpToolProvider in MongoDB |
| `engine/src/memento/tools/tool_labels.py` | NEW — label → tool mapping |
| `engine/src/memento/matrix_listener.py` | MODIFY — environment-only narration |
| `engine/src/memento/crews/narrative/narration/crew.py` | MODIFY — exclude NPC dialogue |

---

## Task 1: Label-to-Tool Mapping

**Files:**
- Create: `engine/src/memento/tools/tool_labels.py`

- [ ] **Step 1: Create the mapping module**

```python
# engine/src/memento/tools/tool_labels.py
"""Maps KG entity labels to allowed engine tools.

An NPC's KG labels determine which tools it can call.
Gateway fetches the NPC's labels and checks against this map.
"""

# Tier 1 — innate, every NPC gets these regardless of labels
INNATE_TOOLS = frozenset({
    "mm_get_state",
    "mm_get_world_time",
    "mm_search_world",
    "mm_get_entity",
    "mm_skill_check",
    "mm_calculate_damage",
    "mm_evaluate_disposition",
    "mm_send_gossip",
})

# Tier 2 & 3 — label grants access
LABEL_TOOLS: dict[str, set[str]] = {
    "Combat": {
        "mm_resolve_combat",
        "mm_assess_combat",
        "mm_check_plausibility",
    },
    "Trade": {
        "mm_give_item",
        "mm_create_item",
    },
    "Memory": {
        "mm_remember_event",
        "mm_npc_memory",
        "mm_update_entity",
    },
    "Travel": {
        "mm_move_to",
    },
    "Explore": {
        "mm_create_location",
        "mm_create_room",
    },
    "Leadership": {
        "mm_create_npc",
        "mm_design_npc",
    },
    "QuestGiver": {
        "mm_give_quest",
        "mm_design_quest",
        "mm_write_quest_dialogue",
    },
    "MasterCraft": {
        "mm_design_item",
    },
    "Cartography": {
        "mm_design_location",
        "mm_design_region",
    },
    "Perception": {
        "mm_detect_events",
        "mm_reputation_check",
    },
}


def get_allowed_tools(labels: list[str]) -> set[str]:
    """Given an NPC's KG labels, return the set of tools it can call."""
    allowed = set(INNATE_TOOLS)
    for label in labels:
        if label in LABEL_TOOLS:
            allowed |= LABEL_TOOLS[label]
    return allowed
```

- [ ] **Step 2: Verify**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine
PYTHONPATH=src python3 -c "
from memento.tools.tool_labels import get_allowed_tools
barkeep = get_allowed_tools(['NPC', 'Combat', 'Trade', 'Memory'])
print('Barkeep tools:', sorted(barkeep))
print('Count:', len(barkeep))
"
```

- [ ] **Step 3: Commit**

```bash
git add engine/src/memento/tools/tool_labels.py
git commit -m "feat(engine): add label-to-tool mapping for NPC capability gating"
```

---

## Task 2: Engine Auth Middleware

**Files:**
- Create: `gateway/src/gateway/engine_auth.py`

- [ ] **Step 1: Create auth module**

```python
# gateway/src/gateway/engine_auth.py
"""Auth + capability gating for engine tool endpoints.

Verifies ENGINE_API_TOKEN and checks NPC's KG labels
to determine if the requested tool is allowed.
"""

import asyncio
import os
from functools import lru_cache

from fastapi import HTTPException, Header


async def verify_engine_token(authorization: str = Header("")) -> None:
    """Verify the bearer token matches ENGINE_API_TOKEN."""
    expected = os.getenv("ENGINE_API_TOKEN", "")
    if not expected:
        return  # No token configured = no auth (dev mode)
    if not authorization.startswith("Bearer ") or authorization[7:] != expected:
        raise HTTPException(status_code=403, detail="Invalid engine token")


async def check_tool_access(npc_id: str, tool_name: str) -> None:
    """Check if this NPC can call this tool based on its KG labels.

    Fetches the NPC's entity from KG, reads labels, maps to allowed tools.
    Raises 403 if the tool is not in the NPC's allowed set.
    """
    from memento.tools.tool_labels import get_allowed_tools, INNATE_TOOLS

    # Innate tools always allowed — skip KG fetch
    if tool_name in INNATE_TOOLS:
        return

    # Fetch NPC labels from KG
    try:
        from memento.bonfires_client import get_client
        client = await asyncio.to_thread(get_client)
        entity = await asyncio.to_thread(client.kg.get_entity, npc_id)
        if isinstance(entity, dict) and "entity" in entity:
            entity = entity["entity"]
        labels = entity.get("labels", []) if isinstance(entity, dict) else []
    except Exception:
        labels = []

    allowed = get_allowed_tools(labels)
    if tool_name not in allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "capability_missing",
                "tool": tool_name,
                "npc_labels": labels,
                "message": f"This NPC doesn't have access to {tool_name}. "
                           f"Required labels: check tool_labels.py mapping.",
            },
        )
```

- [ ] **Step 2: Commit**

```bash
git add gateway/src/gateway/engine_auth.py
git commit -m "feat(gateway): add engine auth and label-based tool gating"
```

---

## Task 3: Gateway Engine Routes — Tier 1 (State & Knowledge)

**Files:**
- Create: `gateway/src/gateway/routes/engine.py`
- Modify: `gateway/src/gateway/app.py`

Start with the simplest endpoints — reads and pure functions. No crews, instant or near-instant.

- [ ] **Step 1: Create engine.py with Tier 1 routes**

```python
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
```

- [ ] **Step 2: Register router in app.py**

Add to `gateway/src/gateway/app.py` after the existing router imports:

```python
from gateway.routes import action, session, state, entity, chain, engine
```

And add:

```python
app.include_router(engine.router, prefix="/api")
```

- [ ] **Step 3: Verify it starts**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/gateway
PYTHONPATH=../engine/src:src python3 -c "from gateway.routes.engine import router; print('routes:', len(router.routes))"
```

- [ ] **Step 4: Commit**

```bash
git add gateway/src/gateway/routes/engine.py gateway/src/gateway/app.py
git commit -m "feat(gateway): add Tier 1 engine routes — state, knowledge, mechanics"
```

---

## Task 4: Gateway Engine Routes — Tier 2 (World Mutation)

**Files:**
- Modify: `gateway/src/gateway/routes/engine.py`

Add world mutation endpoints. These write to the KG (and chain via dual-write).

- [ ] **Step 1: Add Tier 2 models and routes to engine.py**

Append to `gateway/src/gateway/routes/engine.py`:

```python
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
```

- [ ] **Step 2: Verify build**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/gateway
PYTHONPATH=../engine/src:src python3 -c "from gateway.routes.engine import router; print('routes:', len(router.routes))"
```

- [ ] **Step 3: Commit**

```bash
git add gateway/src/gateway/routes/engine.py
git commit -m "feat(gateway): add Tier 2 engine routes — world mutation, creation, gossip"
```

---

## Task 5: Gateway Engine Routes — Tier 3 (Crew-Powered)

**Files:**
- Modify: `gateway/src/gateway/routes/engine.py`

Add crew-powered endpoints. These call CrewAI crews with LLM calls and take 2-30s. All run inside `_engine_lock`.

- [ ] **Step 1: Add Tier 3 models and routes**

Append to `gateway/src/gateway/routes/engine.py`:

```python
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
    """Full combat pipeline: assess → resolve → consequences → death check."""
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
```

- [ ] **Step 2: Verify route count**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/gateway
PYTHONPATH=../engine/src:src python3 -c "from gateway.routes.engine import router; print('routes:', len(router.routes))"
```

Expected: ~25+ routes

- [ ] **Step 3: Commit**

```bash
git add gateway/src/gateway/routes/engine.py
git commit -m "feat(gateway): add Tier 3 engine routes — combat, design crews, world building"
```

---

## Task 6: MongoDB Tool Seed Script

**Files:**
- Create: `scripts/seed_engine_tools.py`

A Python script that inserts the `HttpToolProvider` document into the Bonfires MongoDB. This makes all 30 tools available to NPC agents.

- [ ] **Step 1: Create the seed script**

```python
#!/usr/bin/env python3
"""Seed the memento-engine HttpToolProvider in MongoDB.

Usage:
    python scripts/seed_engine_tools.py

Requires MONGO_URI env var pointing to the Bonfires MongoDB.
"""

import os
import sys
from pymongo import MongoClient

PROVIDER = {
    "providerId": "memento-engine",
    "providerName": "Memento Mori Game Engine",
    "description": "Game mechanics tools for NPC agents — combat, skill checks, world queries, world building",
    "enabled": True,
    "baseConfig": {
        "baseUrl": "{{env:MEMENTO_GATEWAY_URL}}",
        "headers": {"Content-Type": "application/json"},
        "auth": {
            "type": "bearer",
            "keyName": "Authorization",
            "valueTemplate": "Bearer {{env:ENGINE_API_TOKEN}}",
        },
        "defaultTimeout": 60000,
    },
    "tools": [
        # Tier 1 — State & Knowledge
        {
            "id": "mm_get_state", "name": "Get Entity State",
            "description": "Get an entity's current state from the knowledge graph — HP, inventory, labels, edges, recent events. Call this before responding to check your current condition.",
            "enabled": True,
            "httpConfig": {"endpoint": "/api/engine/state", "method": "POST",
                           "bodyTemplate": {"entity_name": "{{entity_name}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "entity_name": {"type": "string", "description": "Entity name to look up"}
            }, "required": ["entity_name"]},
        },
        {
            "id": "mm_get_world_time", "name": "Get World Time",
            "description": "Get current in-game time — moon phase, date, time of day, season.",
            "enabled": True,
            "httpConfig": {"endpoint": "/api/engine/world/time", "method": "GET"},
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "id": "mm_search_world", "name": "Search World",
            "description": "Search the game world's knowledge graph for entities, locations, NPCs, items, relationships, and lore.",
            "enabled": True,
            "httpConfig": {"endpoint": "/api/engine/world/search", "method": "POST",
                           "bodyTemplate": {"query": "{{query}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "query": {"type": "string", "description": "Search query"}
            }, "required": ["query"]},
        },
        {
            "id": "mm_get_entity", "name": "Get Entity Details",
            "description": "Get detailed information about a specific game entity by name.",
            "enabled": True,
            "httpConfig": {"endpoint": "/api/engine/world/entity", "method": "POST",
                           "bodyTemplate": {"name": "{{name}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "name": {"type": "string", "description": "Entity name"}
            }, "required": ["name"]},
        },
        {
            "id": "mm_skill_check", "name": "Roll Skill Check",
            "description": "Roll a d20 skill check. Returns PASS or FAIL with margin. Use for persuasion, stealth, lockpicking, any non-combat check.",
            "enabled": True,
            "httpConfig": {"endpoint": "/api/engine/skill-check", "method": "POST",
                           "bodyTemplate": {"skill_level": "{{skill_level}}", "difficulty": "{{difficulty}}", "modifiers": "{{modifiers}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "skill_level": {"type": "number", "description": "Skill level (0-30)"},
                "difficulty": {"type": "number", "description": "Difficulty class (1-40)"},
                "modifiers": {"type": "number", "description": "Situational modifier", "default": 0},
            }, "required": ["skill_level", "difficulty"]},
        },
        {
            "id": "mm_calculate_damage", "name": "Calculate Damage",
            "description": "Calculate final damage from weapon damage, strength, and armor.",
            "enabled": True,
            "httpConfig": {"endpoint": "/api/engine/damage", "method": "POST",
                           "bodyTemplate": {"weapon_damage": "{{weapon_damage}}", "attacker_strength": "{{attacker_strength}}", "defender_armor": "{{defender_armor}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "weapon_damage": {"type": "number"}, "attacker_strength": {"type": "number"}, "defender_armor": {"type": "number"},
            }, "required": ["weapon_damage", "attacker_strength", "defender_armor"]},
        },
        {
            "id": "mm_evaluate_disposition", "name": "Evaluate Disposition",
            "description": "Calculate how an interaction shifts friendship and trust.",
            "enabled": True,
            "httpConfig": {"endpoint": "/api/engine/disposition", "method": "POST",
                           "bodyTemplate": {"current_friendship": "{{current_friendship}}", "current_trust": "{{current_trust}}", "interaction_type": "{{interaction_type}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "current_friendship": {"type": "number"}, "current_trust": {"type": "number"},
                "interaction_type": {"type": "string", "enum": ["friendly_conversation", "hostile_action", "gift", "betrayal", "help_in_combat", "theft", "trade"]},
            }, "required": ["current_friendship", "current_trust", "interaction_type"]},
        },
        # Tier 2 — World Mutation
        {
            "id": "mm_remember_event", "name": "Remember Event",
            "description": "Record a significant event in the world's memory. Use for deaths, discoveries, betrayals, victories. The world will remember this.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/world/remember", "method": "POST",
                           "bodyTemplate": {"summary": "{{summary}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "summary": {"type": "string", "description": "What happened"}
            }, "required": ["summary"]},
        },
        {
            "id": "mm_update_entity", "name": "Update Entity",
            "description": "Update an entity's summary or labels in the knowledge graph.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/world/update-entity", "method": "POST",
                           "bodyTemplate": {"name": "{{name}}", "new_summary": "{{new_summary}}", "new_labels": "{{new_labels}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "name": {"type": "string"}, "new_summary": {"type": "string"}, "new_labels": {"type": "string"},
            }, "required": ["name"]},
        },
        {
            "id": "mm_give_item", "name": "Give Item",
            "description": "Transfer an item from one entity to another. Use for quest rewards, trades, theft.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/world/give-item", "method": "POST",
                           "bodyTemplate": {"item_name": "{{item_name}}", "from_entity": "{{from_entity}}", "to_entity": "{{to_entity}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "item_name": {"type": "string"}, "from_entity": {"type": "string"}, "to_entity": {"type": "string"},
            }, "required": ["item_name", "from_entity", "to_entity"]},
        },
        {
            "id": "mm_give_quest", "name": "Give Quest",
            "description": "Create a quest and assign it to a player.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/world/give-quest", "method": "POST",
                           "bodyTemplate": {"quest_name": "{{quest_name}}", "description": "{{description}}", "giver_name": "{{giver_name}}", "player_name": "{{player_name}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "quest_name": {"type": "string"}, "description": {"type": "string"},
                "giver_name": {"type": "string"}, "player_name": {"type": "string"},
            }, "required": ["quest_name", "description", "giver_name", "player_name"]},
        },
        {
            "id": "mm_create_npc", "name": "Create NPC",
            "description": "Create a new NPC entity in the world.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/world/create-npc", "method": "POST",
                           "bodyTemplate": {"name": "{{name}}", "entity_type": "NPC", "summary": "{{summary}}", "location_name": "{{location_name}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "name": {"type": "string"}, "summary": {"type": "string"}, "location_name": {"type": "string"},
            }, "required": ["name", "summary"]},
        },
        {
            "id": "mm_create_item", "name": "Create Item",
            "description": "Create a new item in the world. Use for crafting, forging, finding.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/world/create-item", "method": "POST",
                           "bodyTemplate": {"name": "{{name}}", "entity_type": "Item", "summary": "{{summary}}", "location_name": "{{location_name}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "name": {"type": "string"}, "summary": {"type": "string"}, "location_name": {"type": "string"},
            }, "required": ["name", "summary"]},
        },
        {
            "id": "mm_create_location", "name": "Create Location",
            "description": "Discover or build a new location in the world.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/world/create-location", "method": "POST",
                           "bodyTemplate": {"name": "{{name}}", "entity_type": "Location", "summary": "{{summary}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "name": {"type": "string"}, "summary": {"type": "string"},
            }, "required": ["name", "summary"]},
        },
        {
            "id": "mm_move_to", "name": "Move To Location",
            "description": "Move to a different location in the world.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/world/move", "method": "POST",
                           "bodyTemplate": {"entity_name": "{{entity_name}}", "destination": "{{destination}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "entity_name": {"type": "string"}, "destination": {"type": "string"},
            }, "required": ["entity_name", "destination"]},
        },
        {
            "id": "mm_send_gossip", "name": "Send Gossip",
            "description": "Send a message to another NPC. Creates organic information flow between NPCs.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/world/gossip", "method": "POST",
                           "bodyTemplate": {"from_npc": "{{from_npc}}", "to_npc": "{{to_npc}}", "message": "{{message}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "from_npc": {"type": "string"}, "to_npc": {"type": "string"}, "message": {"type": "string"},
            }, "required": ["from_npc", "to_npc", "message"]},
        },
        # Tier 3 — Crew-Powered
        {
            "id": "mm_resolve_combat", "name": "Resolve Combat",
            "description": "Execute full combat resolution: assess, resolve attack/ability, apply consequences, check death. Returns complete outcome with authoritative entity states.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/combat/resolve", "method": "POST",
                           "bodyTemplate": {"action": "{{action}}", "attacker": "{{attacker}}", "target": "{{target}}", "location": "{{location}}", "context": "{{context}}", "attacker_stats": "{{attacker_stats}}", "target_stats": "{{target_stats}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "action": {"type": "string"}, "attacker": {"type": "string"}, "target": {"type": "string"},
                "location": {"type": "string"}, "context": {"type": "string"},
                "attacker_stats": {"type": "string"}, "target_stats": {"type": "string"},
            }, "required": ["action", "attacker", "target", "location"]},
        },
        {
            "id": "mm_assess_combat", "name": "Assess Combat",
            "description": "Evaluate a combat situation without resolving it.",
            "enabled": True,
            "httpConfig": {"endpoint": "/api/engine/combat/assess", "method": "POST",
                           "bodyTemplate": {"action": "{{action}}", "attacker": "{{attacker}}", "target": "{{target}}", "location": "{{location}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "action": {"type": "string"}, "attacker": {"type": "string"},
                "target": {"type": "string"}, "location": {"type": "string"},
            }, "required": ["action", "attacker", "target", "location"]},
        },
        {
            "id": "mm_check_plausibility", "name": "Check Plausibility",
            "description": "Check if an action is physically plausible in the current scene.",
            "enabled": True,
            "httpConfig": {"endpoint": "/api/engine/plausibility", "method": "POST",
                           "bodyTemplate": {"action": "{{action}}", "context": "{{context}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "action": {"type": "string"}, "context": {"type": "string"},
            }, "required": ["action", "context"]},
        },
        {
            "id": "mm_design_quest", "name": "Design Quest",
            "description": "Design a morally complex quest with choices, rewards, and consequences.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/design/quest", "method": "POST",
                           "bodyTemplate": {"location": "{{location}}", "npc_name": "{{npc_name}}", "player_level": "{{player_level}}", "active_quests": "{{active_quests}}", "faction_context": "{{faction_context}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "location": {"type": "string"}, "npc_name": {"type": "string"},
                "player_level": {"type": "number", "default": 1},
                "active_quests": {"type": "string"}, "faction_context": {"type": "string"},
            }, "required": ["location", "npc_name"]},
        },
        {
            "id": "mm_design_item", "name": "Design Item",
            "description": "Design thematically appropriate items with stats and lore.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/design/item", "method": "POST",
                           "bodyTemplate": {"location_name": "{{location_name}}", "rarity_budget": "{{rarity_budget}}", "num_items": "{{num_items}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "location_name": {"type": "string"}, "rarity_budget": {"type": "string", "default": "common"},
                "num_items": {"type": "number", "default": 1},
            }, "required": ["location_name"]},
        },
        {
            "id": "mm_design_npc", "name": "Design NPC",
            "description": "Design a full NPC with personality, stats, and backstory.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/design/npc", "method": "POST",
                           "bodyTemplate": {"role": "{{role}}", "location_name": "{{location_name}}", "region_context": "{{region_context}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "role": {"type": "string"}, "location_name": {"type": "string"}, "region_context": {"type": "string"},
            }, "required": ["role", "location_name"]},
        },
        {
            "id": "mm_design_location", "name": "Design Location",
            "description": "Design a full location with tile map, secrets, and atmosphere.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/design/location", "method": "POST",
                           "bodyTemplate": {"location_plan": "{{location_plan}}", "region_name": "{{region_name}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "location_plan": {"type": "string"}, "region_name": {"type": "string"},
            }, "required": ["location_plan", "region_name"]},
        },
        {
            "id": "mm_design_region", "name": "Design Region",
            "description": "Design an entire region with biome, culture, threats, and locations.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/design/region", "method": "POST",
                           "bodyTemplate": {"theme": "{{theme}}", "adjacent_regions": "{{adjacent_regions}}", "player_level": "{{player_level}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "theme": {"type": "string"}, "adjacent_regions": {"type": "string"},
                "player_level": {"type": "number", "default": 1},
            }, "required": ["theme"]},
        },
        {
            "id": "mm_npc_memory", "name": "NPC Memory",
            "description": "Record a first-person memory of a scene from your perspective.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/npc-memory", "method": "POST",
                           "bodyTemplate": {"summary": "{{summary}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "summary": {"type": "string", "description": "Your first-person memory of what happened"},
            }, "required": ["summary"]},
        },
    ],
}


def main():
    mongo_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("MONGO_DB_NAME", "bonfires_staging")
    if not mongo_uri:
        print("Error: MONGO_URI not set")
        sys.exit(1)

    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db["httptoolproviders"]

    # Upsert by providerId
    result = collection.update_one(
        {"providerId": PROVIDER["providerId"]},
        {"$set": PROVIDER},
        upsert=True,
    )

    if result.upserted_id:
        print(f"Created HttpToolProvider: {PROVIDER['providerId']} ({len(PROVIDER['tools'])} tools)")
    else:
        print(f"Updated HttpToolProvider: {PROVIDER['providerId']} ({len(PROVIDER['tools'])} tools)")

    client.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify tool count**

```bash
python3 -c "
import json
exec(open('scripts/seed_engine_tools.py').read().split('def main')[0])
print(f'Tools: {len(PROVIDER[\"tools\"])}')
for t in PROVIDER['tools']:
    print(f'  {t[\"id\"]}: {t[\"name\"]}')
"
```

- [ ] **Step 3: Commit**

```bash
git add scripts/seed_engine_tools.py
git commit -m "feat: add MongoDB seed script for memento-engine HttpToolProvider"
```

---

## Task 7: Game Loop Migration — Environment Narrator

**Files:**
- Modify: `engine/src/memento/crews/narrative/narration/crew.py`

Update the narration crew's system prompt to generate environment-only output with NPC @tags. It should never write NPC dialogue — NPCs respond themselves via their Bonfires agents.

- [ ] **Step 1: Read the current narration crew**

Read `engine/src/memento/crews/narrative/narration/crew.py` to understand the current agent prompts.

- [ ] **Step 2: Update the narrator agent's backstory/goal**

Find the Master Narrator agent (or equivalent) and update its `backstory` or `goal` to include:

Add to the narrator's instructions:
```
CRITICAL RULES:
- NEVER write dialogue for NPCs. They will speak for themselves.
- NEVER write actions for NPCs (e.g., "Roric reaches for his hammer"). They decide their own actions.
- DO describe the environment, atmosphere, sounds, smells, weather, lighting.
- DO tag NPCs with @username when they would notice or react to something.
- Example: "The tavern falls silent as blood drips on the floorboards. @roric sets down the glass he was cleaning. @elara's hand moves to her blade."
- This tells the NPCs to react, without speaking for them.
```

- [ ] **Step 3: Commit**

```bash
git add engine/src/memento/crews/narrative/narration/crew.py
git commit -m "refactor(engine): narration crew generates environment only, tags NPCs"
```

---

## Task 8: Integration Test

**Files:**
- Create: `engine/tests/test_engine_routes.py`

- [ ] **Step 1: Write tests for the engine routes**

```python
# engine/tests/test_engine_routes.py
"""Tests for engine tool endpoints. Requires gateway to be importable."""

import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("BONFIRE_API_KEY"),
    reason="BONFIRE_API_KEY not set — skip integration tests",
)


def test_tool_labels():
    from memento.tools.tool_labels import get_allowed_tools
    # Barkeep with Combat, Trade, Memory labels
    tools = get_allowed_tools(["NPC", "Combat", "Trade", "Memory"])
    assert "mm_get_state" in tools  # innate
    assert "mm_resolve_combat" in tools  # Combat label
    assert "mm_give_item" in tools  # Trade label
    assert "mm_remember_event" in tools  # Memory label
    assert "mm_design_region" not in tools  # no Cartography label


def test_tool_labels_empty():
    from memento.tools.tool_labels import get_allowed_tools
    tools = get_allowed_tools([])
    assert "mm_get_state" in tools  # innate always
    assert "mm_resolve_combat" not in tools  # no Combat label


def test_tool_labels_all():
    from memento.tools.tool_labels import get_allowed_tools, LABEL_TOOLS, INNATE_TOOLS
    all_labels = list(LABEL_TOOLS.keys())
    tools = get_allowed_tools(all_labels)
    # Should have innate + all label tools
    expected = set(INNATE_TOOLS)
    for label_tools in LABEL_TOOLS.values():
        expected |= label_tools
    assert tools == expected


def test_seed_script_provider_structure():
    """Verify the seed script's PROVIDER dict is well-formed."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("seed", "scripts/seed_engine_tools.py")
    mod = importlib.util.module_from_spec(spec)
    # Only load the module-level code, not main()
    exec(open("scripts/seed_engine_tools.py").read().split("def main")[0])
    # PROVIDER should be in local scope
    assert PROVIDER["providerId"] == "memento-engine"
    assert len(PROVIDER["tools"]) >= 25
    # Every tool has required fields
    for tool in PROVIDER["tools"]:
        assert "id" in tool
        assert "name" in tool
        assert "httpConfig" in tool
        assert "inputSchema" in tool
```

- [ ] **Step 2: Run tests**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine
PYTHONPATH=src python3 -m pytest tests/test_engine_routes.py -v
```

- [ ] **Step 3: Commit**

```bash
git add engine/tests/test_engine_routes.py
git commit -m "test: add engine route and tool label tests"
```

---

## Verification

1. **Start gateway**: `bash start.sh` — verify `/api/engine/world/time` returns game time
2. **Test auth**: `curl -H "Authorization: Bearer wrong" localhost:8080/api/engine/world/time` → 403
3. **Test tool gating**: call `mm_resolve_combat` with an NPC that lacks the "Combat" label → 403 with capability_missing
4. **Test skill check**: `curl -X POST -H "Content-Type: application/json" -d '{"skill_level":10,"difficulty":15}' localhost:8080/api/engine/skill-check` → PASS/FAIL result
5. **Seed MongoDB**: `python scripts/seed_engine_tools.py` → creates HttpToolProvider
6. **Create test NPC agent** in MongoDB with `enabledMcpTools: ["memento-engine"]`, platform: matrix
7. **Send message** to NPC's Matrix room → NPC calls engine tools → responds in character
