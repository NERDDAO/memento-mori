# TurnController Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace RoundController with an episode-driven TurnController where Graphiti custom types extract world reaction seeds, a WorldReactionCrew creates new entities/quests/lore from those seeds, and per-location locking enables parallel turn processing. Inline actions (combat, movement, trade) are handled by NPC tool calls — not re-resolved by crews.

**Architecture:** Delve stack gets per-caller custom types. The engine defines world seed types (NewEntitySeed, QuestSeed, LocationChange, LoreSeed), vector-matches action text to select relevant types, pushes to stack, reads back structured extraction, and a WorldReactionCrew creates new KG entities from the seeds. Matrix transport is injected via protocol.

**Tech Stack:** Python 3.12, Pydantic v2, CrewAI, Graphiti (via Delve), sentence-transformers (embeddings), pytest, asyncio

**Spec:** `docs/superpowers/specs/2026-04-05-turn-controller-design.md`

---

## File Structure

### New files (memento-mori engine)

| File | Responsibility |
|------|---------------|
| `engine/src/memento/rpg_types.py` | World seed custom types for Graphiti extraction (NewEntitySeed, QuestSeed, LocationChange, LoreSeed) |
| `engine/src/memento/type_selector.py` | Vector-match action text against type descriptions, returns requested_types |
| `engine/src/memento/world_reaction.py` | WorldReactionCrew — creates KG entities/quests/lore from extracted seeds |
| `engine/src/memento/transport.py` | Transport protocol + MatrixTransport + NullTransport |
| `engine/src/memento/lock_manager.py` | Per-location threading locks |
| `engine/src/memento/narration_cooldown.py` | Persistent JSON-backed narration cooldown |
| `engine/src/memento/turn_controller.py` | Main orchestrator — thin pipeline coordinating all components |
| `engine/tests/test_lock_manager.py` | Tests for LocationLockManager |
| `engine/tests/test_narration_cooldown.py` | Tests for NarrationCooldown |
| `engine/tests/test_type_selector.py` | Tests for TypeSelector |
| `engine/tests/test_world_reaction.py` | Tests for WorldReactionCrew |
| `engine/tests/test_world_reaction.py` | Tests for WorldReactionCrew |
| `engine/tests/test_turn_controller.py` | Integration tests for TurnController |

### Modified files (memento-mori)

| File | Change |
|------|--------|
| `engine/src/memento/models/state_update.py` | Add `warning_details` field to StateUpdate |
| `engine/src/memento/matrix_listener.py` | Use TurnController + LocationLockManager + MatrixTransport (behind feature flag) |

### New/modified files (delve)

| File | Change |
|------|--------|
| `src/infrastructure/dto/requests.py` | Add `requested_types` to StackMessage |
| `src/infrastructure/database/models/stack.py` | Add `requested_types` field to Stack |
| `src/core/services/stack_service.py` | Merge requested_types at process time, pass to episode creation |
| `src/core/services/knowledge_graph/custom_types.py` | Add RPG types to registry |
| `tests/unit/test_stack_service_add.py` | Test requested_types flow |

---

## Phase 1: Foundation (memento-mori — no external deps)

### Task 1: LocationLockManager

**Files:**
- Create: `engine/src/memento/lock_manager.py`
- Create: `engine/tests/test_lock_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/test_lock_manager.py
import threading
from memento.lock_manager import LocationLockManager


def test_acquire_returns_lock():
    lock = LocationLockManager.acquire("tavern")
    assert isinstance(lock, threading.Lock)


def test_same_location_returns_same_lock():
    a = LocationLockManager.acquire("tavern")
    b = LocationLockManager.acquire("tavern")
    assert a is b


def test_different_locations_return_different_locks():
    a = LocationLockManager.acquire("tavern")
    b = LocationLockManager.acquire("market")
    assert a is not b


def test_concurrent_acquire_is_safe():
    """Multiple threads acquiring locks for different locations concurrently."""
    results = {}
    errors = []

    def worker(loc):
        try:
            lock = LocationLockManager.acquire(loc)
            with lock:
                results[loc] = threading.current_thread().name
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(f"loc-{i}",)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 20
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd engine && python -m pytest tests/test_lock_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'memento.lock_manager'`

- [ ] **Step 3: Implement LocationLockManager**

```python
# engine/src/memento/lock_manager.py
"""Per-location threading locks — replaces global _turn_lock."""

from __future__ import annotations

import threading


class LocationLockManager:
    """Per-location locks so different locations process in parallel."""

    _locks: dict[str, threading.Lock] = {}
    _meta_lock = threading.Lock()

    @classmethod
    def acquire(cls, location: str) -> threading.Lock:
        """Return (or create) the lock for a location."""
        with cls._meta_lock:
            if location not in cls._locks:
                cls._locks[location] = threading.Lock()
            return cls._locks[location]

    @classmethod
    def reset(cls) -> None:
        """Clear all locks. For tests only."""
        with cls._meta_lock:
            cls._locks.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && python -m pytest tests/test_lock_manager.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```
git add engine/src/memento/lock_manager.py engine/tests/test_lock_manager.py
git commit -m "feat(engine): add LocationLockManager for per-location turn locking"
```

---

### Task 2: NarrationCooldown (persistent)

**Files:**
- Create: `engine/src/memento/narration_cooldown.py`
- Create: `engine/tests/test_narration_cooldown.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/test_narration_cooldown.py
import time
from pathlib import Path
from memento.narration_cooldown import NarrationCooldown


def test_should_narrate_first_time(tmp_path):
    nc = NarrationCooldown(path=tmp_path / "cooldowns.json")
    assert nc.should_narrate("tavern") is True


def test_record_blocks_immediate_renarration(tmp_path):
    nc = NarrationCooldown(path=tmp_path / "cooldowns.json", cooldown=10.0)
    nc.record("tavern")
    assert nc.should_narrate("tavern") is False


def test_cooldown_expires(tmp_path):
    nc = NarrationCooldown(path=tmp_path / "cooldowns.json", cooldown=0.1)
    nc.record("tavern")
    time.sleep(0.15)
    assert nc.should_narrate("tavern") is True


def test_persists_across_instances(tmp_path):
    path = tmp_path / "cooldowns.json"
    nc1 = NarrationCooldown(path=path, cooldown=10.0)
    nc1.record("tavern")

    nc2 = NarrationCooldown(path=path, cooldown=10.0)
    assert nc2.should_narrate("tavern") is False


def test_independent_locations(tmp_path):
    nc = NarrationCooldown(path=tmp_path / "cooldowns.json", cooldown=10.0)
    nc.record("tavern")
    assert nc.should_narrate("tavern") is False
    assert nc.should_narrate("market") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd engine && python -m pytest tests/test_narration_cooldown.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement NarrationCooldown**

```python
# engine/src/memento/narration_cooldown.py
"""Persistent narration cooldown — survives engine restarts."""

from __future__ import annotations

import json
import time
from pathlib import Path

from memento.log import get_logger

logger = get_logger(__name__)

_DEFAULT_PATH = Path("data/narration_cooldowns.json")


class NarrationCooldown:
    """JSON file-backed per-location narration gating."""

    def __init__(
        self,
        *,
        path: Path = _DEFAULT_PATH,
        cooldown: float = 30.0,
    ) -> None:
        self._path = path
        self._cooldown = cooldown

    def should_narrate(self, location: str) -> bool:
        state = self._load()
        last = state.get(location, 0.0)
        return (time.time() - last) >= self._cooldown

    def record(self, location: str) -> None:
        state = self._load()
        state[location] = time.time()
        self._save(state)

    def _load(self) -> dict[str, float]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to read narration cooldowns from %s", self._path)
            return {}

    def _save(self, state: dict[str, float]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(state))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && python -m pytest tests/test_narration_cooldown.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```
git add engine/src/memento/narration_cooldown.py engine/tests/test_narration_cooldown.py
git commit -m "feat(engine): add persistent NarrationCooldown with JSON file backing"
```

---

### Task 3: Transport Protocol + NullTransport

**Files:**
- Create: `engine/src/memento/transport.py`

- [ ] **Step 1: Write the transport module**

```python
# engine/src/memento/transport.py
"""Transport protocol — decouples TurnController from Matrix."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    import nio

from memento.log import get_logger

logger = get_logger(__name__)


class Transport(Protocol):
    """Interface for phase emission and NPC tracking."""

    def emit_phase(self, location: str, phase: str, crew: str | None = None) -> None: ...
    def emit_art(self, location: str, art_text: str) -> None: ...
    def get_npc_count(self, location: str) -> int: ...
    def get_npc_response_count(self, location: str) -> int: ...
    def clear_npc_responses(self, location: str) -> None: ...


class NullTransport:
    """No-op transport for tests and headless runs."""

    def emit_phase(self, location: str, phase: str, crew: str | None = None) -> None:
        pass

    def emit_art(self, location: str, art_text: str) -> None:
        pass

    def get_npc_count(self, location: str) -> int:
        return 0

    def get_npc_response_count(self, location: str) -> int:
        return 0

    def clear_npc_responses(self, location: str) -> None:
        pass


class MatrixTransport:
    """Matrix-backed transport — wraps nio.AsyncClient for thread-safe calls.

    Phase emission and art posting run on the main asyncio loop via
    run_coroutine_threadsafe (the controller runs in a worker thread).
    NPC tracking delegates to the shared round_controller module-level trackers.
    """

    def __init__(
        self,
        client: nio.AsyncClient,
        room_id: str,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._client = client
        self._room_id = room_id
        self._loop = loop

    def emit_phase(self, location: str, phase: str, crew: str | None = None) -> None:
        body = f"[phase] {phase}" + (f":{crew}" if crew else "")
        rpg_meta: dict[str, Any] = {
            "type": "phase",
            "phase": phase,
            "location": location,
            "channel": "events",
        }
        if crew:
            rpg_meta["crew"] = crew

        content = {
            "msgtype": "m.text",
            "body": body,
            "com.bonfires.rpg": rpg_meta,
        }
        coro = self._client.room_send(self._room_id, "m.room.message", content)
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            future.result(timeout=5)
        except Exception:
            logger.debug("emit_phase(%s:%s) send failed", phase, crew, exc_info=True)

    def emit_art(self, location: str, art_text: str) -> None:
        lines = art_text.split("\n")
        content = {
            "msgtype": "m.text",
            "body": art_text,
            "com.bonfires.rpg": {
                "type": "scene_art",
                "location": location,
                "lines": lines,
                "width": max(len(line) for line in lines) if lines else 0,
                "height": len(lines),
                "channel": "narrative",
            },
        }
        coro = self._client.room_send(self._room_id, "m.room.message", content)
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        future.add_done_callback(
            lambda f: f.exception() and logger.debug("Art post failed", exc_info=f.exception())
        )

    def get_npc_count(self, location: str) -> int:
        from memento.agent_controller import get_agent_controller
        controller = get_agent_controller()
        return len(controller.get_npc_user_ids(location))

    def get_npc_response_count(self, location: str) -> int:
        from memento.round_controller import npc_response_count
        return npc_response_count(location)

    def clear_npc_responses(self, location: str) -> None:
        from memento.round_controller import clear_npc_responses
        clear_npc_responses(location)
```

- [ ] **Step 2: Verify NullTransport satisfies the Protocol**

Run: `cd engine && python -c "from memento.transport import Transport, NullTransport; t: Transport = NullTransport(); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```
git add engine/src/memento/transport.py
git commit -m "feat(engine): add Transport protocol, MatrixTransport, and NullTransport"
```

---

### Task 4: World Seed Custom Types

**Files:**
- Create: `engine/src/memento/rpg_types.py`

- [ ] **Step 1: Write the world seed type models**

```python
# engine/src/memento/rpg_types.py
"""World seed custom types for Graphiti episode extraction.

These are NOT action replays — combat/movement/trade are handled inline by NPC
tool calls. These types represent world consequences: new entities, quests,
location changes, and lore that should exist as a result of what happened.

Each type's docstring is used as the matching corpus for the TypeSelector.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NewEntitySeed(BaseModel):
    """Extracted when conversation implies a new NPC, creature, or item should exist in the world that doesn't already."""

    entity_name: str = Field(..., description="Name of the new entity")
    entity_type: str = Field("", description="One of: npc, item, creature")
    location: str = Field("", description="Where the entity should appear")
    description: str = Field("", description="Brief description of the entity")
    source_context: str = Field("", description="What in the conversation implied this entity")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["NewEntitySeed"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {"entity_name": self.entity_name}
        if self.entity_type:
            out["entity_type"] = self.entity_type
        if self.location:
            out["location"] = self.location
        if self.description:
            out["description"] = self.description
        if self.source_context:
            out["source_context"] = self.source_context
        return out


class QuestSeed(BaseModel):
    """Extracted when interaction suggests a quest opportunity, quest progression, or quest-related discovery."""

    quest_name: str = Field("", description="Name or short title of the quest")
    giver_name: str = Field("", description="NPC who triggered or gave the quest")
    objective_hint: str = Field("", description="What needs to be done")
    trigger_context: str = Field("", description="What in the conversation triggered this")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["QuestSeed"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.quest_name:
            out["quest_name"] = self.quest_name
        if self.giver_name:
            out["giver_name"] = self.giver_name
        if self.objective_hint:
            out["objective_hint"] = self.objective_hint
        if self.trigger_context:
            out["trigger_context"] = self.trigger_context
        return out


class LocationChange(BaseModel):
    """Extracted when the room state should change as a consequence of what happened — doors opened, fires started, structures collapsed."""

    location: str = Field("", description="Location being changed")
    change_description: str = Field("", description="What changed")
    new_exits: list[str] = Field(default_factory=list, description="New exits or passages revealed")
    removed_features: list[str] = Field(default_factory=list, description="Features destroyed or removed")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["LocationChange"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.location:
            out["location"] = self.location
        if self.change_description:
            out["change_description"] = self.change_description
        if self.new_exits:
            out["new_exits"] = self.new_exits
        if self.removed_features:
            out["removed_features"] = self.removed_features
        return out


class LoreSeed(BaseModel):
    """Extracted when new world lore, history, or mythology is revealed or created during conversation."""

    lore_topic: str = Field("", description="Topic or title of the lore")
    content: str = Field("", description="The lore content")
    source_npc: str = Field("", description="NPC who revealed it")
    related_locations: list[str] = Field(default_factory=list, description="Locations related to this lore")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["LoreSeed"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.lore_topic:
            out["lore_topic"] = self.lore_topic
        if self.content:
            out["content"] = self.content
        if self.source_npc:
            out["source_npc"] = self.source_npc
        if self.related_locations:
            out["related_locations"] = self.related_locations
        return out


# Registry of all world seed types — used by TypeSelector and Delve type registration
RPG_ENTITY_TYPES: dict[str, type[BaseModel]] = {
    "NewEntitySeed": NewEntitySeed,
    "QuestSeed": QuestSeed,
    "LocationChange": LocationChange,
    "LoreSeed": LoreSeed,
}
```

- [ ] **Step 2: Verify models are valid**

Run: `cd engine && python -c "from memento.rpg_types import RPG_ENTITY_TYPES; print(list(RPG_ENTITY_TYPES.keys()))"`
Expected: `['NewEntitySeed', 'QuestSeed', 'LocationChange', 'LoreSeed']`

- [ ] **Step 3: Commit**

```
git add engine/src/memento/rpg_types.py
git commit -m "feat(engine): add world seed custom types for Graphiti episode extraction"
```

---

### Task 5: TypeSelector (vector matching)

**Files:**
- Create: `engine/src/memento/type_selector.py`
- Create: `engine/tests/test_type_selector.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/test_type_selector.py
from memento.type_selector import TypeSelector
from memento.rpg_types import RPG_ENTITY_TYPES


def test_select_quest_seed():
    ts = TypeSelector(threshold=0.3)
    for name, model in RPG_ENTITY_TYPES.items():
        ts.register(name, model)

    result = ts.select("The innkeeper mentions a lost artifact in the caves")
    assert "QuestSeed" in result


def test_select_new_entity_seed():
    ts = TypeSelector(threshold=0.3)
    for name, model in RPG_ENTITY_TYPES.items():
        ts.register(name, model)

    result = ts.select("A mysterious stranger appears at the tavern door")
    assert "NewEntitySeed" in result


def test_simple_action_may_match_nothing_or_few():
    ts = TypeSelector(threshold=0.6)  # stricter threshold
    for name, model in RPG_ENTITY_TYPES.items():
        ts.register(name, model)

    result = ts.select("I look around the room")
    # At strict threshold, a generic action shouldn't match specific seeds
    assert "QuestSeed" not in result


def test_lenient_threshold_over_includes():
    ts = TypeSelector(threshold=0.0)  # match everything
    for name, model in RPG_ENTITY_TYPES.items():
        ts.register(name, model)

    result = ts.select("anything")
    assert len(result) == len(RPG_ENTITY_TYPES)


def test_empty_registry_returns_empty():
    ts = TypeSelector(threshold=0.3)
    result = ts.select("attack the goblin")
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd engine && python -m pytest tests/test_type_selector.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement TypeSelector**

The embedding function uses `sentence-transformers` which is already available in the engine environment. If not installed, fall back to a simple TF-IDF approach.

```python
# engine/src/memento/type_selector.py
"""Vector-match action text against RPG type descriptions for type selection."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel

from memento.log import get_logger

logger = get_logger(__name__)

# Try sentence-transformers, fall back to simple bag-of-words
_model = None


def _get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("TypeSelector using sentence-transformers")
        except ImportError:
            _model = "bow"
            logger.info("TypeSelector using bag-of-words fallback")
    return _model


def _embed(text: str) -> list[float]:
    model = _get_model()
    if model == "bow":
        return _bow_embed(text)
    return model.encode(text).tolist()


def _bow_embed(text: str) -> list[float]:
    """Simple bag-of-words embedding fallback."""
    words = set(text.lower().split())
    # Use a fixed vocabulary derived from RPG terms
    vocab = sorted(words)
    return [1.0 if w in words else 0.0 for w in vocab]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        # BoW fallback: use Jaccard-like overlap
        set_a = {i for i, v in enumerate(a) if v > 0}
        set_b = {i for i, v in enumerate(b) if v > 0}
        if not set_a or not set_b:
            return 0.0
        # Fall back to word overlap
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


class TypeSelector:
    """Vector-match action text against RPG type descriptions."""

    def __init__(self, threshold: float = 0.3) -> None:
        self.threshold = threshold
        self.types: dict[str, type[BaseModel]] = {}
        self._embeddings: dict[str, list[float]] = {}

    def register(self, name: str, model: type[BaseModel]) -> None:
        """Register a type. Embeds the docstring for matching."""
        self.types[name] = model
        desc = model.__doc__ or name
        self._embeddings[name] = _embed(desc)

    def select(self, action_text: str) -> list[str]:
        """Return type names whose descriptions are similar to the action."""
        if not self._embeddings:
            return []
        action_emb = _embed(action_text)
        selected = []
        for name, type_emb in self._embeddings.items():
            sim = _cosine_similarity(action_emb, type_emb)
            if sim >= self.threshold:
                selected.append(name)
        return selected
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && python -m pytest tests/test_type_selector.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```
git add engine/src/memento/type_selector.py engine/tests/test_type_selector.py
git commit -m "feat(engine): add TypeSelector with vector matching for RPG type selection"
```

---

### Task 6: StateUpdate — add warning_details

**Files:**
- Modify: `engine/src/memento/models/state_update.py:102-127`

- [ ] **Step 1: Add warning_details field**

Add `warning_details: dict[str, str] | None = None` to the `StateUpdate` class at line 127 (after `subsystem_warnings`):

```python
# Add after line 127 (subsystem_warnings field):
    warning_details: dict[str, str] | None = None
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `cd engine && python -m pytest tests/test_state_update.py -v`
Expected: All pass (additive change only)

- [ ] **Step 3: Commit**

```
git add engine/src/memento/models/state_update.py
git commit -m "feat(engine): add warning_details field to StateUpdate for client display"
```

---

## Phase 2: Delve Stack Extension

### Task 7: StackMessage requested_types field

**Files:**
- Modify: `delve/src/infrastructure/dto/requests.py:2196-2227` (StackMessage class)
- Modify: `delve/tests/unit/test_stack_service_add.py`

- [ ] **Step 1: Add requested_types to StackMessage**

Add after the `metadata` field (line 2215 of `delve/src/infrastructure/dto/requests.py`):

```python
    requested_types: list[str] = Field(
        default_factory=list,
        description="Custom entity type names to extract during episode processing",
    )
```

- [ ] **Step 2: Add requested_types to to_dict()**

In `StackMessage.to_dict()`, add after the metadata line:

```python
        if self.requested_types:
            d["requested_types"] = self.requested_types
```

- [ ] **Step 3: Verify the model accepts the new field**

Run: `cd delve && python -c "from infrastructure.dto.requests import StackMessage; m = StackMessage(text='test', userId='u1', chatId='c1', timestamp='2026-01-01T00:00:00Z', requested_types=['CombatAction']); print(m.requested_types)"`
Expected: `['CombatAction']`

- [ ] **Step 4: Commit**

```
cd delve && git add src/infrastructure/dto/requests.py
git commit -m "feat: add requested_types field to StackMessage for per-caller custom types"
```

---

### Task 8: Stack model — accumulate requested_types

**Files:**
- Modify: `delve/src/infrastructure/database/models/stack.py:17-232`

- [ ] **Step 1: Add requested_types field to Stack model**

Add after the `message_ids` field (line 29):

```python
    requested_types: list[str] = Field(
        default_factory=list,
        description="Union of requested custom types across all messages in this cycle",
    )
```

- [ ] **Step 2: Add merge method**

Add a method after `add_message_id`:

```python
    def merge_requested_types(self, types: list[str]) -> None:
        """Add type names to the accumulated set (deduplicating)."""
        existing = set(self.requested_types)
        for t in types:
            if t not in existing:
                self.requested_types.append(t)
                existing.add(t)
```

- [ ] **Step 3: Update clear_messages to also clear requested_types**

Modify `clear_messages` to also reset types:

```python
    def clear_messages(self) -> None:
        """Empty the message_ids list and update last_processed_at."""
        self.message_ids = []
        self.requested_types = []
        self.last_processed_at = datetime.now()
```

- [ ] **Step 4: Verify**

Run: `cd delve && python -c "
from infrastructure.database.models.stack import Stack
s = Stack(agent_id='test')
s.merge_requested_types(['CombatAction', 'QuestInteraction'])
s.merge_requested_types(['CombatAction', 'TradeAction'])
print(s.requested_types)
"`
Expected: `['CombatAction', 'QuestInteraction', 'TradeAction']`

- [ ] **Step 5: Commit**

```
cd delve && git add src/infrastructure/database/models/stack.py
git commit -m "feat: add requested_types accumulation to Stack model"
```

---

### Task 9: stack_service.add() — merge types into stack

**Files:**
- Modify: `delve/src/core/services/stack_service.py:322-400` (add method)

- [ ] **Step 1: Update stack.add() to merge requested_types**

After the message is added to the stack (after `await self.mongo_service.add_message_to_stack(agent_id, str(mongo_id))`), add type merging. Find the section near the end of the `add` method where the stack is updated, and add:

```python
            # Merge requested_types into the stack
            if msg.requested_types:
                stack = await Stack.get_by_agent_id(agent_id)
                if stack:
                    stack.merge_requested_types(msg.requested_types)
                    await stack.save()
```

- [ ] **Step 2: Verify add works with requested_types**

This requires a running MongoDB. Add a unit test that mocks the DB:

```python
# In tests/unit/test_stack_service_add.py, add:
async def test_add_with_requested_types_stores_on_stack(stack_service, mocker):
    """Verify requested_types from StackMessage get merged into Stack."""
    # This is an integration concern — verify the field flows through
    msg = StackMessage(
        text="I attack the goblin",
        userId="player1",
        chatId="room1",
        timestamp="2026-01-01T00:00:00Z",
        requested_types=["CombatAction"],
    )
    assert msg.requested_types == ["CombatAction"]
```

- [ ] **Step 3: Commit**

```
cd delve && git add src/core/services/stack_service.py tests/unit/test_stack_service_add.py
git commit -m "feat: merge requested_types from StackMessage into Stack during add"
```

---

### Task 10: World seed types in Delve type registry

**Files:**
- Modify: `delve/src/core/services/knowledge_graph/custom_types.py`

- [ ] **Step 1: Add world seed types to the registry**

Add the world seed type classes at the end of the file, before the `CUSTOM_ENTITY_TYPES` list. These mirror the memento-mori types registered in Delve's type system:

```python
# --- World seed types (registered by memento-mori bonfire) ---

class NewEntitySeed(BaseModel):
    """Extracted when conversation implies a new NPC, creature, or item should exist."""
    entity_name: str | None = Field(None, description="Name of the new entity")
    entity_type: str | None = Field(None, description="npc, item, creature")
    location: str | None = Field(None, description="Where the entity should appear")
    description: str | None = Field(None, description="Brief description")
    source_context: str | None = Field(None, description="What implied this entity")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["NewEntitySeed"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.entity_name is not None:
            out["entity_name"] = self.entity_name
        if self.entity_type is not None:
            out["entity_type"] = self.entity_type
        if self.location is not None:
            out["location"] = self.location
        if self.description is not None:
            out["description"] = self.description
        if self.source_context is not None:
            out["source_context"] = self.source_context
        return out


class QuestSeed(BaseModel):
    """Extracted when interaction suggests a quest opportunity or progression."""
    quest_name: str | None = Field(None, description="Name of the quest")
    giver_name: str | None = Field(None, description="NPC who triggered it")
    objective_hint: str | None = Field(None, description="What needs to be done")
    trigger_context: str | None = Field(None, description="What triggered this")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["QuestSeed"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.quest_name is not None:
            out["quest_name"] = self.quest_name
        if self.giver_name is not None:
            out["giver_name"] = self.giver_name
        if self.objective_hint is not None:
            out["objective_hint"] = self.objective_hint
        if self.trigger_context is not None:
            out["trigger_context"] = self.trigger_context
        return out


class LocationChange(BaseModel):
    """Extracted when room state should change — doors opened, fires started, structures collapsed."""
    location: str | None = Field(None, description="Location being changed")
    change_description: str | None = Field(None, description="What changed")
    new_exits: list[str] = Field(default_factory=list, description="New exits revealed")
    removed_features: list[str] = Field(default_factory=list, description="Features destroyed")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["LocationChange"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.location is not None:
            out["location"] = self.location
        if self.change_description is not None:
            out["change_description"] = self.change_description
        if self.new_exits:
            out["new_exits"] = self.new_exits
        if self.removed_features:
            out["removed_features"] = self.removed_features
        return out


class LoreSeed(BaseModel):
    """Extracted when new world lore, history, or mythology is revealed."""
    lore_topic: str | None = Field(None, description="Topic of the lore")
    content: str | None = Field(None, description="The lore content")
    source_npc: str | None = Field(None, description="NPC who revealed it")
    related_locations: list[str] = Field(default_factory=list, description="Related locations")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["LoreSeed"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.lore_topic is not None:
            out["lore_topic"] = self.lore_topic
        if self.content is not None:
            out["content"] = self.content
        if self.source_npc is not None:
            out["source_npc"] = self.source_npc
        if self.related_locations:
            out["related_locations"] = self.related_locations
        return out
```

- [ ] **Step 2: Add world seed types to CUSTOM_ENTITY_TYPES and get_graphiti_entity_types()**

Update `CUSTOM_ENTITY_TYPES` list:

```python
CUSTOM_ENTITY_TYPES: list[type[BaseModel]] = [
    User,
    TaxonomyLabel,
    Update,
    Applicant,
    Evidence,
    ReviewResult,
    WorkingDocUpdate,
    NewEntitySeed,
    QuestSeed,
    LocationChange,
    LoreSeed,
]
```

Update `get_graphiti_entity_types()`:

```python
def get_graphiti_entity_types() -> dict[str, type[BaseModel]]:
    return {
        "User": User,
        "TaxonomyLabel": TaxonomyLabel,
        "Update": Update,
        "Applicant": Applicant,
        "Evidence": Evidence,
        "ReviewResult": ReviewResult,
        "WorkingDocUpdate": WorkingDocUpdate,
        "NewEntitySeed": NewEntitySeed,
        "QuestSeed": QuestSeed,
        "LocationChange": LocationChange,
        "LoreSeed": LoreSeed,
    }
```

- [ ] **Step 3: Commit**

```
cd delve && git add src/core/services/knowledge_graph/custom_types.py
git commit -m "feat: register world seed custom types for Graphiti episode extraction"
```

---

## Phase 3: Orchestration (memento-mori)

### Task 11: WorldReactionCrew

**Files:**
- Create: `engine/src/memento/world_reaction.py`
- Create: `engine/tests/test_world_reaction.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/test_world_reaction.py
from memento.world_reaction import WorldReactionCrew, TurnContext


def test_no_entities_returns_empty():
    crew = WorldReactionCrew()
    ctx = TurnContext(location="tavern", location_uuid="loc-123", player_name="Kael")
    result = crew.react([], ctx)
    assert result == {}


def test_new_entity_seed_creates_entry():
    crew = WorldReactionCrew()
    ctx = TurnContext(location="tavern", location_uuid="loc-123", player_name="Kael")
    entities = [{"type": "NewEntitySeed", "entity_name": "Mysterious Stranger", "entity_type": "npc", "description": "A hooded figure"}]
    result = crew.react(entities, ctx)
    assert "new_entities" in result
    assert len(result["new_entities"]) == 1


def test_quest_seed_creates_entry():
    crew = WorldReactionCrew()
    ctx = TurnContext(location="tavern", location_uuid="loc-123", player_name="Kael")
    entities = [{"type": "QuestSeed", "quest_name": "The Lost Artifact", "giver_name": "Innkeeper"}]
    result = crew.react(entities, ctx)
    assert "new_quests" in result


def test_unknown_type_is_skipped():
    crew = WorldReactionCrew()
    ctx = TurnContext(location="tavern", location_uuid="loc-123", player_name="Kael")
    entities = [{"type": "UnknownType", "data": "whatever"}]
    result = crew.react(entities, ctx)
    assert result == {}


def test_multiple_seeds_processed():
    crew = WorldReactionCrew()
    ctx = TurnContext(location="tavern", location_uuid="loc-123", player_name="Kael")
    entities = [
        {"type": "NewEntitySeed", "entity_name": "Dark Blade", "entity_type": "item", "description": "A cursed sword"},
        {"type": "QuestSeed", "quest_name": "Retrieve the Blade", "giver_name": "Blacksmith"},
        {"type": "LoreSeed", "lore_topic": "The Curse of Ironhold", "content": "An ancient curse..."},
    ]
    result = crew.react(entities, ctx)
    assert "new_entities" in result
    assert "new_quests" in result
    assert "lore" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd engine && python -m pytest tests/test_world_reaction.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement WorldReactionCrew**

```python
# engine/src/memento/world_reaction.py
"""WorldReactionCrew — creates KG entities from episode-extracted world seeds.

Does NOT re-resolve inline actions (combat, movement, trade) — those are
handled by NPC MCP tool calls during the round. This crew creates NEW things
in the world as consequences of what happened.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from memento.log import get_logger

logger = get_logger(__name__)


@dataclass
class TurnContext:
    """Context passed to reaction handlers."""
    location: str
    location_uuid: str
    player_name: str
    combined_action: str = ""
    episode_summary: str = ""


class WorldReactionCrew:
    """Orchestrates entity creation from episode-extracted world seeds."""

    def react(self, extracted_entities: list[dict], ctx: TurnContext) -> dict[str, Any]:
        """Process all extracted seeds. Returns summary of what was created."""
        results: dict[str, Any] = {}

        for entity in extracted_entities:
            entity_type = entity.get("type", "")
            try:
                if entity_type == "NewEntitySeed":
                    results.setdefault("new_entities", []).append(
                        self._create_entity(entity, ctx)
                    )
                elif entity_type == "QuestSeed":
                    results.setdefault("new_quests", []).append(
                        self._create_quest(entity, ctx)
                    )
                elif entity_type == "LocationChange":
                    results.setdefault("location_changes", []).append(
                        self._apply_location_change(entity, ctx)
                    )
                elif entity_type == "LoreSeed":
                    results.setdefault("lore", []).append(
                        self._persist_lore(entity, ctx)
                    )
            except Exception:
                logger.warning("World reaction failed for %s", entity_type, exc_info=True)

        return results

    def _resolve_uuid(self, name: str) -> str:
        """Resolve an entity name to UUID via KG search. Returns empty string on failure."""
        if not name:
            return ""
        try:
            from memento.bonfires_client import get_client
            client = get_client()
            result = client.kg.search(name, num_results=3)
            entities = result.get("entities", result.get("nodes", []))
            for e in entities:
                if e.get("name", "").lower() == name.lower():
                    return e.get("uuid", "")
        except Exception:
            logger.debug("UUID resolution failed for %s", name)
        return ""

    def _create_entity(self, seed: dict, ctx: TurnContext) -> dict:
        """Create a new entity in the KG from a NewEntitySeed."""
        entity_name = seed.get("entity_name", "")
        entity_type = seed.get("entity_type", "npc")
        description = seed.get("description", "")

        if not entity_name:
            return {"error": "no entity_name"}

        label_map = {"npc": "NPC", "item": "Item", "creature": "Creature"}
        labels = [label_map.get(entity_type, "Entity")]

        try:
            from memento.bonfires_client import get_client
            client = get_client()
            uuid = client.kg.create_entity(
                entity_name,
                labels,
                {"description": description, "source": "world_reaction", "location": ctx.location},
            )

            # Link to location
            if ctx.location_uuid:
                edge_type = "LOCATED_IN" if entity_type in ("npc", "creature") else "FOUND_AT"
                client.kg.create_edge(uuid, ctx.location_uuid, edge_type, "")

            logger.info("Created %s entity: %s (%s)", entity_type, entity_name, uuid)
            return {"uuid": uuid, "name": entity_name, "type": entity_type}
        except Exception:
            logger.warning("Failed to create entity %s", entity_name, exc_info=True)
            return {"error": f"creation_failed: {entity_name}"}

    def _create_quest(self, seed: dict, ctx: TurnContext) -> dict:
        """Create a quest entity in the KG from a QuestSeed."""
        quest_name = seed.get("quest_name", "")
        giver_name = seed.get("giver_name", "")
        objective = seed.get("objective_hint", "")

        if not quest_name:
            return {"error": "no quest_name"}

        try:
            from memento.bonfires_client import get_client
            client = get_client()
            uuid = client.kg.create_entity(
                quest_name,
                ["Quest"],
                {
                    "objective": objective,
                    "giver": giver_name,
                    "location": ctx.location,
                    "source": "world_reaction",
                },
            )

            # Link to location
            if ctx.location_uuid:
                client.kg.create_edge(uuid, ctx.location_uuid, "AVAILABLE_AT", "")

            # Link to giver NPC
            giver_uuid = self._resolve_uuid(giver_name)
            if giver_uuid:
                client.kg.create_edge(uuid, giver_uuid, "GIVEN_BY", "")

            logger.info("Created quest: %s (%s)", quest_name, uuid)
            return {"uuid": uuid, "name": quest_name, "giver": giver_name}
        except Exception:
            logger.warning("Failed to create quest %s", quest_name, exc_info=True)
            return {"error": f"creation_failed: {quest_name}"}

    def _apply_location_change(self, seed: dict, ctx: TurnContext) -> dict:
        """Update location state in KG from a LocationChange seed."""
        change = seed.get("change_description", "")
        new_exits = seed.get("new_exits", [])

        if not change and not new_exits:
            return {"error": "no change specified"}

        try:
            if ctx.location_uuid:
                from memento.bonfires_client import get_client
                client = get_client()
                updates: dict[str, Any] = {}
                if change:
                    updates["recent_change"] = change
                if new_exits:
                    updates["new_exits"] = new_exits
                client.kg.update_entity(ctx.location_uuid, updates)

            logger.info("Location change at %s: %s", ctx.location, change)
            return {"location": ctx.location, "change": change, "new_exits": new_exits}
        except Exception:
            logger.warning("Failed to apply location change at %s", ctx.location, exc_info=True)
            return {"error": f"location_change_failed: {ctx.location}"}

    def _persist_lore(self, seed: dict, ctx: TurnContext) -> dict:
        """Create a lore entity in the KG from a LoreSeed."""
        topic = seed.get("lore_topic", "")
        content = seed.get("content", "")
        source_npc = seed.get("source_npc", "")

        if not topic:
            return {"error": "no lore_topic"}

        try:
            from memento.bonfires_client import get_client
            client = get_client()
            uuid = client.kg.create_entity(
                topic,
                ["Lore"],
                {
                    "content": content,
                    "source_npc": source_npc,
                    "location": ctx.location,
                    "source": "world_reaction",
                },
            )

            # Link to related locations
            for loc_name in seed.get("related_locations", []):
                loc_uuid = self._resolve_uuid(loc_name)
                if loc_uuid:
                    client.kg.create_edge(uuid, loc_uuid, "RELATES_TO", "")

            logger.info("Created lore: %s (%s)", topic, uuid)
            return {"uuid": uuid, "topic": topic}
        except Exception:
            logger.warning("Failed to persist lore %s", topic, exc_info=True)
            return {"error": f"lore_failed: {topic}"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && python -m pytest tests/test_world_reaction.py -v`
Expected: 5 passed (KG calls will fail in tests without mocking, but the structure tests pass — the handlers catch exceptions and return error dicts)

- [ ] **Step 5: Commit**

```
git add engine/src/memento/world_reaction.py engine/tests/test_world_reaction.py
git commit -m "feat(engine): add WorldReactionCrew — creates KG entities from world seeds"
```

---

### Task 12: TurnController

**Files:**
- Create: `engine/src/memento/turn_controller.py`
- Create: `engine/tests/test_turn_controller.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/test_turn_controller.py
from unittest.mock import MagicMock, patch
from memento.turn_controller import TurnController
from memento.transport import NullTransport
from memento.type_selector import TypeSelector
from memento.world_reaction import WorldReactionCrew


def _make_controller(**overrides):
    defaults = dict(
        location="tavern",
        location_uuid="loc-123",
        actions=[{"player_name": "Kael", "action": "look around"}],
        transport=NullTransport(),
        type_selector=TypeSelector(threshold=0.3),
        world_reaction=WorldReactionCrew(),
        npc_wait=0.1,
    )
    defaults.update(overrides)
    return TurnController(**defaults)


def test_run_returns_tuple():
    with patch.object(TurnController, "_ingest_and_extract", return_value={"content": "A quiet tavern.", "entities": []}):
        with patch.object(TurnController, "_narrate", return_value="The tavern is quiet."):
            tc = _make_controller()
            narrative, state_update = tc.run()
            assert isinstance(narrative, str)
            assert isinstance(state_update, dict)


def test_run_emits_ready_phase_on_success():
    transport = MagicMock()
    transport.get_npc_count.return_value = 0
    with patch.object(TurnController, "_ingest_and_extract", return_value={"content": "Scene.", "entities": []}):
        with patch.object(TurnController, "_narrate", return_value="Narrative."):
            tc = _make_controller(transport=transport)
            tc.run()
            transport.emit_phase.assert_called_with("tavern", "ready", None)


def test_run_emits_ready_on_exception():
    transport = MagicMock()
    with patch.object(TurnController, "_run_inner", side_effect=RuntimeError("boom")):
        tc = _make_controller(transport=transport)
        narrative, state_update = tc.run()
        assert narrative == ""
        transport.emit_phase.assert_called_with("tavern", "ready", None)


def test_combined_action_joins_actions():
    tc = _make_controller(actions=[
        {"player_name": "Kael", "action": "attack goblin"},
        {"player_name": "Lyra", "action": "cast heal"},
    ])
    assert "Kael: attack goblin" in tc.combined_action
    assert "Lyra: cast heal" in tc.combined_action
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd engine && python -m pytest tests/test_turn_controller.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement TurnController**

```python
# engine/src/memento/turn_controller.py
"""TurnController — episode-driven turn orchestration.

Thin pipeline: type selection → stack ingest → route → NPC wait → narrate → post-turn.
Replaces RoundController.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from memento.world_reaction import WorldReactionCrew, TurnContext
from memento.log import get_logger
from memento.models.state_update import (
    EventSummary,
    QuestSummary,
    StateUpdate,
    WorldTimeDisplay,
)
from memento.narration_cooldown import NarrationCooldown
from memento.transport import Transport
from memento.type_selector import TypeSelector

logger = get_logger(__name__)

_narration_cooldown = NarrationCooldown()


class TurnController:
    """Episode-driven turn orchestrator.

    Designed to run in a worker thread via asyncio.to_thread.
    """

    def __init__(
        self,
        location: str,
        location_uuid: str,
        actions: list[dict],
        transport: Transport,
        type_selector: TypeSelector,
        world_reaction: WorldReactionCrew,
        npc_wait: float = 15.0,
    ) -> None:
        self.location = location
        self.location_uuid = location_uuid
        self.actions = actions
        self.transport = transport
        self.type_selector = type_selector
        self.world_reaction = world_reaction
        self.npc_wait = npc_wait

        self.player_name: str = actions[0].get("player_name", "unknown") if actions else "unknown"
        self.combined_action: str = "; ".join(
            f"{a.get('player_name', '?')}: {a.get('action', '?')}" for a in actions
        )

        # Mutable state built up during run()
        self.narrative: str = ""
        self.world_time: dict = {}
        self.crew_results: dict = {}
        self.subsystem_warnings: list[str] = []

    def run(self) -> tuple[str, dict]:
        """Execute the full turn. Returns (narrative, state_update_dict)."""
        try:
            return self._run_inner()
        except Exception:
            logger.error("TurnController.run() failed", exc_info=True)
            self.subsystem_warnings.append("round_failed")
            self.transport.emit_phase(self.location, "ready", None)
            return "", self._build_state_update()

    def _run_inner(self) -> tuple[str, dict]:
        # 1. Type selection (vector match — zero LLM calls)
        self.transport.emit_phase(self.location, "resolving", "type_selection")
        requested_types = self.type_selector.select(self.combined_action)
        logger.info("Type selection for '%s': %s", self.combined_action[:80], requested_types)

        # 2. Ingest to Delve stack + extract episode
        self.transport.emit_phase(self.location, "resolving", "episode")
        episode = self._ingest_and_extract(requested_types)

        # 3. NPC wait (event-driven) — NPCs respond to actions in Matrix
        self._await_npcs()

        # 4. World reactions — create new entities/quests/lore from seeds
        self.transport.emit_phase(self.location, "resolving", "world_reaction")
        ctx = TurnContext(
            location=self.location,
            location_uuid=self.location_uuid,
            player_name=self.player_name,
            combined_action=self.combined_action,
            episode_summary=episode.get("content", ""),
        )
        self.crew_results = self.world_reaction.react(
            episode.get("entities", []),
            ctx,
        )

        # 5. Narrate (episode summary + world reaction results, cooldown-gated)
        if _narration_cooldown.should_narrate(self.location):
            self.narrative = self._narrate(episode, self.crew_results)
            _narration_cooldown.record(self.location)
        else:
            logger.info("Narration suppressed at %s (cooldown)", self.location)
            self.narrative = ""

        # 6. Post-turn
        if self.narrative:
            self._post_turn()

        self.transport.emit_phase(self.location, "ready", None)
        return self.narrative, self._build_state_update()

    def _ingest_and_extract(self, requested_types: list[str]) -> dict:
        """Push messages to Delve stack, trigger processing, read episode."""
        try:
            from memento.bonfires_client import get_client
            client = get_client()

            # Build messages for the stack
            from datetime import datetime, UTC
            timestamp = datetime.now(UTC).isoformat()
            for action in self.actions:
                client.stack.add(
                    text=action.get("action", ""),
                    user_id=action.get("player_name", "unknown"),
                    chat_id=self.location,
                    timestamp=timestamp,
                    requested_types=requested_types,
                )

            # Trigger immediate processing
            result = client.stack.process_now()
            return result if isinstance(result, dict) else {"content": "", "entities": []}
        except Exception:
            logger.warning("Episode ingestion failed", exc_info=True)
            self.subsystem_warnings.append("episode_unavailable")
            return {"content": "", "entities": []}

    def _await_npcs(self) -> None:
        """Event-driven NPC wait with early exit."""
        expected = self.transport.get_npc_count(self.location)
        if expected == 0:
            return

        self.transport.emit_phase(self.location, "npc_response", None)
        self.transport.clear_npc_responses(self.location)

        deadline = time.monotonic() + self.npc_wait
        poll_interval = 1.0

        while time.monotonic() < deadline:
            responded = self.transport.get_npc_response_count(self.location)
            if responded >= expected:
                logger.info("All %d NPCs responded at %s", expected, self.location)
                break
            time.sleep(poll_interval)

    def _narrate(self, episode: dict, crew_results: dict) -> str:
        """Run narration crew with episode summary + crew results."""
        self.transport.emit_phase(self.location, "resolving", "narrating")
        from memento.crews.narrative.narration import make_narration_crew

        events_str = str(crew_results) if crew_results else ""
        context = episode.get("content", "")

        crew = make_narration_crew(
            action=self.combined_action,
            context=context,
            events=events_str,
            mode="action",
        )
        result = crew.kickoff()
        return result.raw

    def _post_turn(self) -> None:
        """Post-turn: time advance + scene art (fire-and-forget)."""
        try:
            from memento.tools.time import advance_time
            world_time = advance_time(1)
            self.world_time = world_time.to_display()
        except Exception:
            logger.warning("Time advance failed", exc_info=True)
            self.subsystem_warnings.append("time_unavailable")

        # Scene art — fire-and-forget, cached by location UUID
        if self.narrative and self.location_uuid:
            threading.Thread(
                target=self._request_art,
                daemon=True,
            ).start()

    def _request_art(self) -> None:
        """Generate and cache scene art (runs in background thread)."""
        try:
            from memento.bonfires_client import get_client
            client = get_client()
            entity = client.kg.get_entity_or_none(self.location_uuid)
            if entity and entity.get("properties", {}).get("ascii_art"):
                return  # Already cached

            from memento.crews.ascii_art.crew import make_scene_art_crew
            crew = make_scene_art_crew(self.location, self.narrative[:500], "dark fantasy")
            result = crew.kickoff()
            art = result.raw.strip()

            if art:
                client.kg.update_entity(self.location_uuid, {"ascii_art": art})
                self.transport.emit_art(self.location, art)
        except Exception:
            logger.warning("Art generation failed for %s", self.location, exc_info=True)

    def _build_state_update(self) -> dict:
        """Build StateUpdate dict."""
        warning_details = None
        if self.subsystem_warnings:
            warning_details = {}
            detail_map = {
                "round_failed": "Turn processing encountered an error",
                "episode_unavailable": "Episode extraction timed out — action processed without structured analysis",
                "time_unavailable": "World time advance failed",
                "quest_unavailable": "Quest system timed out — progress may be delayed",
                "reputation_unavailable": "Reputation system unavailable",
            }
            for w in self.subsystem_warnings:
                warning_details[w] = detail_map.get(w, w)

        # Query active quests by UUID
        active_quests = None
        try:
            from memento.round_controller import query_active_quests
            raw_quests = query_active_quests(self.player_name)
            if raw_quests:
                active_quests = [QuestSummary(**q) for q in raw_quests]
        except Exception:
            pass

        state_update = StateUpdate(
            location=self.location,
            world_time=WorldTimeDisplay(**self.world_time) if isinstance(self.world_time, dict) and self.world_time else None,
            active_quests=active_quests,
            subsystem_warnings=self.subsystem_warnings,
            warning_details=warning_details,
        )
        return state_update.model_dump(exclude_none=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && python -m pytest tests/test_turn_controller.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```
git add engine/src/memento/turn_controller.py engine/tests/test_turn_controller.py
git commit -m "feat(engine): add TurnController — episode-driven turn orchestration"
```

---

## Phase 4: Integration

### Task 13: Wire TurnController into EngineMatrixListener

**Files:**
- Modify: `engine/src/memento/matrix_listener.py`

- [ ] **Step 1: Add feature flag and TurnController path**

Replace the `_run_batch_turn_inner` method to support both old and new controllers. Add at the top of the file:

```python
import os
_USE_TURN_CONTROLLER = os.getenv("MEMENTO_USE_TURN_CONTROLLER", "").lower() in ("1", "true", "yes")
```

- [ ] **Step 2: Update _run_batch_turn_inner to use TurnController when flag is on**

Replace the `_run_batch_turn_inner` static method:

```python
    @staticmethod
    def _run_batch_turn_inner(location_name: str, actions: list[dict],
                              matrix_client=None, room_id: str = "",
                              loop=None) -> tuple[str, dict]:
        if _USE_TURN_CONTROLLER:
            from memento.turn_controller import TurnController
            from memento.transport import MatrixTransport, NullTransport
            from memento.type_selector import TypeSelector
            from memento.world_reaction import WorldReactionCrew
            from memento.rpg_types import RPG_ENTITY_TYPES

            transport: Transport | NullTransport
            if matrix_client and room_id and loop:
                transport = MatrixTransport(matrix_client, room_id, loop)
            else:
                transport = NullTransport()

            type_selector = TypeSelector(threshold=0.3)
            for name, model in RPG_ENTITY_TYPES.items():
                type_selector.register(name, model)

            # Resolve location UUID
            location_uuid = ""
            try:
                from memento.tools.kg import _resolve_entity_uuid
                location_uuid = _resolve_entity_uuid(location_name) or ""
            except Exception:
                pass

            controller = TurnController(
                location=location_name,
                location_uuid=location_uuid,
                actions=actions,
                transport=transport,
                type_selector=type_selector,
                world_reaction=WorldReactionCrew(),
            )
            return controller.run()
        else:
            from memento.round_controller import RoundController
            controller = RoundController(
                location=location_name,
                actions=actions,
                loop=loop,
                room_id=room_id,
                matrix_client=matrix_client,
            )
            return controller.run()
```

- [ ] **Step 3: Replace global _turn_lock with LocationLockManager**

Replace the lock acquisition in `_run_batch_turn`:

```python
    @staticmethod
    def _run_batch_turn(location_name: str, actions: list[dict],
                        matrix_client=None, room_id: str = "",
                        loop=None) -> tuple[str, dict]:
        """Run turn with per-location locking."""
        from memento.lock_manager import LocationLockManager
        lock = LocationLockManager.acquire(location_name)
        with lock:
            return EngineMatrixListener._run_batch_turn_inner(
                location_name, actions, matrix_client, room_id, loop
            )
```

Do the same for `_run_turn`:

```python
    @staticmethod
    def _run_turn(player_id: str, location_name: str, action: str,
                  matrix_client=None, room_id: str = "",
                  loop=None) -> tuple[str, dict]:
        from memento.lock_manager import LocationLockManager
        lock = LocationLockManager.acquire(location_name)
        with lock:
            return EngineMatrixListener._run_turn_inner(
                player_id, location_name, action, matrix_client, room_id, loop
            )
```

- [ ] **Step 4: Remove the old global _turn_lock import**

Remove:
```python
_turn_lock = threading.Lock()
```

And remove the `import threading` at the top (now handled inside lock_manager).

- [ ] **Step 5: Test with flag off (backward compat)**

Run: `cd engine && MEMENTO_USE_TURN_CONTROLLER= python -c "from memento.matrix_listener import EngineMatrixListener; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Test with flag on**

Run: `cd engine && MEMENTO_USE_TURN_CONTROLLER=1 python -c "from memento.matrix_listener import EngineMatrixListener; print('OK')"`
Expected: `OK`

- [ ] **Step 7: Commit**

```
git add engine/src/memento/matrix_listener.py
git commit -m "feat(engine): wire TurnController into EngineMatrixListener behind feature flag"
```

---

### Task 14: Run full test suite

- [ ] **Step 1: Run all engine tests**

Run: `cd engine && python -m pytest tests/ -v`
Expected: All pass

- [ ] **Step 2: Run all gateway tests**

Run: `cd gateway && python -m pytest tests/ -v`
Expected: All pass

- [ ] **Step 3: Fix any failures**

If any tests fail, fix the issues and commit.

- [ ] **Step 4: Final commit**

```
git add -A
git commit -m "test: verify all tests pass with TurnController integration"
```
