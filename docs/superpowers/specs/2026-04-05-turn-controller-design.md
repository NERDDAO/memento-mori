# TurnController — Episode-Driven Orchestration

Replaces the current `RoundController` with a Delve-integrated turn pipeline. Graphiti custom types drive crew routing via structured episode extraction. Vector similarity selects which types to request per turn — zero LLM calls for type selection.

## Context

The current `RoundController` (`engine/src/memento/round_controller.py`) is a stoplight orchestrator that runs 5-8 LLM calls per turn regardless of complexity. It hardcodes `"unknown"` for combat targets and quest NPCs, uses a global `threading.Lock` that serializes all locations, and sleeps 15 seconds for NPC responses even when none are present.

## Architecture

### Turn Lifecycle

```
Round closes (RoundManager batch window or solo fast-path)
  1. round_callback sends player actions to Matrix room
     (NPC agents see and respond to these)
  2. Vector match action text against type descriptions → requested_types
  3. stack.add(messages, requested_types) + trigger immediate processing
  4. Graphiti add_episode extracts structured entities for matching types
  5. CrewRouter reads extracted types → fires only relevant crews
  6. NPC wait (event-driven, exits early when all respond or timeout)
  7. Narrate (episode summary + crew results)
  8. Post-turn (time advance, scene art fire-and-forget, state update)
```

### What Changes vs. What Stays

**Stays:**
- `RoundManager` batching (20s window / solo fast-path)
- `round_callback` sending actions to Matrix rooms
- `EngineMatrixListener` picking up batches
- Matrix as NPC communication channel
- CrewAI crews for combat, quest, narration
- Gateway <-> Client WebSocket protocol

**Changes:**
- `RoundController` replaced by `TurnController` (new file)
- Global `_turn_lock` replaced by per-location `LocationLockManager`
- Event detection replaced by Delve episode extraction with world seed custom types
- Classification/detector/merge crews eliminated — inline actions handled by NPC tools
- Context crew eliminated (episode summary replaces it)
- Plausibility check eliminated — entity resolution handles structural impossibility (target not here, item not owned); creative impossibility ("I fly to the moon") is handled by the narration crew which narrates failed actions as in-world failures
- New `WorldReactionCrew` creates entities/quests/lore from episode-extracted seeds
- NPC wait: fixed 15s sleep replaced by event-driven poll with early exit
- Narration cooldown: module-level dict replaced by persistent JSON file
- Transport protocol decouples Matrix from controller logic
- UUID everywhere (quest queries, entity refs, location lookups)
- Scene art re-enabled as fire-and-forget post-turn
- Subsystem warnings get human-readable detail strings

## Components

### 1. RPG Custom Types — World Reaction Seeds

Pydantic models registered with Delve's Graphiti as custom entity types. These are **not action replays** — combat, movement, and inventory are already handled inline by NPC tool calls during the round. These types represent **world consequences** that the episode extraction discovers: new entities, quests, location changes, and lore that should exist as a result of what happened.

```python
# engine/src/memento/rpg_types.py

class NewEntitySeed(BaseModel):
    """Extracted when conversation implies a new NPC, creature, or item should exist in the world."""
    entity_name: str
    entity_type: str = ""      # npc, item, creature
    location: str = ""
    description: str = ""
    source_context: str = ""   # what in the conversation implied this entity

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["NewEntitySeed"]

class QuestSeed(BaseModel):
    """Extracted when interaction suggests a quest opportunity or quest progression."""
    quest_name: str = ""
    giver_name: str = ""       # NPC who triggered it
    objective_hint: str = ""   # what needs to be done
    trigger_context: str = ""  # what in the conversation triggered this

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["QuestSeed"]

class LocationChange(BaseModel):
    """Extracted when the room state should change as a consequence of actions."""
    location: str = ""
    change_description: str = ""  # "door opened", "fire started", "rubble collapsed"
    new_exits: list[str] = []     # new exits/passages revealed
    removed_features: list[str] = []  # features destroyed/removed

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["LocationChange"]

class LoreSeed(BaseModel):
    """Extracted when new world lore is revealed or created during conversation."""
    lore_topic: str = ""
    content: str = ""
    source_npc: str = ""       # who revealed it
    related_locations: list[str] = []

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["LoreSeed"]
```

**Important distinction:** Inline actions (combat, movement, trade, inventory) are resolved by NPC agents via MCP tool calls during the round. The custom types above are for **world reactions** — things the world should create or change in response to what happened. The WorldReactionCrew reads these seeds and orchestrates entity creation.

### 2. Type Selector (Vector Matching)

Runs in the engine (called by `EngineMatrixListener` after receiving the batch from Matrix, before pushing to Delve stack). Embeds type descriptions once at startup, then cosine similarity against incoming action text.

```python
# engine/src/memento/type_selector.py

class TypeSelector:
    """Vector-match action text against RPG type descriptions."""

    def __init__(self, threshold: float = 0.3):
        self.threshold = threshold  # lenient — over-include is fine
        self.types: dict[str, type[BaseModel]] = {}
        self.embeddings: dict[str, list[float]] = {}

    def register(self, name: str, model: type[BaseModel]) -> None:
        """Register a type. Embeds the docstring for matching."""
        self.types[name] = model
        self.embeddings[name] = embed(model.__doc__ or name)

    def select(self, action_text: str) -> list[str]:
        """Return type names whose descriptions are similar to the action."""
        action_emb = embed(action_text)
        selected = []
        for name, type_emb in self.embeddings.items():
            if cosine_similarity(action_emb, type_emb) >= self.threshold:
                selected.append(name)
        return selected
```

Lenient threshold (0.3) means "when in doubt, include it." Graphiti won't extract a type that doesn't apply — no harm in over-requesting. The type descriptions in the Pydantic docstrings are the matching corpus.

### 3. Delve Stack Extension — Per-Caller Custom Types

Extends the Delve stack to accept `requested_types` per message. At process time, the stack unions all requested types across messages and passes them to episode creation.

**Delve changes (delve/ repo):**

- `StackMessage` gets optional `requested_types: list[str]` field
- `Stack` model gets `requested_types: list[str]` field (accumulated across adds)
- `stack.add()` merges message types into the stack's accumulated set
- `_process_stack_background()` reads the accumulated set, resolves type names via a type registry, passes to `create_single_episode(custom_types_config=...)`
- Stack clears `requested_types` after processing (same lifecycle as clearing messages)

**Type registry:**

A dict mapping type names to Pydantic models. RPG types are registered at bonfire configuration time. Starts as a simple module-level dict, can evolve to config-driven later.

```python
# delve: type_registry.py
ENTITY_REGISTRY: dict[str, type[BaseModel]] = {
    # Built-in
    "User": User,
    "TaxonomyLabel": TaxonomyLabel,
    "Update": Update,
    # RPG types (registered by memento-mori bonfire)
    "CombatAction": CombatAction,
    "QuestInteraction": QuestInteraction,
    "SocialInteraction": SocialInteraction,
    "TradeAction": TradeAction,
    "MovementAction": MovementAction,
}
```

**Immediate processing:** The game engine triggers stack processing immediately after adding messages (bypass the 20-min cycle). The existing `process_stack_task` can be invoked on demand.

### 4. WorldReactionCrew

An orchestrator crew that reads extracted world seeds from the episode and creates new entities, quests, location changes, and lore in the KG. Does NOT re-resolve inline actions (combat, movement) — those are already handled by NPC tool calls.

```python
# engine/src/memento/world_reaction.py

class WorldReactionCrew:
    """Orchestrates entity creation from episode-extracted world seeds."""

    def react(self, extracted_entities: list[dict], ctx: TurnContext) -> dict:
        """Process all extracted seeds. Returns summary of what was created."""
        results = {}
        for entity in extracted_entities:
            entity_type = entity.get("type", "")
            try:
                if entity_type == "NewEntitySeed":
                    results["new_entities"] = results.get("new_entities", [])
                    results["new_entities"].append(self._create_entity(entity, ctx))
                elif entity_type == "QuestSeed":
                    results["new_quests"] = results.get("new_quests", [])
                    results["new_quests"].append(self._create_quest(entity, ctx))
                elif entity_type == "LocationChange":
                    results["location_changes"] = results.get("location_changes", [])
                    results["location_changes"].append(self._apply_location_change(entity, ctx))
                elif entity_type == "LoreSeed":
                    results["lore"] = results.get("lore", [])
                    results["lore"].append(self._persist_lore(entity, ctx))
            except Exception:
                logger.warning("World reaction failed for %s", entity_type, exc_info=True)
        return results
```

Each handler creates KG entities/edges via the Bonfires SDK. Entity resolution for existing entities (NPCs, items, locations referenced by name) uses `kg.search()` to find UUIDs — this is the inline resolution that happens during seed processing, not a separate step.

### 5. TurnController

The main orchestrator. Thin pipeline that coordinates the above components.

```python
# engine/src/memento/turn_controller.py

class TurnController:
    def __init__(
        self,
        location: str,
        location_uuid: str,
        actions: list[dict],
        transport: Transport,
        type_selector: TypeSelector,
        world_reaction: WorldReactionCrew,
        npc_wait: float = 15.0,
    ): ...

    def run(self) -> tuple[str, dict]:
        try:
            return self._run_inner()
        except Exception:
            logger.error("TurnController.run() failed", exc_info=True)
            self.transport.emit_phase(self.location, "ready", None)
            return "", self._build_state_update(warnings=["round_failed"])

    def _run_inner(self) -> tuple[str, dict]:
        # 1. Type selection (vector match — zero LLM calls)
        requested_types = self.type_selector.select(self.combined_action)

        # 2. Ingest to Delve stack + trigger processing
        episode = self._ingest_and_extract(requested_types)

        # 3. NPC wait (event-driven) — NPCs respond to actions in Matrix
        self._await_npcs()

        # 4. World reactions — create new entities/quests/lore from seeds
        reaction_results = self.world_reaction.react(
            episode.get("entities", []),
            self._build_turn_context(),
        )

        # 5. Narrate (episode summary + world reaction results)
        narrative = self._narrate(episode, reaction_results)

        # 6. Post-turn
        if narrative:
            self._post_turn()

        self.transport.emit_phase(self.location, "ready", None)
        return narrative, self._build_state_update()
```

### 6. Transport Protocol

Decouples the controller from Matrix. Controller receives a `Transport` at construction.

```python
# engine/src/memento/transport.py

class Transport(Protocol):
    def emit_phase(self, location: str, phase: str, crew: str | None) -> None: ...
    def emit_art(self, location: str, art_text: str) -> None: ...
    def get_npc_count(self, location: str) -> int: ...
    def get_npc_response_count(self, location: str) -> int: ...
    def clear_npc_responses(self, location: str) -> None: ...

class MatrixTransport:
    """Wraps nio.AsyncClient + event loop for thread-safe calls from worker thread."""
    def __init__(self, client: nio.AsyncClient, room_id: str, loop: asyncio.AbstractEventLoop): ...

class NullTransport:
    """No-op for tests."""
```

### 7. LocationLockManager

Per-location threading locks replacing the global `_turn_lock`.

```python
# engine/src/memento/lock_manager.py

class LocationLockManager:
    _locks: dict[str, threading.Lock] = {}
    _meta_lock = threading.Lock()

    @classmethod
    def acquire(cls, location: str) -> threading.Lock:
        with cls._meta_lock:
            if location not in cls._locks:
                cls._locks[location] = threading.Lock()
            return cls._locks[location]
```

### 8. NarrationCooldown (Persistent)

JSON file-backed cooldown that survives engine restarts.

```python
# engine/src/memento/narration_cooldown.py

class NarrationCooldown:
    COOLDOWN = 30.0
    _path = Path("data/narration_cooldowns.json")

    def should_narrate(self, location: str) -> bool: ...
    def record(self, location: str) -> None: ...
```

### 9. Scene Art (Re-enabled)

Fire-and-forget in `post_turn`. Caches by location UUID in KG. Posts via Transport.

### 10. StateUpdate — Warning Details

```python
class StateUpdate(BaseModel):
    location: str
    world_time: WorldTimeDisplay | None = None
    events: EventSummary | None = None
    active_quests: list[QuestSummary] | None = None
    subsystem_warnings: list[str] = []
    warning_details: dict[str, str] | None = None  # human-readable
```

### 11. UUID Everywhere

- `query_active_quests(player_uuid: str)` — takes UUID, uses edge traversal
- `TurnController` requires `location_uuid` at construction
- Entity refs from Graphiti resolved to UUIDs before passing to crews
- State update includes entity UUIDs for client-side matching

## LLM Call Budget

| Scenario | Current | New |
|----------|---------|-----|
| Simple action ("look around") | 5-8 calls | 2 (Graphiti + narration) |
| Action with world consequences | 5-8 calls | 2-3 (Graphiti + narration + world reaction KG writes) |
| Combat (resolved by NPC tools) | 5-8 calls | 2 (Graphiti + narration — combat handled inline by tools) |

Note: Combat, movement, and trade are resolved inline by NPC MCP tool calls during the round. The engine's LLM budget is only Graphiti extraction + narration. WorldReactionCrew creates KG entities but doesn't need LLM calls — it writes structured data from Graphiti's extraction.

## Files Affected

**New files (memento-mori):**
- `engine/src/memento/turn_controller.py` — main orchestrator
- `engine/src/memento/rpg_types.py` — Pydantic custom types
- `engine/src/memento/type_selector.py` — vector matching for type selection
- `engine/src/memento/world_reaction.py` — WorldReactionCrew orchestrator for entity creation from seeds
- `engine/src/memento/transport.py` — Transport protocol + MatrixTransport + NullTransport
- `engine/src/memento/lock_manager.py` — per-location locks
- `engine/src/memento/narration_cooldown.py` — persistent cooldown

**Modified files (memento-mori):**
- `engine/src/memento/matrix_listener.py` — use TurnController + LocationLockManager + MatrixTransport
- `engine/src/memento/models/state_update.py` — add `warning_details` field
- `engine/src/memento/round_controller.py` — deprecated (kept for reference during migration)
- `gateway/src/gateway/round_callback.py` — unchanged (still sends actions to Matrix; type selection happens in the engine)

**New/modified files (delve):**
- `src/infrastructure/dto/requests.py` — add `requested_types` to StackMessage
- `src/infrastructure/database/models/stack.py` — add `requested_types` field
- `src/core/services/stack_service.py` — merge requested types at process time
- `src/core/services/knowledge_graph/custom_types.py` — register RPG types (or new registry file)

**Tests:**
- New tests for TurnController, WorldReactionCrew, TypeSelector, LocationLockManager
- Update existing round_controller tests to use new interface
- Test NullTransport integration
- Test type selection vector matching

## Migration Path

1. Implement new components alongside existing `RoundController`
2. Feature flag in `EngineMatrixListener` to choose old vs new controller
3. Test in dev with flag on
4. Remove `RoundController` and flag once stable

## Open Decisions

- **Embedding model for TypeSelector:** Use the same model as the vector store (already available via VectorStoreService), or a lightweight local model?
- **Type registration mechanism:** Start with hardcoded dict in Delve. Evolve to config-driven (bonfire settings) if more consumers need custom types.
- **Immediate stack processing trigger:** Expose as a dedicated API endpoint, or reuse the existing `process_stack_task` with an on-demand queue push?
