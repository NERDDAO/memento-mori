# Reveal/Deepen ECS Room-State Core — Implementation Plan (Slice 1, Plan 1 of N)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Spec: `docs/superpowers/specs/2026-06-26-agent-driven-opening-cxn-catch-design.md` (Components C + H). This is **Plan 1 of the slice** — the headless, single-repo reveal/deepen state machine. Later plans wire it to a gateway `mm_look` MCP tool + incremental draw (Plan 2), the player-persona + agent-runtime + cxn-fired observability (Plan 3), and the cinematic intro (Plan 4).

**Goal:** Build the accretive room reveal-state machine — "looking again adds detail, never starts from scratch" — as pure, backend-agnostic, headless-testable engine code.

**Architecture:** A room's lookable things carry a `reveal_level` component (in `attrs`; 0 = latent, 1 = surfaced, 2+ = deepened) plus a `salience` for ordering. `reveal_or_deepen(repo, location)` advances that state one step per call — REVEAL the next most-salient unseen thing, else DEEPEN the shallowest revealed thing, else `exhausted` — mutating `reveal_level` monotonically via the async `StateRepository` protocol (so it works on both the in-memory and EventSourced/KG backends). `seed_room_ecs` seeds a `SeedRoom`'s facts as ECS entities carrying those components. This is the first real ECS effect (the future `mm_look`'s effect).

**Tech Stack:** Python 3.12, `memento` engine, `pytest` + `pytest-asyncio` (`asyncio_mode = "auto"` — async test functions need **no** `@pytest.mark.asyncio` decorator). Test command: `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest <path> -q`.

## Branch & base

- **Branch:** `opening/cxn-catch` (already cut off `opening/engine-core` @ `0b83829`; carries the spec + Phase-0 spike). Work in the existing worktree `…/scratchpad/mmori-cxn-catch`.
- Single repo (memento-mori), engine only. No cross-service changes in this plan.

## Global Constraints

- Commit trailer (exact, every commit): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Never `git add -A`** — stage only the files each task touches.
- `reveal_or_deepen` MUST use only the async `StateRepository` protocol methods (`get_entities_at_location`, `get_items_at_location`, `set_attr`) so it is backend-agnostic — never reach into a concrete repo's internals or assume in-memory.
- Reveal-state lives in `attrs`: **`reveal_level: int`** (0 latent / 1 surfaced / 2+ deepened) and **`salience: int`**. `set_attr(uuid, "reveal_level", n)` writes `attrs["reveal_level"]` (it writes top-level only for `"is_dead"`; everything else goes to `attrs`).
- `reveal_level` is **monotonic** — it only ever increases, capped at `max_depth`. A look never resets or lowers it.
- A thing is a reveal candidate **iff it carries a `reveal_level` component** — the room/location entity and the player (added in a later plan) are NOT candidates because they aren't seeded with `reveal_level`.
- `get_entities_at_location` **excludes** `kind=="item"`; items come from `get_items_at_location`. The candidate gather MUST union both, or the iron blade (an item) is invisible.
- Ruff-format only the files each task touches (the base isn't ruff-clean): `python3.12 -m ruff format <files>`.

## Key existing symbols (reuse, don't reinvent) — verbatim anchors on `opening/cxn-catch`

- **`SeedRoom` / `SeedFact`** — `engine/src/memento/opening/seed_types.py`. `SeedFact(key, name, kind, salience, canon, uuid=None, labels=(), attrs={}, on_surface=None)` (frozen dataclass). `SeedRoom(location_id, name, description, facts: tuple[SeedFact,...], exits, win_exit)`. `FORCED_FIRST = 1_000_000`.
- **`deep_roads_seed()`** — `engine/src/memento/opening/deep_roads.py`. Returns the `SeedRoom` at `LOC_DEEP_ROADS = "507f1f77bcf86cd799439011"`, name `"the deep roads"`, with 3 facts: `dying_adventurer` (kind `"character"`, salience `FORCED_FIRST`, uuid `"507f1f77bcf86cd799439013"`, name `"a dying adventurer"`), `threat` (kind `"threat"`, salience `100`, uuid `None`, name `"something in the dark"`), `iron_blade` (kind `"item"`, salience `50`, uuid `None`, name `"an iron blade"`, attrs `{"damage": 4}`, labels `("Item","Weapon")`).
- **`EntityDoc`** (`engine/src/memento/state/repository.py`): `{uuid, name, kind, labels: list[str], location_uuid: str|None, attrs: dict, is_dead: bool}`. **`ItemDoc`**: `{uuid, name, kind:"item", labels, owner_uuid: str|None, location_uuid: str|None, attrs}`.
- **`InMemoryStateRepository`** (`engine/src/memento/state/in_memory.py`): `seed_entity(doc)` / `seed_item(doc)` are **sync**; `get_entity(uuid)`, `get_entities_at_location(loc)` (excludes items), `get_items_at_location(loc)` (floor items: `owner_uuid is None`), and **`set_attr(uuid, field, value)`** are **async**. `set_attr` writes `attrs[field]` (except `field=="is_dead"` → top-level), returns the updated doc. `seed_item` stores the doc in both `_items` and `_entities` (same object), so `set_attr` on an item uuid works.

## File Structure

- `engine/src/memento/opening/reveal.py` (**new**) — the whole deliverable: `RevealDelta` dataclass, `reveal_or_deepen`, `seed_room_ecs`, and private helpers `_view` / `_lookable_things` / `_stable_uuid`. One file, one responsibility (the reveal-state machine).
- `engine/tests/opening/test_reveal.py` (**new**) — the headless tests.

---

# Task 1 — `reveal_or_deepen`: the reveal/deepen state machine

**Files:**
- Create: `engine/src/memento/opening/reveal.py`
- Test: `engine/tests/opening/test_reveal.py`

**Interfaces:**
- Produces: `RevealDelta(kind: str, entity: dict|None, depth: int)` where `kind ∈ {"revealed","deepened","exhausted"}` and `entity` is `{uuid, name, kind, labels}` (None when exhausted). `async reveal_or_deepen(repo, location_uuid, *, max_depth=DEFAULT_MAX_DEPTH=3) -> RevealDelta`. Consumed by Task 2's end-to-end test and by Plan 2's gateway `mm_look` tool.

- [ ] **Step 1 — write the failing tests** (`engine/tests/opening/test_reveal.py`). `asyncio_mode="auto"` → no decorator needed:
```python
from memento.opening.reveal import reveal_or_deepen
from memento.state.in_memory import InMemoryStateRepository


def _seed_thing(repo, uuid, name, salience, *, kind="character", reveal_level=0):
    repo.seed_entity(
        {
            "uuid": uuid,
            "name": name,
            "kind": kind,
            "labels": ["Character"],
            "location_uuid": "loc-1",
            "attrs": {"salience": salience, "reveal_level": reveal_level},
            "is_dead": False,
        }
    )


async def test_reveals_most_salient_first():
    repo = InMemoryStateRepository()
    _seed_thing(repo, "a", "low", 50)
    _seed_thing(repo, "b", "high", 1000)
    _seed_thing(repo, "c", "mid", 100)
    d = await reveal_or_deepen(repo, "loc-1")
    assert d.kind == "revealed" and d.entity["name"] == "high" and d.depth == 1
    assert (await repo.get_entity("b"))["attrs"]["reveal_level"] == 1


async def test_reveals_in_descending_salience_order():
    repo = InMemoryStateRepository()
    _seed_thing(repo, "a", "low", 50)
    _seed_thing(repo, "b", "high", 1000)
    _seed_thing(repo, "c", "mid", 100)
    names = [(await reveal_or_deepen(repo, "loc-1")).entity["name"] for _ in range(3)]
    assert names == ["high", "mid", "low"]


async def test_deepens_after_all_revealed():
    repo = InMemoryStateRepository()
    _seed_thing(repo, "a", "low", 50)
    _seed_thing(repo, "b", "high", 1000)
    for _ in range(2):
        await reveal_or_deepen(repo, "loc-1")
    d = await reveal_or_deepen(repo, "loc-1")
    assert d.kind == "deepened" and d.entity["name"] == "high" and d.depth == 2
    assert (await repo.get_entity("b"))["attrs"]["reveal_level"] == 2


async def test_exhausts_at_max_depth():
    repo = InMemoryStateRepository()
    _seed_thing(repo, "a", "only", 100)
    r = await reveal_or_deepen(repo, "loc-1", max_depth=2)  # reveal -> 1
    d = await reveal_or_deepen(repo, "loc-1", max_depth=2)  # deepen -> 2
    x = await reveal_or_deepen(repo, "loc-1", max_depth=2)  # exhausted
    assert r.kind == "revealed" and d.kind == "deepened" and x.kind == "exhausted"
    assert x.entity is None


async def test_ignores_things_without_reveal_component():
    repo = InMemoryStateRepository()
    repo.seed_entity(
        {
            "uuid": "room",
            "name": "the room",
            "kind": "location",
            "labels": ["Location"],
            "location_uuid": "loc-1",
            "attrs": {},  # no reveal_level -> not a candidate
            "is_dead": False,
        }
    )
    _seed_thing(repo, "a", "thing", 100)
    # max_depth=1 so a revealed thing isn't deepenable: the 2nd look is only
    # "exhausted" if the location ("room") was correctly excluded as a candidate.
    d = await reveal_or_deepen(repo, "loc-1", max_depth=1)
    assert d.entity["name"] == "thing"
    assert (await reveal_or_deepen(repo, "loc-1", max_depth=1)).kind == "exhausted"


async def test_reveal_level_is_monotonic_and_capped():
    repo = InMemoryStateRepository()
    _seed_thing(repo, "a", "only", 100)
    levels = []
    for _ in range(5):
        await reveal_or_deepen(repo, "loc-1", max_depth=3)
        levels.append((await repo.get_entity("a"))["attrs"]["reveal_level"])
    assert levels == [1, 2, 3, 3, 3]
```

- [ ] **Step 2 — run, verify they fail:**
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest engine/tests/opening/test_reveal.py -q
```
Expected: FAIL with `ModuleNotFoundError: No module named 'memento.opening.reveal'`.

- [ ] **Step 3 — implement the state machine** (`engine/src/memento/opening/reveal.py`):
```python
"""Accretive room reveal-state — the "look adds detail" ECS state machine.

A room's lookable things carry a ``reveal_level`` component in ``attrs``
(0 = latent / unseen, 1 = surfaced, 2+ = deepened) plus a ``salience`` for
ordering.  ``reveal_or_deepen`` advances that state one step per call: it
REVEALS the next most-salient unseen thing, and once the room is fully
surfaced it DEEPENS already-seen things (shallowest first).  Re-looking
accretes; it never resets.

The state lives as components on the entity docs in the StateRepository, so
this is the first real ECS effect (the future ``mm_look``'s effect).  Only the
async StateRepository protocol is used (``get_*_at_location`` + ``set_attr``),
so it is backend-agnostic (in-memory or EventSourced/KG) and headless-testable.
"""

from __future__ import annotations

import hashlib
import inspect
from dataclasses import dataclass
from typing import Any

from memento.opening.seed_types import SeedRoom

DEFAULT_MAX_DEPTH: int = 3


@dataclass(frozen=True)
class RevealDelta:
    """What one look changed.

    kind   : "revealed" | "deepened" | "exhausted"
    entity : {uuid, name, kind, labels} view of the changed thing (None if exhausted)
    depth  : the new reveal_level (0 when exhausted)
    """

    kind: str
    entity: dict[str, Any] | None
    depth: int


def _view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "uuid": doc["uuid"],
        "name": doc["name"],
        "kind": doc["kind"],
        "labels": list(doc.get("labels", [])),
    }


async def _lookable_things(repo: Any, location_uuid: str) -> list[dict[str, Any]]:
    """Reveal-tracked things at the location — characters/threats AND items.

    ``get_entities_at_location`` excludes ``kind=="item"``, so items are
    gathered separately and unioned.  A thing is reveal-tracked iff it carries
    a ``reveal_level`` component.
    """
    entities = await repo.get_entities_at_location(location_uuid)
    items = await repo.get_items_at_location(location_uuid)
    things = list(entities) + list(items)
    return [t for t in things if "reveal_level" in t.get("attrs", {})]


async def reveal_or_deepen(
    repo: Any, location_uuid: str, *, max_depth: int = DEFAULT_MAX_DEPTH
) -> RevealDelta:
    """Advance the room's reveal-state by one look.

    REVEAL the next most-salient unseen thing; else DEEPEN the shallowest
    revealed thing (ties -> higher salience -> uuid); else "exhausted".
    ``reveal_level`` is mutated monotonically (only increases, capped at
    ``max_depth``).
    """
    things = await _lookable_things(repo, location_uuid)

    latent = [t for t in things if t["attrs"].get("reveal_level", 0) == 0]
    if latent:
        nxt = max(latent, key=lambda e: (e["attrs"].get("salience", 0), e["uuid"]))
        await repo.set_attr(nxt["uuid"], "reveal_level", 1)
        return RevealDelta(kind="revealed", entity=_view(nxt), depth=1)

    deepenable = [t for t in things if 0 < t["attrs"].get("reveal_level", 0) < max_depth]
    if deepenable:
        nxt = min(
            deepenable,
            key=lambda e: (
                e["attrs"]["reveal_level"],
                -e["attrs"].get("salience", 0),
                e["uuid"],
            ),
        )
        new_depth = nxt["attrs"]["reveal_level"] + 1
        await repo.set_attr(nxt["uuid"], "reveal_level", new_depth)
        return RevealDelta(kind="deepened", entity=_view(nxt), depth=new_depth)

    return RevealDelta(kind="exhausted", entity=None, depth=0)


def _stable_uuid(location_id: str, key: str) -> str:
    """Deterministic 24-hex (ObjectId-shaped) id for a uuid-less seed fact."""
    return hashlib.sha1(f"{location_id}:{key}".encode()).hexdigest()[:24]


async def seed_room_ecs(repo: Any, room: SeedRoom) -> None:
    """Seed a SeedRoom's facts as ECS entities carrying reveal components
    (``reveal_level=0``, ``salience``).  Item-kind facts become floor items;
    others become entities.  ``seed_entity``/``seed_item`` may be sync
    (in-memory) or async (EventSourced) — both are handled.
    """
    for fact in room.facts:
        uuid = fact.uuid or _stable_uuid(room.location_id, fact.key)
        attrs = {**dict(fact.attrs), "salience": fact.salience, "reveal_level": 0}
        if fact.kind == "item":
            res = repo.seed_item(
                {
                    "uuid": uuid,
                    "name": fact.name,
                    "kind": "item",
                    "labels": list(fact.labels),
                    "owner_uuid": None,
                    "location_uuid": room.location_id,
                    "attrs": attrs,
                }
            )
        else:
            res = repo.seed_entity(
                {
                    "uuid": uuid,
                    "name": fact.name,
                    "kind": fact.kind,
                    "labels": list(fact.labels),
                    "location_uuid": room.location_id,
                    "attrs": attrs,
                    "is_dead": False,
                }
            )
        if inspect.isawaitable(res):
            await res
```
*(`seed_room_ecs` is defined here too — Task 2 tests it. It's in the same file because it's part of the same reveal-state responsibility and the file is small.)*

- [ ] **Step 4 — run, verify they pass:**
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest engine/tests/opening/test_reveal.py -q
```
Expected: 6 passed.

- [ ] **Step 5 — ruff-format + commit:**
```bash
python3.12 -m ruff format engine/src/memento/opening/reveal.py engine/tests/opening/test_reveal.py
git add engine/src/memento/opening/reveal.py engine/tests/opening/test_reveal.py
git commit -m "feat(opening): reveal/deepen ECS room-state machine

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Task 2 — `seed_room_ecs` end-to-end with the Deep Roads seed

**Files:**
- Modify: `engine/tests/opening/test_reveal.py` (add the seed + deep-roads e2e tests)
- (`seed_room_ecs` was already implemented in Task 1's `reveal.py` — this task proves it against the real authored seed.)

**Interfaces:**
- Consumes: `seed_room_ecs(repo, room)` + `reveal_or_deepen` (Task 1); `deep_roads_seed()` / `LOC_DEEP_ROADS` (existing).
- Produces: the proof that the authored Deep Roads room, seeded as ECS entities, reveals in the authored salience order (adventurer → threat → blade), including the item fact.

- [ ] **Step 1 — add the failing tests** (append to `engine/tests/opening/test_reveal.py`):
```python
from memento.opening.deep_roads import LOC_DEEP_ROADS, deep_roads_seed
from memento.opening.reveal import seed_room_ecs


async def test_seed_room_ecs_marks_facts_latent_with_salience():
    repo = InMemoryStateRepository()
    await seed_room_ecs(repo, deep_roads_seed())
    ents = await repo.get_entities_at_location(LOC_DEEP_ROADS)
    items = await repo.get_items_at_location(LOC_DEEP_ROADS)
    by_name = {t["name"]: t for t in (list(ents) + list(items))}
    assert by_name["a dying adventurer"]["attrs"]["reveal_level"] == 0
    assert by_name["a dying adventurer"]["attrs"]["salience"] == 1_000_000
    # the iron blade is an item, seeded as a floor item, still reveal-tracked
    assert by_name["an iron blade"]["kind"] == "item"
    assert by_name["an iron blade"]["attrs"]["reveal_level"] == 0
    assert by_name["an iron blade"]["attrs"]["damage"] == 4  # original attrs preserved


async def test_deep_roads_reveals_in_authored_order_then_deepens():
    repo = InMemoryStateRepository()
    await seed_room_ecs(repo, deep_roads_seed())
    names = [
        (await reveal_or_deepen(repo, LOC_DEEP_ROADS)).entity["name"] for _ in range(3)
    ]
    assert names == ["a dying adventurer", "something in the dark", "an iron blade"]
    d = await reveal_or_deepen(repo, LOC_DEEP_ROADS)  # 4th look -> deepen most salient
    assert d.kind == "deepened" and d.entity["name"] == "a dying adventurer"
```

- [ ] **Step 2 — run, verify they fail then pass.** They fail first only if Task 1 weren't done; since `seed_room_ecs` exists, run and confirm green:
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest engine/tests/opening/test_reveal.py -q
```
Expected: 8 passed (6 from Task 1 + 2 here). *(If `test_seed_room_ecs_marks_facts_latent_with_salience` fails on `damage`, confirm `seed_room_ecs` spreads `**dict(fact.attrs)` before the reveal fields — it must preserve the fact's authored attrs.)*

- [ ] **Step 3 — full opening-suite regression** (seeding/reveal didn't disturb the existing opening tests):
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest engine/tests/opening -q
```
Expected: green (the existing opening tests + the new reveal tests).

- [ ] **Step 4 — commit:**
```bash
git add engine/tests/opening/test_reveal.py
git commit -m "test(opening): reveal/deepen proven on the authored Deep Roads seed

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Verification (end-to-end)

1. **State machine (Task 1):** `reveal_or_deepen` reveals most-salient-first, in descending salience order, deepens after all revealed, exhausts at `max_depth`, ignores things without a `reveal_level` component, and keeps `reveal_level` monotonic/capped. 6 tests.
2. **Authored seed (Task 2):** `seed_room_ecs` seeds the Deep Roads facts (incl. the iron-blade *item*) as reveal-tracked ECS entities at `reveal_level=0` preserving authored attrs; the room then reveals adventurer → threat → blade, then deepens the most salient. 2 tests.
3. **No regression:** the existing `engine/tests/opening` suite stays green.
4. **Backend-agnostic:** `reveal_or_deepen` touches only `get_entities_at_location` / `get_items_at_location` / `set_attr` — the same protocol the EventSourced/KG repo implements, so Plan 2 can run it against `app.state.cxn_repo` unchanged.

## What this plan deliberately does NOT do (later plans)

- **Plan 2:** the gateway-hosted `mm_look` MCP tool that calls `reveal_or_deepen` + broadcasts the *incremental* draw delta (client adds the new glyph) + returns the delta for narration; registration in `cxn_tools.py`; the EventSourced seeding of the room into `app.state.cxn_repo`.
- **Plan 3:** player-as-persona (`SelfDto`), `mm_look` in the agent-runtime manifest + a kit, `SceneTurnResponse.fired_cxns`, and the `cxn_fired` observability (log + WS event + "◇ caught: LOOK" client beat) — the cross-repo (bonfires-ai-core) work.
- **Plan 4:** the cinematic intro (epigraph fade + name box), retiring the legacy overlay, and client rendering of the reveal/deepen narration.
