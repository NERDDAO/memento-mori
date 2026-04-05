# TurnController Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace RoundController with an episode-driven TurnController where Graphiti custom types drive crew routing, vector similarity selects types per turn, and per-location locking enables parallel turn processing.

**Architecture:** Delve stack gets per-caller custom types. The engine defines RPG Pydantic types, vector-matches action text to select relevant types, pushes to stack, reads back structured extraction, and routes to crews based on what Graphiti found. Matrix transport is injected via protocol.

**Tech Stack:** Python 3.12, Pydantic v2, CrewAI, Graphiti (via Delve), sentence-transformers (embeddings), pytest, asyncio

**Spec:** `docs/superpowers/specs/2026-04-05-turn-controller-design.md`

---

## File Structure

### New files (memento-mori engine)

| File | Responsibility |
|------|---------------|
| `engine/src/memento/rpg_types.py` | Pydantic custom types for Graphiti extraction (CombatAction, QuestInteraction, etc.) |
| `engine/src/memento/type_selector.py` | Vector-match action text against type descriptions, returns requested_types |
| `engine/src/memento/crew_router.py` | Maps extracted Graphiti entity types to crew callables, resolves UUIDs |
| `engine/src/memento/transport.py` | Transport protocol + MatrixTransport + NullTransport |
| `engine/src/memento/lock_manager.py` | Per-location threading locks |
| `engine/src/memento/narration_cooldown.py` | Persistent JSON-backed narration cooldown |
| `engine/src/memento/turn_controller.py` | Main orchestrator — thin pipeline coordinating all components |
| `engine/tests/test_lock_manager.py` | Tests for LocationLockManager |
| `engine/tests/test_narration_cooldown.py` | Tests for NarrationCooldown |
| `engine/tests/test_type_selector.py` | Tests for TypeSelector |
| `engine/tests/test_crew_router.py` | Tests for CrewRouter |
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

### Task 4: RPG Custom Types

**Files:**
- Create: `engine/src/memento/rpg_types.py`

- [ ] **Step 1: Write the RPG type models**

```python
# engine/src/memento/rpg_types.py
"""RPG custom types for Graphiti episode extraction.

Each type's docstring is used as the matching corpus for the TypeSelector.
Graphiti's add_episode LLM extracts structured entities matching these models.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CombatAction(BaseModel):
    """Extracted when player actions involve combat, fighting, attacking, or violence."""

    attacker_name: str = Field(..., description="Name of the attacker")
    target_name: str = Field(..., description="Name of the target being attacked")
    weapon_or_method: str | None = Field(None, description="Weapon or method used")
    context: str = Field("", description="Brief scene context for the combat")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["CombatAction"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {"attacker_name": self.attacker_name, "target_name": self.target_name}
        if self.weapon_or_method:
            out["weapon_or_method"] = self.weapon_or_method
        if self.context:
            out["context"] = self.context
        return out


class QuestInteraction(BaseModel):
    """Extracted when player interacts with quest content, accepts a quest, progresses a quest, or discovers quest-related information."""

    player_name: str = Field(..., description="Name of the player")
    npc_name: str | None = Field(None, description="Quest giver or relevant NPC")
    action_type: str = Field("", description="One of: accept, progress, complete, discover")
    quest_hint: str = Field("", description="What the quest seems to involve")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["QuestInteraction"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {"player_name": self.player_name}
        if self.npc_name:
            out["npc_name"] = self.npc_name
        if self.action_type:
            out["action_type"] = self.action_type
        if self.quest_hint:
            out["quest_hint"] = self.quest_hint
        return out


class SocialInteraction(BaseModel):
    """Extracted when player engages in faction-affecting, reputation-affecting, or social actions like persuasion, intimidation, or diplomacy."""

    player_name: str = Field(..., description="Name of the player")
    faction_or_npc: str = Field("", description="Faction or NPC involved")
    sentiment: str = Field("", description="One of: friendly, hostile, neutral")
    action_summary: str = Field("", description="Brief summary of the social action")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["SocialInteraction"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {"player_name": self.player_name}
        if self.faction_or_npc:
            out["faction_or_npc"] = self.faction_or_npc
        if self.sentiment:
            out["sentiment"] = self.sentiment
        if self.action_summary:
            out["action_summary"] = self.action_summary
        return out


class TradeAction(BaseModel):
    """Extracted when player buys, sells, trades, or exchanges items with an NPC or merchant."""

    player_name: str = Field(..., description="Name of the player")
    counterparty: str = Field("", description="NPC name or 'merchant'")
    items_given: list[str] = Field(default_factory=list, description="Items given by the player")
    items_received: list[str] = Field(default_factory=list, description="Items received by the player")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["TradeAction"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {"player_name": self.player_name}
        if self.counterparty:
            out["counterparty"] = self.counterparty
        if self.items_given:
            out["items_given"] = self.items_given
        if self.items_received:
            out["items_received"] = self.items_received
        return out


class MovementAction(BaseModel):
    """Extracted when player moves between locations, travels, walks, or goes to a new area."""

    player_name: str = Field(..., description="Name of the player")
    from_location: str | None = Field(None, description="Origin location")
    to_location: str = Field("", description="Destination location")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["MovementAction"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {"player_name": self.player_name}
        if self.from_location:
            out["from_location"] = self.from_location
        if self.to_location:
            out["to_location"] = self.to_location
        return out


# Registry of all RPG types — used by TypeSelector and Delve type registration
RPG_ENTITY_TYPES: dict[str, type[BaseModel]] = {
    "CombatAction": CombatAction,
    "QuestInteraction": QuestInteraction,
    "SocialInteraction": SocialInteraction,
    "TradeAction": TradeAction,
    "MovementAction": MovementAction,
}
```

- [ ] **Step 2: Verify models are valid**

Run: `cd engine && python -c "from memento.rpg_types import RPG_ENTITY_TYPES; print(list(RPG_ENTITY_TYPES.keys()))"`
Expected: `['CombatAction', 'QuestInteraction', 'SocialInteraction', 'TradeAction', 'MovementAction']`

- [ ] **Step 3: Commit**

```
git add engine/src/memento/rpg_types.py
git commit -m "feat(engine): add RPG custom types for Graphiti episode extraction"
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


def test_select_combat_action():
    ts = TypeSelector(threshold=0.3)
    for name, model in RPG_ENTITY_TYPES.items():
        ts.register(name, model)

    result = ts.select("I attack the goblin with my sword")
    assert "CombatAction" in result


def test_select_trade_action():
    ts = TypeSelector(threshold=0.3)
    for name, model in RPG_ENTITY_TYPES.items():
        ts.register(name, model)

    result = ts.select("I want to buy a healing potion from the merchant")
    assert "TradeAction" in result


def test_simple_action_may_match_nothing_or_few():
    ts = TypeSelector(threshold=0.6)  # stricter threshold
    for name, model in RPG_ENTITY_TYPES.items():
        ts.register(name, model)

    result = ts.select("I look around the room")
    # At strict threshold, a generic action shouldn't match combat/trade/quest
    assert "CombatAction" not in result


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

### Task 10: RPG types in Delve type registry

**Files:**
- Modify: `delve/src/core/services/knowledge_graph/custom_types.py`

- [ ] **Step 1: Add RPG types to the registry**

Add the RPG type classes at the end of the file, before the `CUSTOM_ENTITY_TYPES` list. These are copies of the memento-mori types but registered in Delve's type system:

```python
# --- RPG custom types (registered by memento-mori bonfire) ---

class CombatAction(BaseModel):
    """Extracted when player actions involve combat, fighting, or violence."""
    attacker_name: str | None = Field(None, description="Name of the attacker")
    target_name: str | None = Field(None, description="Name of the target")
    weapon_or_method: str | None = Field(None, description="Weapon or method used")
    context: str | None = Field(None, description="Brief scene context")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["CombatAction"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.attacker_name is not None:
            out["attacker_name"] = self.attacker_name
        if self.target_name is not None:
            out["target_name"] = self.target_name
        if self.weapon_or_method is not None:
            out["weapon_or_method"] = self.weapon_or_method
        if self.context is not None:
            out["context"] = self.context
        return out


class QuestInteraction(BaseModel):
    """Extracted when player interacts with quest content."""
    player_name: str | None = Field(None, description="Name of the player")
    npc_name: str | None = Field(None, description="Quest giver or relevant NPC")
    action_type: str | None = Field(None, description="accept, progress, complete, discover")
    quest_hint: str | None = Field(None, description="What the quest involves")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["QuestInteraction"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.player_name is not None:
            out["player_name"] = self.player_name
        if self.npc_name is not None:
            out["npc_name"] = self.npc_name
        if self.action_type is not None:
            out["action_type"] = self.action_type
        if self.quest_hint is not None:
            out["quest_hint"] = self.quest_hint
        return out


class SocialInteraction(BaseModel):
    """Extracted when player engages in faction or reputation-affecting social actions."""
    player_name: str | None = Field(None, description="Name of the player")
    faction_or_npc: str | None = Field(None, description="Faction or NPC involved")
    sentiment: str | None = Field(None, description="friendly, hostile, neutral")
    action_summary: str | None = Field(None, description="Summary of the social action")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["SocialInteraction"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.player_name is not None:
            out["player_name"] = self.player_name
        if self.faction_or_npc is not None:
            out["faction_or_npc"] = self.faction_or_npc
        if self.sentiment is not None:
            out["sentiment"] = self.sentiment
        if self.action_summary is not None:
            out["action_summary"] = self.action_summary
        return out


class TradeAction(BaseModel):
    """Extracted when player buys, sells, or trades items."""
    player_name: str | None = Field(None, description="Name of the player")
    counterparty: str | None = Field(None, description="NPC name or merchant")
    items_given: list[str] = Field(default_factory=list, description="Items given")
    items_received: list[str] = Field(default_factory=list, description="Items received")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["TradeAction"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.player_name is not None:
            out["player_name"] = self.player_name
        if self.counterparty is not None:
            out["counterparty"] = self.counterparty
        if self.items_given:
            out["items_given"] = self.items_given
        if self.items_received:
            out["items_received"] = self.items_received
        return out


class MovementAction(BaseModel):
    """Extracted when player moves between locations."""
    player_name: str | None = Field(None, description="Name of the player")
    from_location: str | None = Field(None, description="Origin location")
    to_location: str | None = Field(None, description="Destination location")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["MovementAction"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.player_name is not None:
            out["player_name"] = self.player_name
        if self.from_location is not None:
            out["from_location"] = self.from_location
        if self.to_location is not None:
            out["to_location"] = self.to_location
        return out
```

- [ ] **Step 2: Add RPG types to CUSTOM_ENTITY_TYPES and get_graphiti_entity_types()**

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
    CombatAction,
    QuestInteraction,
    SocialInteraction,
    TradeAction,
    MovementAction,
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
        "CombatAction": CombatAction,
        "QuestInteraction": QuestInteraction,
        "SocialInteraction": SocialInteraction,
        "TradeAction": TradeAction,
        "MovementAction": MovementAction,
    }
```

- [ ] **Step 3: Commit**

```
cd delve && git add src/core/services/knowledge_graph/custom_types.py
git commit -m "feat: register RPG custom types for Graphiti episode extraction"
```

---

## Phase 3: Orchestration (memento-mori)

### Task 11: CrewRouter

**Files:**
- Create: `engine/src/memento/crew_router.py`
- Create: `engine/tests/test_crew_router.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/test_crew_router.py
from memento.crew_router import CrewRouter, TurnContext


def test_no_entities_returns_empty():
    router = CrewRouter()
    ctx = TurnContext(location="tavern", location_uuid="loc-123", player_name="Kael")
    result = router.route([], ctx)
    assert result == {}


def test_combat_entity_triggers_combat_handler():
    router = CrewRouter()
    ctx = TurnContext(location="tavern", location_uuid="loc-123", player_name="Kael")
    entities = [{"type": "CombatAction", "attacker_name": "Kael", "target_name": "Grumlock"}]
    result = router.route(entities, ctx)
    assert "CombatAction" in result


def test_unknown_type_is_skipped():
    router = CrewRouter()
    ctx = TurnContext(location="tavern", location_uuid="loc-123", player_name="Kael")
    entities = [{"type": "UnknownType", "data": "whatever"}]
    result = router.route(entities, ctx)
    assert result == {}


def test_multiple_entities_routes_all():
    router = CrewRouter()
    ctx = TurnContext(location="tavern", location_uuid="loc-123", player_name="Kael")
    entities = [
        {"type": "CombatAction", "attacker_name": "Kael", "target_name": "Grumlock"},
        {"type": "QuestInteraction", "player_name": "Kael", "npc_name": "Innkeeper"},
    ]
    result = router.route(entities, ctx)
    assert "CombatAction" in result
    assert "QuestInteraction" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd engine && python -m pytest tests/test_crew_router.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement CrewRouter**

```python
# engine/src/memento/crew_router.py
"""CrewRouter — maps extracted Graphiti entity types to crew callables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from memento.log import get_logger

logger = get_logger(__name__)


@dataclass
class TurnContext:
    """Context passed to crew handlers."""
    location: str
    location_uuid: str
    player_name: str
    combined_action: str = ""
    episode_summary: str = ""


@dataclass
class CrewRoute:
    type_name: str
    handler: Callable[[dict, TurnContext], dict]


class CrewRouter:
    """Routes extracted Graphiti entity types to crew callables."""

    def __init__(self) -> None:
        self.routes: list[CrewRoute] = [
            CrewRoute("CombatAction", self._handle_combat),
            CrewRoute("QuestInteraction", self._handle_quest),
            CrewRoute("SocialInteraction", self._handle_social),
            CrewRoute("TradeAction", self._handle_trade),
        ]

    def route(self, extracted_entities: list[dict], ctx: TurnContext) -> dict[str, Any]:
        """Run crews for all extracted entity types. Returns merged results."""
        results: dict[str, Any] = {}
        extracted_types = {e.get("type") for e in extracted_entities}

        for route in self.routes:
            if route.type_name in extracted_types:
                entity = next(
                    (e for e in extracted_entities if e.get("type") == route.type_name),
                    None,
                )
                if entity is None:
                    continue
                try:
                    resolved = self._resolve_uuids(entity, ctx)
                    results[route.type_name] = route.handler(resolved, ctx)
                except Exception:
                    logger.warning("Crew route %s failed", route.type_name, exc_info=True)
                    results[route.type_name] = {"error": f"{route.type_name}_failed"}

        return results

    def _resolve_uuids(self, entity: dict, ctx: TurnContext) -> dict:
        """Resolve entity name references to UUIDs via KG search.

        Scoped to the current location. Returns entity dict with uuid fields added.
        If resolution fails, the entity is returned as-is (handler decides what to do).
        """
        resolved = dict(entity)
        name_fields = ["target_name", "npc_name", "counterparty", "faction_or_npc"]

        for field in name_fields:
            name = entity.get(field)
            if not name:
                continue
            try:
                from memento.bonfires_client import get_client
                client = get_client()
                result = client.kg.search(name, num_results=3)
                entities = result.get("entities", result.get("nodes", []))
                for e in entities:
                    if e.get("name", "").lower() == name.lower():
                        resolved[f"{field}_uuid"] = e.get("uuid", "")
                        break
            except Exception:
                logger.debug("UUID resolution failed for %s=%s", field, name)

        return resolved

    def _handle_combat(self, entity: dict, ctx: TurnContext) -> dict:
        """Run CombatFlow with resolved entity data."""
        from memento.flows.combat import CombatFlow

        flow = CombatFlow()
        flow.state.action = ctx.combined_action
        flow.state.attacker = entity.get("attacker_name", ctx.player_name)
        flow.state.target = entity.get("target_name", "unknown")
        flow.state.location = ctx.location
        flow.state.context = ctx.episode_summary
        flow.kickoff()

        return {
            "resolution": flow.state.resolution,
            "consequences": flow.state.consequences,
            "target_uuid": entity.get("target_name_uuid", ""),
        }

    def _handle_quest(self, entity: dict, ctx: TurnContext) -> dict:
        """Run QuestFlow with resolved entity data."""
        from memento.flows.quest import QuestFlow

        flow = QuestFlow()
        flow.state.location = ctx.location
        flow.state.npc = entity.get("npc_name", "unknown")
        flow.state.player_level = 1
        flow.kickoff()

        return {
            "quest_concept": flow.state.quest_concept,
            "npc_uuid": entity.get("npc_name_uuid", ""),
        }

    def _handle_social(self, entity: dict, ctx: TurnContext) -> dict:
        """Run reputation crew with resolved entity data."""
        from memento.crews.faction.reputation import make_reputation_crew

        crew = make_reputation_crew(
            player=ctx.player_name,
            faction=entity.get("faction_or_npc", "unknown"),
            action=ctx.combined_action,
        )
        result = crew.kickoff()

        return {
            "reputation": result.raw,
            "faction": entity.get("faction_or_npc", ""),
        }

    def _handle_trade(self, entity: dict, ctx: TurnContext) -> dict:
        """Handle trade actions via inventory system."""
        return {
            "counterparty": entity.get("counterparty", ""),
            "items_given": entity.get("items_given", []),
            "items_received": entity.get("items_received", []),
            "counterparty_uuid": entity.get("counterparty_uuid", ""),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && python -m pytest tests/test_crew_router.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```
git add engine/src/memento/crew_router.py engine/tests/test_crew_router.py
git commit -m "feat(engine): add CrewRouter — maps Graphiti types to crew callables"
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
from memento.crew_router import CrewRouter


def _make_controller(**overrides):
    defaults = dict(
        location="tavern",
        location_uuid="loc-123",
        actions=[{"player_name": "Kael", "action": "look around"}],
        transport=NullTransport(),
        type_selector=TypeSelector(threshold=0.3),
        crew_router=CrewRouter(),
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

from memento.crew_router import CrewRouter, TurnContext
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
        crew_router: CrewRouter,
        npc_wait: float = 15.0,
    ) -> None:
        self.location = location
        self.location_uuid = location_uuid
        self.actions = actions
        self.transport = transport
        self.type_selector = type_selector
        self.crew_router = crew_router
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

        # 3. Route extracted types to crews
        self.transport.emit_phase(self.location, "resolving", "crews")
        ctx = TurnContext(
            location=self.location,
            location_uuid=self.location_uuid,
            player_name=self.player_name,
            combined_action=self.combined_action,
            episode_summary=episode.get("content", ""),
        )
        self.crew_results = self.crew_router.route(
            episode.get("entities", []),
            ctx,
        )

        # 4. NPC wait (event-driven)
        self._await_npcs()

        # 5. Narrate (cooldown-gated)
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
            from memento.crew_router import CrewRouter
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
                crew_router=CrewRouter(),
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
