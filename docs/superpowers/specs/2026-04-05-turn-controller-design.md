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
- Event detection replaced by Delve episode extraction with custom types
- Classification/detector/merge crews eliminated
- Context crew eliminated (episode summary replaces it)
- Plausibility check eliminated (KG entity resolution replaces it)
- New `CrewRouter` maps extracted types to crew callables
- NPC wait: fixed 15s sleep replaced by event-driven poll with early exit
- Narration cooldown: module-level dict replaced by persistent JSON file
- Transport protocol decouples Matrix from controller logic
- UUID everywhere (quest queries, entity refs, location lookups)
- Scene art re-enabled as fire-and-forget post-turn
- Subsystem warnings get human-readable detail strings

## Components

### 1. RPG Custom Types

Pydantic models registered with Delve's Graphiti as custom entity types. Graphiti's `add_episode` LLM extracts structured entities matching these models from room messages.

```python
# engine/src/memento/rpg_types.py

class CombatAction(BaseModel):
    """Extracted when player actions involve combat or violence."""
    attacker_name: str
    target_name: str
    weapon_or_method: str | None = None
    context: str = ""

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["CombatAction"]

class QuestInteraction(BaseModel):
    """Extracted when player interacts with quest-related content."""
    player_name: str
    npc_name: str | None = None
    action_type: str = ""      # accept, progress, complete, discover
    quest_hint: str = ""

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["QuestInteraction"]

class SocialInteraction(BaseModel):
    """Extracted when player engages in faction or reputation-affecting actions."""
    player_name: str
    faction_or_npc: str = ""
    sentiment: str = ""        # friendly, hostile, neutral
    action_summary: str = ""

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["SocialInteraction"]

class TradeAction(BaseModel):
    """Extracted when player buys, sells, or trades items."""
    player_name: str
    counterparty: str = ""
    items_given: list[str] = []
    items_received: list[str] = []

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["TradeAction"]

class MovementAction(BaseModel):
    """Extracted when player moves between locations."""
    player_name: str
    from_location: str | None = None
    to_location: str = ""

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["MovementAction"]
```

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

### 4. CrewRouter

Maps extracted Graphiti entity types to crew callables. Checks which custom type entities were extracted from the episode and fires corresponding crews with resolved UUIDs.

```python
# engine/src/memento/crew_router.py

@dataclass
class CrewRoute:
    type_name: str
    handler: Callable[[dict, TurnContext], dict]

class CrewRouter:
    def __init__(self):
        self.routes: list[CrewRoute] = [
            CrewRoute("CombatAction", self._handle_combat),
            CrewRoute("QuestInteraction", self._handle_quest),
            CrewRoute("SocialInteraction", self._handle_social),
            CrewRoute("TradeAction", self._handle_trade),
        ]

    def route(self, extracted_entities: list[dict], ctx: TurnContext) -> dict:
        """Run crews for all extracted entity types. Returns merged results."""
        results = {}
        extracted_types = {e.get("type") for e in extracted_entities}
        for route in self.routes:
            if route.type_name in extracted_types:
                entity = next(e for e in extracted_entities if e["type"] == route.type_name)
                resolved = self._resolve_uuids(entity)
                results[route.type_name] = route.handler(resolved, ctx)
        return results
```

Entity name-to-UUID resolution uses `kg.search()` scoped to the current location. If resolution fails (entity not at this location), the route is skipped — world state acts as the plausibility check.

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
        crew_router: CrewRouter,
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

        # 3. Route extracted types to crews
        crew_results = self.crew_router.route(
            episode.get("entities", []),
            self._build_turn_context(),
        )

        # 4. NPC wait (event-driven)
        self._await_npcs()

        # 5. Narrate
        narrative = self._narrate(episode, crew_results)

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
| Combat action | 5-8 calls | 3-4 (Graphiti + CombatFlow + narration) |
| Multi-event (combat + quest) | 7-10 calls | 4-5 (Graphiti + Combat + Quest + narration) |

## Files Affected

**New files (memento-mori):**
- `engine/src/memento/turn_controller.py` — main orchestrator
- `engine/src/memento/rpg_types.py` — Pydantic custom types
- `engine/src/memento/type_selector.py` — vector matching for type selection
- `engine/src/memento/crew_router.py` — type-to-crew routing
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
- New tests for TurnController, CrewRouter, TypeSelector, LocationLockManager
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
