# Memento Mori — Immersive Opening, Engine Core (V1·a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.
>
> On approval, the full plan is committed to `memento-mori/docs/superpowers/plans/2026-06-21-mmori-immersive-opening-engine-core.md`. Spec: `memento-mori/docs/superpowers/specs/2026-06-21-mmori-immersive-opening-design.md`.

**Goal:** Build the deterministic engine core of Memento Mori's immersive opening — `look`-to-build accretion, lazy-canon materialization on intent, a scene director that orders the three onboarding beats (witnessed death → diegetic controls → cross-the-exit goal) — entirely inside `memento-mori/engine`, tested with the existing Fake/InMemory doubles.

**Architecture:** A new `opening/` package (sparse salience-weighted seed + `SceneDirector` + swappable `DescribeClient`) layered onto the existing cxn turn pipeline. `look` is a read-only construction routed through a describe port; materialization is a promote-on-miss branch in `EntityResolver`; beats and the win-predicate live in `SceneDirector`. No LLM in V1·a — a deterministic `TemplateDescribeClient` sits behind the describe port (the LLM describer is a later swap). No self-"I"/name-routing, no gateway server, no client — those are follow-on plans.

**Tech Stack:** Python 3.x, `TypedDict`/`@dataclass`, pytest (`asyncio_mode = "auto"`), `InMemoryStateRepository`, `FakeComprehensionClient`.

## Context

This is slice **V1·a** of the immersive-opening spec. Exploration confirmed the look-to-build core is self-contained in `memento-mori/engine` against stable seams, while the self-agent spine (self-"I" gate, name→profile routing, the activation-store gateway, the inner-dialogue backend) is ~100% net-new across three repos and is deferred to its own plan. Building the engine core first de-risks the novel mechanics deterministically and gives the later self-agent/client plans a tested foundation.

## Global Constraints

- All paths under `/home/at0x/Vaults/Bonfires/memento-mori/engine/`. Run gates from `engine/`: `python -m pytest` (asyncio_mode=auto — async tests need **no** decorator), `ruff check src/ tests/`, `ruff format src/ tests/`.
- **Do NOT touch `engine/src/memento/seed.py`** (the existing CrewAI "Threshold" + narrator seeding) — the new opening system lives in a new package `engine/src/memento/opening/`.
- **UUIDs, never names**, for identity/lookups/matching (repo convention). Names are display-only.
- **`TypedDict` additions must use `typing.NotRequired`** so existing literal constructions stay valid (`CxnDef`, `TurnOutcome` are total today).
- **New constructor deps on `EntityResolver` and `TurnRouter` are optional (`= None`)** so the existing unit tests (`test_entity_resolver.py`, `test_turn_router.py`) stay green without edits.
- Reuse existing test doubles: `FakeComprehensionClient` (`cxn/kernel_client.py`), `InMemoryStateRepository` (`state/in_memory.py`, with `seed_entity`/`seed_item`), `CapturingMemoryClient`, `NoopChainMirror`. Reuse `engine/tests/fixtures.py` builders (`character_doc`, `location_doc`, `item_doc`) + UUID constants.
- TDD per task; commit trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`; stage only touched files.

## Verified seams (from exploration)

- `EntityResolver.resolve(frame, actor_id, cxn)` → `dict[str,str] | ResolutionFailure`; miss points are `_resolve_patient` (in_memory `entity_resolver.py:160-161`, no-location `:151-152`) and `_resolve_instrument` (`:186-187`); `cxn` already threaded in, unused. `ResolutionFailure = {"reason": str}` (`unresolved_role:<r>` / `ambiguous_role:<r>`).
- `TurnRouter.handle(utterance, actor_id) -> TurnOutcome`: comprehend → predicate lookup (`turn_router.py:96-107`) → resolve → build `SemanticFrame` → `constructicon.match` → `executor.execute`. The read-only `look` branch slots in **right after predicate lookup**, before resolve.
- `EffectExecutor.execute(cxn, caller_id, bindings)` — positional only (no `active_construct_ids`). MOVE effect = `move_entity($agent→$location)`; `_phase1` defaults `roles["location"]` to the agent's CURRENT location if `None` (`executor.py:221-228`), so a MOVE destination must be **bound explicitly** before execute. `exit_exists` guard reads room `attrs["exits"][].target_uuid` (`executor.py:74`).
- `ComprehendedFrame = {predicate, roles: list[FrameRole], matched, raw_text}`; `FrameRole = {role, filler}`. `EntityResolver.resolve` skips `agent`/`location` roles.
- State: rooms = `EntityDoc` `kind=="location"`, `labels=["Location"]`, `attrs["exits"] = [{"direction","target_uuid",...}]`, `attrs["description"]`. `InMemoryStateRepository.seed_entity(doc)` / `seed_item(doc)` (item stored in BOTH `_entities` and `_items`, so a seeded item is also returned by `get_entities_at_location` → resolvable as a `patient`). Mark dead = `set_attr(uuid,"is_dead",True)` (top-level) + `link(uuid, location, "DIED_IN")`. `get_actor_snapshot(uuid)["location"]` = location_uuid.
- `CONSTRUCTION_REGISTRY` keyed by cxn `name`; `ConstructiconRegistry.match` dispatches by `predicate`. `_validate_conditions()` runs at import over `effect_template` `if_condition`s (empty template = safe).
- Tests: `engine/tests/unit/`, `engine/tests/integration/`; `fixtures.py` UUID consts (`KAEL, GOBLIN, IRON_SWORD, ASH_MARKET, …`) + doc builders.

## File Structure

**New package `engine/src/memento/opening/`:**
- `seed_types.py` — `SeedFact`, `SeedRoom` (pure data).
- `describe.py` — `DescribeRequest`/`DescribeResult`, `DescribeClient` Protocol, `TemplateDescribeClient` (deterministic default), `FakeDescribeClient` (canned, tests).
- `director.py` — `SceneDirector` (latent facts, surfaced/materialized sets, salience order, `on_surface` beats incl. witnessed death, win-predicate).
- `loader.py` — `load_seed_room(seed, repo, actor_id) -> SceneDirector`.
- `deep_roads.py` — the authored seed room (`deep_roads_seed()`).

**Modified (cxn pipeline):**
- `cxn/types.py` — `CxnDef.read_only: NotRequired[bool]`; `TurnOutcome.narration: NotRequired[str|None]`, `TurnOutcome.won: NotRequired[bool]`.
- `cxn/definitions.py` — `LOOK_CXN` + register it.
- `cxn/turn_router.py` — optional `director`/`describe_client` deps; look branch; MOVE exit-resolution; post-execute win check.
- `cxn/entity_resolver.py` — optional `director` dep; promote-on-miss in patient/instrument misses.

**Tests:** `engine/tests/unit/test_opening_*.py` (per unit) + `engine/tests/integration/test_opening_arc.py`.

---

## Task 1: Seed types

**Files:** Create `engine/src/memento/opening/__init__.py` (empty), `engine/src/memento/opening/seed_types.py`; Test `engine/tests/unit/test_opening_seed_types.py`.

**Interfaces — Produces:**
```python
FORCED_FIRST: int  # = 1_000_000, salience sentinel surfaced before all else

@dataclass(frozen=True)
class SeedFact:
    key: str                       # stable handle, e.g. "dying_adventurer"
    name: str                      # display, e.g. "a dying adventurer"
    kind: str                      # "character" | "item" | "threat"
    salience: int                  # higher surfaces first
    canon: bool                    # True = seeded into repo at load; False = latent (prose-only until intent)
    uuid: str | None = None        # required for canon facts; generated on promote for latent
    labels: tuple[str, ...] = ()
    attrs: Mapping[str, Any] = field(default_factory=dict)
    on_surface: str | None = None  # beat hook key, e.g. "die"

@dataclass(frozen=True)
class SeedRoom:
    location_id: str
    name: str
    description: str
    facts: tuple[SeedFact, ...]
    exits: tuple[Mapping[str, Any], ...]   # {"direction","target_uuid",...}
    win_exit: str                          # direction whose crossing = win
```

- [ ] **Step 1 — failing test** `test_opening_seed_types.py`:
```python
from memento.opening.seed_types import SeedFact, SeedRoom, FORCED_FIRST

def test_seedfact_defaults_and_forced_first():
    f = SeedFact(key="blade", name="an iron blade", kind="item", salience=10, canon=False)
    assert f.uuid is None and f.labels == () and f.attrs == {} and f.on_surface is None
    assert FORCED_FIRST > 0

def test_seedroom_holds_facts_and_win_exit():
    f = SeedFact(key="body", name="a body", kind="character", salience=FORCED_FIRST,
                 canon=True, uuid="507f1f77bcf86cd799439011", on_surface="die")
    room = SeedRoom(location_id="loc1", name="the deep roads", description="dark",
                    facts=(f,), exits=({"direction": "on", "target_uuid": "loc2"},), win_exit="on")
    assert room.facts[0].on_surface == "die" and room.win_exit == "on"
```
- [ ] **Step 2 — run, expect FAIL** (`ModuleNotFoundError`): `python -m pytest tests/unit/test_opening_seed_types.py -v`
- [ ] **Step 3 — implement** `seed_types.py` exactly as the Produces block (with `from __future__ import annotations`, `from dataclasses import dataclass, field`, `from typing import Any`, `from collections.abc import Mapping`).
- [ ] **Step 4 — run, expect PASS.** Then `ruff format src/ tests/ && ruff check src/ tests/`.
- [ ] **Step 5 — commit:** `feat(opening): seed types (SeedFact/SeedRoom)`

---

## Task 2: Describe port + template + fake

**Files:** Create `engine/src/memento/opening/describe.py`; Test `engine/tests/unit/test_opening_describe.py`.

**Interfaces — Consumes:** `SeedFact`. **Produces:**
```python
@dataclass(frozen=True)
class DescribeRequest:
    room_name: str
    room_description: str
    focus: SeedFact | None              # the newly-surfaced fact this turn
    surfaced: tuple[SeedFact, ...]      # previously revealed facts
    candidates: tuple[SeedFact, ...]    # latent, unmaterialized facts currently in view

@dataclass(frozen=True)
class DescribeResult:
    prose: str
    candidates: tuple[str, ...]         # candidate noun display-names (for the future client)

class DescribeClient(Protocol):
    async def describe(self, request: DescribeRequest) -> DescribeResult: ...

class TemplateDescribeClient:   # deterministic default, no LLM
    async def describe(self, request: DescribeRequest) -> DescribeResult: ...

class FakeDescribeClient:       # canned per-focus-key, for tests
    def __init__(self, canned: dict[str, str]) -> None: ...
    async def describe(self, request: DescribeRequest) -> DescribeResult: ...
```

- [ ] **Step 1 — failing test:**
```python
from memento.opening.seed_types import SeedFact
from memento.opening.describe import DescribeRequest, TemplateDescribeClient, FakeDescribeClient

async def test_template_describer_mentions_focus_and_lists_candidates():
    focus = SeedFact(key="body", name="a dying adventurer", kind="character", salience=999, canon=True)
    blade = SeedFact(key="blade", name="an iron blade", kind="item", salience=10, canon=False)
    req = DescribeRequest(room_name="the deep roads", room_description="Cold stone closes in.",
                          focus=focus, surfaced=(), candidates=(blade,))
    res = await TemplateDescribeClient().describe(req)
    assert "deep roads" in res.prose.lower()
    assert "dying adventurer" in res.prose.lower()
    assert res.candidates == ("an iron blade",)

async def test_fake_describer_returns_canned_for_focus_key():
    focus = SeedFact(key="body", name="a dying adventurer", kind="character", salience=999, canon=True)
    req = DescribeRequest(room_name="r", room_description="d", focus=focus, surfaced=(), candidates=())
    res = await FakeDescribeClient({"body": "Someone is dying here."}).describe(req)
    assert res.prose == "Someone is dying here."
```
- [ ] **Step 2 — run, expect FAIL.**
- [ ] **Step 3 — implement.** `TemplateDescribeClient.describe`: `prose = request.room_description` + (focus ? f" Before you, {request.focus.name}." : "") deterministically; `candidates = tuple(c.name for c in request.candidates)`. `FakeDescribeClient.describe`: `prose = self._canned.get(request.focus.key if request.focus else "", request.room_description)`; candidates as template.
- [ ] **Step 4 — run, expect PASS.** Lint.
- [ ] **Step 5 — commit:** `feat(opening): describe port + template/fake clients`

---

## Task 3: SceneDirector

**Files:** Create `engine/src/memento/opening/director.py`; Test `engine/tests/unit/test_opening_director.py`.

**Interfaces — Consumes:** `SeedRoom`, `SeedFact`, `StateRepository`. **Produces:**
```python
class SceneDirector:
    def __init__(self, seed: SeedRoom, repo: StateRepository, actor_id: str) -> None: ...
    @property
    def location_id(self) -> str: ...
    def register_canon_uuid(self, key: str, uuid: str) -> None: ...   # loader records seeded canon uuids
    def next_to_surface(self) -> SeedFact | None: ...                 # highest-salience unsurfaced fact
    def candidates(self) -> tuple[SeedFact, ...]: ...                 # latent, unmaterialized, surfaced-or-not
    def mark_surfaced(self, key: str) -> None: ...
    async def apply_surface_beats(self, fact: SeedFact) -> None: ...  # runs on_surface hooks (e.g. "die")
    def find_latent(self, filler: str) -> SeedFact | None: ...        # latent, unmaterialized, name-match (normalized)
    def mark_materialized(self, key: str, uuid: str) -> None: ...
    async def is_won(self) -> bool: ...                               # actor left location_id
```

Notes: holds `_facts: dict[str,SeedFact]` (all), `_surfaced: set[str]`, `_materialized: set[str]`, `_uuid_by_key: dict[str,str]`. `next_to_surface` = max salience among `_facts` not in `_surfaced` (None if none). `candidates` = facts where `not canon and key not in _materialized`. `find_latent` reuses the resolver normalization (strip `the|a|an`, lowercase) and matches against `fact.name`. `apply_surface_beats`: if `fact.on_surface == "die"` → `uuid = self._uuid_by_key[fact.key]` → `await repo.set_attr(uuid,"is_dead",True)` + `await repo.link(uuid, self._location_id, "DIED_IN")` (idempotent: guard on `is_dead` already True). `is_won`: `snap = await repo.get_actor_snapshot(actor_id); return snap.get("location") != self._location_id`.

- [ ] **Step 1 — failing test** (drive with `InMemoryStateRepository` + fixtures):
```python
from memento.state.in_memory import InMemoryStateRepository
from memento.opening.seed_types import SeedFact, SeedRoom, FORCED_FIRST
from memento.opening.director import SceneDirector

BODY="507f1f77bcf86cd799439011"; LOC="507f1f77bcf86cd799439099"; PLAYER="507f1f77bcf86cd7994390aa"

def _seed():
    body = SeedFact(key="body", name="a dying adventurer", kind="character", salience=FORCED_FIRST,
                    canon=True, uuid=BODY, labels=("Character",), on_surface="die")
    blade = SeedFact(key="blade", name="an iron blade", kind="item", salience=10, canon=False,
                     labels=("Item","Weapon"), attrs={"power":4})
    return SeedRoom(location_id=LOC, name="the deep roads", description="dark",
                    facts=(body,blade), exits=({"direction":"on","target_uuid":"loc2"},), win_exit="on")

async def test_surface_order_and_death_beat():
    repo = InMemoryStateRepository()
    await repo.seed_entity({"uuid":BODY,"name":"adventurer","kind":"character","labels":["Character"],
                            "location_uuid":LOC,"attrs":{},"is_dead":False})
    await repo.seed_entity({"uuid":PLAYER,"name":"you","kind":"character","labels":["Character"],
                            "location_uuid":LOC,"attrs":{"inventory":[]},"is_dead":False})
    d = SceneDirector(_seed(), repo, PLAYER); d.register_canon_uuid("body", BODY)
    first = d.next_to_surface(); assert first.key == "body"          # forced-first
    d.mark_surfaced("body"); await d.apply_surface_beats(first)
    assert (await repo.get_entity(BODY))["is_dead"] is True          # witnessed death
    assert d.next_to_surface().key == "blade"                        # next salient

async def test_find_latent_and_win_predicate():
    repo = InMemoryStateRepository()
    await repo.seed_entity({"uuid":PLAYER,"name":"you","kind":"character","labels":["Character"],
                            "location_uuid":LOC,"attrs":{"inventory":[]},"is_dead":False})
    d = SceneDirector(_seed(), repo, PLAYER)
    assert d.find_latent("the iron blade").key == "blade"            # normalized name-match
    assert await d.is_won() is False
    await repo.move_entity(PLAYER, "loc2")
    assert await d.is_won() is True                                  # left the room
```
- [ ] **Step 2 — run, expect FAIL.**
- [ ] **Step 3 — implement** `SceneDirector` per Produces + notes (reuse `cxn.entity_resolver._normalize` or inline the same regex).
- [ ] **Step 4 — run, expect PASS.** Lint.
- [ ] **Step 5 — commit:** `feat(opening): SceneDirector (surface order, death beat, win predicate)`

---

## Task 4: Seed loader

**Files:** Create `engine/src/memento/opening/loader.py`; Test `engine/tests/unit/test_opening_loader.py`.

**Interfaces — Consumes:** `SeedRoom`, `InMemoryStateRepository`, `SceneDirector`. **Produces:** `async def load_seed_room(seed: SeedRoom, repo: InMemoryStateRepository, actor_id: str) -> SceneDirector`.

Behavior: seed the location EntityDoc (`kind="location"`, `labels=["Location"]`, `attrs={"description": seed.description, "exits": list(seed.exits)}`); for each `fact.canon` seed an EntityDoc (`kind` "character"/"threat") or ItemDoc (`kind="item"` → `seed_item`) at `location_uuid=seed.location_id` with `fact.labels`/`fact.attrs`, and `director.register_canon_uuid(fact.key, fact.uuid)`; **do NOT** seed latent (`canon=False`) facts. Return the constructed `SceneDirector`.

- [ ] **Step 1 — failing test:** after `load_seed_room(_seed(), repo, PLAYER)`: `await repo.get_entity(LOC)` is a location with `attrs["exits"]`; `await repo.get_entity(BODY)` exists (canon); the blade (latent) is **not** present (`get_entities_at_location(LOC)` contains BODY but no blade); returned director `.next_to_surface().key == "body"`.
- [ ] **Step 2 — run, expect FAIL.**
- [ ] **Step 3 — implement** `load_seed_room` per behavior.
- [ ] **Step 4 — run, expect PASS.** Lint.
- [ ] **Step 5 — commit:** `feat(opening): seed-room loader`

---

## Task 5: LOOK construction + TurnOutcome narration + read-only router branch

**Files:** Modify `cxn/types.py`, `cxn/definitions.py`, `cxn/turn_router.py`; Test `engine/tests/unit/test_opening_look.py`.

**Interfaces — Produces (type changes):**
```python
# cxn/types.py
class CxnDef(TypedDict):
    ...
    read_only: NotRequired[bool]
class TurnOutcome(TypedDict):
    ...
    narration: NotRequired[str | None]
    won: NotRequired[bool]
```
`LOOK_CXN: CxnDef` — `name="LOOK"`, `predicate="look"`, `mcp_tool_name="mm_look"`, `description="Look around / examine the scene."`, `semantic_roles=[]`, `restrictions=[]`, `guards=[]`, `chain_mirror=False`, `effect_template=[]`, `episode_template=""`, `read_only=True`. Add to `CONSTRUCTION_REGISTRY`.

`TurnRouter.__init__` gains `director: SceneDirector | None = None, describe_client: DescribeClient | None = None` (after `bonfire_id`, defaulted). In `handle`, **after predicate lookup** (`turn_router.py:96-107`) and before resolve:
```python
if cxn.get("read_only"):
    if self._director is None or self._describe is None:
        return TurnOutcome(status="clarify", update=None,
                           message="There is nothing to perceive.", reason="no_scene")
    fact = self._director.next_to_surface()
    if fact is not None:
        self._director.mark_surfaced(fact.key)
        await self._director.apply_surface_beats(fact)
    loc = await self._state_location_of(actor_id)   # small helper via resolver's repo / snapshot
    req = DescribeRequest(room_name=..., room_description=..., focus=fact,
                          surfaced=(), candidates=self._director.candidates())
    result = await self._describe.describe(req)
    return TurnOutcome(status="narrated", update=None, message=None, reason=None,
                       narration=result.prose)
```
Note: TurnRouter has no repo handle today; add it OR read room name/description from the director's seed (cleaner — director already holds `SeedRoom`). Prefer: expose `director.room_name`/`director.room_description` so the router needs no repo.

- [ ] **Step 1 — failing test:** build a `TurnRouter` with `FakeComprehensionClient({"look around": {"predicate":"look","roles":[],"matched":True,"raw_text":"look around"}})`, a loaded `SceneDirector`, and `FakeDescribeClient({"body":"A dying adventurer lies before you."})`. `outcome = await router.handle("look around", PLAYER)` → `outcome["status"]=="narrated"`, `"dying adventurer" in outcome["narration"]`, and `await repo.get_entity(BODY))["is_dead"] is True` (death beat fired through the look path). A second `handle("look around", …)` surfaces the next fact (no re-death).
- [ ] **Step 2 — run, expect FAIL.**
- [ ] **Step 3 — implement** the type changes, `LOOK_CXN`, and the router branch + optional deps + `director.room_name`/`room_description` accessors.
- [ ] **Step 4 — run, expect PASS.** Re-run `tests/unit/test_turn_router.py` (existing) to confirm green (optional deps default `None`). Lint.
- [ ] **Step 5 — commit:** `feat(opening): LOOK construction + read-only describe branch`

---

## Task 6: Lazy materialization (promote-on-miss)

**Files:** Modify `cxn/entity_resolver.py`; Test `engine/tests/unit/test_opening_materialize.py`.

**Interfaces:** `EntityResolver.__init__(self, state, director: SceneDirector | None = None)`. In `_resolve_patient`, the 0-match branch (`entity_resolver.py:160-161`) and in `_resolve_instrument` (`:186-187`), before returning `unresolved_role`, attempt promotion:
```python
if self._director is not None:
    fact = self._director.find_latent(filler)
    if fact is not None:
        uuid = fact.uuid or _new_object_id()
        doc = {"uuid": uuid, "name": fact.name.removeprefix("a ").removeprefix("an ").removeprefix("the "),
               "kind": fact.kind, "labels": list(fact.labels),
               "location_uuid": location_uuid, "attrs": dict(fact.attrs), "is_dead": False}
        if fact.kind == "item":
            doc["owner_uuid"] = None
            await self._state.seed_item(doc)        # stored in _entities AND _items → resolvable + takeable
        else:
            await self._state.seed_entity(doc)
        self._director.mark_materialized(fact.key, uuid)
        return uuid
```
(`_new_object_id` = 24-hex; reuse any existing id helper, else `uuid4().hex[:24]`.) `seed_entity`/`seed_item` are InMemory-only methods not on the `StateRepository` Protocol — narrow the `director`-present path to the concrete repo, or add `seed_entity`/`seed_item` to the Protocol as a `@runtime_checkable` capability check; **prefer** a small `materialize(doc, *, is_item)` method added to the repo Protocol + InMemory impl so the resolver stays Protocol-typed (no `Any`). Decide in implementation; keep signatures explicit.

- [ ] **Step 1 — failing test:** loaded director with a latent blade; resolver with `director=`. Comprehend frame `{"predicate":"take","roles":[{"role":"patient","filler":"the iron blade"}],"matched":True,...}`. `resolution = await resolver.resolve(frame, PLAYER, TAKE_CXN)` returns a UUID string (not `ResolutionFailure`); `await repo.get_entity(<that uuid>)` exists at `LOC` with `labels` incl. `"Item"`; `director` reports the fact materialized. A control case with `director=None` still returns `{"reason":"unresolved_role:patient"}`.
- [ ] **Step 2 — run, expect FAIL.**
- [ ] **Step 3 — implement** the promote-on-miss branch + the repo `materialize` method (Protocol + InMemory).
- [ ] **Step 4 — run, expect PASS.** Re-run existing `test_entity_resolver.py` green. Lint.
- [ ] **Step 5 — commit:** `feat(opening): lazy materialization on resolve-miss`

---

## Task 7: MOVE exit-resolution + win check

**Files:** Modify `cxn/turn_router.py`; Test `engine/tests/unit/test_opening_win.py`.

**Interfaces:** In `handle`, (a) when `cxn["predicate"] == "move"`, resolve the frame's `location` filler (a direction or exit target-name) against the actor's room exits → `target_uuid`, and inject it into the bound roles before `executor.execute` (set `bound_roles["location"] = target_uuid`); (b) after a successful `execute` of any turn, if `self._director` and `await self._director.is_won()` → set `outcome["won"] = True` and append a handoff narration (stub: `"The road goes on, into the dark."`).

Exit-resolution helper (router-local): read the actor's room (`get_actor_snapshot(actor_id)["location"]` → `get_entity(location)["attrs"]["exits"]`), match the `location` filler against each exit's `direction` (and optionally a name) → `target_uuid`; if no match, fall through to the existing MOVE path (executor will default to current location and the `exit_exists` guard governs). This needs a repo handle on the router — add `repo: StateRepository | None = None` to `TurnRouter.__init__` (optional, defaulted), used only for exit-resolution + win.

- [ ] **Step 1 — failing test:** loaded room with exit `{"direction":"on","target_uuid":"loc2"}`; player seeded at `LOC`. Frame `{"predicate":"move","roles":[{"role":"location","filler":"on"}],"matched":True,...}`. `outcome = await router.handle("go on", PLAYER)` → `outcome["status"]=="executed"`, `outcome.get("won") is True`, and `await repo.get_actor_snapshot(PLAYER))["location"] == "loc2"`.
- [ ] **Step 2 — run, expect FAIL.**
- [ ] **Step 3 — implement** exit-resolution + win check + optional `repo` dep.
- [ ] **Step 4 — run, expect PASS.** Existing `test_turn_router.py` green. Lint.
- [ ] **Step 5 — commit:** `feat(opening): MOVE exit-resolution + win predicate`

---

## Task 8: Authored deep-roads seed + end-to-end opening arc

**Files:** Create `engine/src/memento/opening/deep_roads.py`; Test `engine/tests/integration/test_opening_arc.py`.

**Interfaces — Produces:** `def deep_roads_seed() -> SeedRoom` — dying adventurer (`canon=True, salience=FORCED_FIRST, on_surface="die"`, `labels=("Character",)`), the threat (`canon=False, kind="threat", salience=high, labels=("Character",)`), the iron blade (`canon=False, kind="item", salience=med, labels=("Item","Weapon"), attrs={"power":4}`), and exit `{"direction":"on","target_uuid":<next>}`, `win_exit="on"`.

- [ ] **Step 1 — failing integration test** `test_opening_arc.py` — wire the full stack (`InMemoryStateRepository`, `load_seed_room`, `EntityResolver(repo, director)`, `EffectExecutor(repo, CapturingMemoryClient(), NoopChainMirror())`, `ConstructiconRegistry`, `TurnRouter(comprehension=fake, constructicon, resolver, executor, bonfire_id, director, FakeDescribeClient(...), repo)`), seed a player at the room, drive the three beats with canned frames:
```python
async def test_opening_three_beats_end_to_end():
    # ... setup as above; fake frames for the three utterances ...
    look = await router.handle("look around", PLAYER)
    assert look["status"] == "narrated" and "dying" in look["narration"].lower()
    assert (await repo.get_entity(BODY))["is_dead"] is True                       # BEAT 1 permadeath
    take = await router.handle("take the iron blade", PLAYER)
    assert take["status"] == "executed"
    snap = await repo.get_actor_snapshot(PLAYER)
    assert any("blade" in (i.get("name","")) for i in snap["inventory"])          # BEAT 2 controls/materialize
    go = await router.handle("go on", PLAYER)
    assert go["status"] == "executed" and go.get("won") is True                   # BEAT 3 goal
```
- [ ] **Step 2 — run, expect FAIL.**
- [ ] **Step 3 — implement** `deep_roads_seed()` (and any test-frame fixtures). Tune fact labels/attrs so TAKE's guards (`item_carryable`/`capacity_ok`/`same_room`) pass on the materialized blade.
- [ ] **Step 4 — run, expect PASS.** Full suite green: `python -m pytest`. Lint.
- [ ] **Step 5 — commit:** `feat(opening): deep-roads seed + end-to-end opening arc`

---

## Self-Review (done)

- **Spec coverage (§ of `2026-06-21-mmori-immersive-opening-design.md`):** seed room + salience (§3) → Tasks 1/3/8; lazy canon (§3.1) → Task 6; look-to-build/describe (§4.4) → Tasks 2/5; witnessed-death beat (§3 Beat 1) → Tasks 3/5/8; controls-by-materialization (Beat 2) → Tasks 6/8; goal=cross-exit (Beat 3) → Tasks 7/8; director (§4.6) → Task 3. **Deferred (own plans, noted in §6):** self-"I"/name-routing (§2.1-2.3, systems 10-13), inner-dialogue backend, client rendering (§5), activation gateway, real generation handoff/procgen.
- **Type consistency:** `SceneDirector`/`SeedFact`/`SeedRoom`/`DescribeRequest`/`DescribeResult`/`DescribeClient` names are used identically across tasks; `TurnOutcome.narration`/`won` and `CxnDef.read_only` are `NotRequired`; new constructor deps optional everywhere.
- **No placeholders:** every task has concrete test + impl code and exact gate commands.

## Verification (end-to-end)

From `engine/`:
1. `python -m pytest` — all green (incl. existing `test_turn_router.py`, `test_entity_resolver.py`, `test_executor.py` — additive proof).
2. `python -m pytest tests/integration/test_opening_arc.py -v` — the three beats land: look kills the adventurer (permadeath witnessed), "take the iron blade" materializes a latent item and equips/carries it (controls + lazy canon), "go on" crosses the exit and flags `won` (goal).
3. `ruff format --check src/ tests/ && ruff check src/ tests/` — clean.

## Open follow-ons (next plans)

1. **Self-agent spine** — self-"I" agency gate, name→profile routing, the net-new activation-store gateway server, inner-dialogue backend (needs its own brainstorm; ~100% net-new across kernel/gateway/runtime).
2. **Client rendering** — inner/embodiment typographic split, card lighting + death-darkening, accretion in present/map, the viewer panel; surface `narration`/materialization over the WS contract.
3. **Real describe (LLM) + generation handoff** — swap an LLM `DescribeClient` behind the port; wire the win handoff to procgen.
