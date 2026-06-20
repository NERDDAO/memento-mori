# Memento-Mori cxn Control System — Prep & Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get the memento-mori repo to a shareable state with clear threads — a new dev clones, reads one START-HERE doc, and within an hour knows what's being built, what's reusable (with verified signatures), what's legacy/fallback, and which thread is theirs, with a stub-backed seam enabling independent parallel work.

**Architecture:** Lay the foundation (importable-but-empty `cxn`/`state`/`memory` packages + an async test toolchain), land the one shared seam every component imports (`cxn/types.py`), then produce the onboarding docs (reuse inventory, START-HERE + legacy banners, decommission inventory, thread sheet) that resolve every open spec caveat into a verified fact or an owned thread. No behavior change to the legacy CrewAI/Delve stack — it is labeled, not removed.

**Tech Stack:** Python 3.10+ (`engine/`), pytest + pytest-asyncio, httpx, motor, mongomock-motor, TypedDict-based DTOs. Companion spec: `docs/superpowers/specs/2026-06-19-mm-construction-control-system-design.md`.

## Global Constraints

- **Engine Day-1 cut line is UUID-args-only.** Agents pass entity UUIDs as MCP tool args; no text comprehension, no LLM, no NLP in any test, zero *new* graph-memory endpoints required by the skeleton. (spec §2.2, §5, §7.3, §8.4)
- **Always use UUIDs, never names** for lookups/comparisons/matching (repo convention, `CLAUDE.md`).
- **Types only in Track A** — `cxn/types.py` carries DTOs, zero logic.
- **No deletion of the legacy stack** — `crews/`, `flows/`, `round_controller.py`, `tools/kg.py` are labeled (banner / inventory), never removed in this plan.
- **Docs cross-link** — START-HERE → reuse-inventory → thread-sheet form a single navigable path.
- **The comprehend reframe is authoritative:** the graph-memory *route* does not exist, but the comprehension *capability* exists and is exercised in `memory_kernel` (`FCGBridgeClient.comprehend(_scoped)`, `_comprehend_loaded_grammar`, and `runtime/kernel.py` search-comprehends-query). Docs must reflect "expose, not build." (spec §5.3, §5.6 — already reframed)

---

### Task 1: Part 0 — Package skeleton + async test toolchain

**Files:**
- Create: `engine/src/memento/cxn/__init__.py`, `engine/src/memento/state/__init__.py`, `engine/src/memento/memory/__init__.py`
- Create: `engine/tests/unit/__init__.py`, `engine/tests/integration/__init__.py`, `engine/tests/fixtures.py` (placeholder)
- Modify: `engine/pyproject.toml` (dev extras + pytest config)
- Test: `engine/tests/unit/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: importable empty packages `memento.cxn`, `memento.state`, `memento.memory`; a working `pytest -q` with `asyncio_mode = "auto"`; `engine/tests/fixtures.py` (empty placeholder, filled in Task 2).

- [ ] **Step 1: Write the failing async smoke test**

```python
# engine/tests/unit/test_smoke.py
"""Proves the async test toolchain is wired (pytest-asyncio, asyncio_mode=auto)."""
import memento.cxn  # noqa: F401
import memento.state  # noqa: F401
import memento.memory  # noqa: F401


async def test_async_smoke():
    """A bare async test that runs only if asyncio_mode='auto' is configured."""
    assert True
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd engine && python -m pytest tests/unit/test_smoke.py -q`
Expected: collection/import error (`ModuleNotFoundError: memento.cxn`) OR `async def functions are not natively supported` — proving the toolchain is not yet in place.

- [ ] **Step 3: Create the empty packages**

Each `__init__.py` is empty except a one-line module docstring:
```python
"""Construction-based control system — cxn layer (see docs/superpowers/specs/2026-06-19-mm-construction-control-system-design.md)."""
```
(`state/__init__.py` → "state layer", `memory/__init__.py` → "memory/kernel-client layer".) `engine/tests/unit/__init__.py` and `engine/tests/integration/__init__.py` are empty. `engine/tests/fixtures.py` is a placeholder:
```python
"""Shared test fixtures (UUIDs, entity docs) for the cxn control system. Filled in Task 2."""
```

- [ ] **Step 4: Add the test toolchain to `engine/pyproject.toml`**

Extend the `dev` optional-dependency list (currently `["pytest>=7.0"]`) to:
```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "motor>=3.4",
    "mongomock-motor>=0.0.29",
]
```
Add a pytest config block (append to `pyproject.toml`):
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 5: Install and run the smoke test to confirm it passes**

Run: `cd engine && pip install -e '.[dev]' && python -m pytest tests/unit/test_smoke.py -q`
Expected: 1 passed. Then `python -m pytest --collect-only -q` succeeds with no collection errors.

- [ ] **Step 6: Commit**

```bash
git add engine/src/memento/cxn engine/src/memento/state engine/src/memento/memory engine/tests/unit engine/tests/integration engine/tests/fixtures.py engine/tests/unit/test_smoke.py engine/pyproject.toml
git commit -m "feat(cxn): Part 0 — package skeleton + async test toolchain"
```

---

### Task 2: Part 0 — Doc placeholders, env slice, kernel smoke script

**Files:**
- Create: `docs/START-HERE.md`, `docs/cxn/reuse-inventory.md`, `docs/cxn/thread-sheet.md`, `docs/cxn/gm-contract.md` (headed placeholders)
- Create: `scripts/kernel_smoke.py`
- Modify: `example.env` (cxn-slice vars), `engine/tests/fixtures.py` (agreed fixture UUIDs)

**Interfaces:**
- Consumes: the packages from Task 1.
- Produces: four headed doc placeholders (filled by Tasks 4–7); `scripts/kernel_smoke.py` (importable, runnable); fixture UUID constants in `engine/tests/fixtures.py` that Track A and later tests import.

- [ ] **Step 1: Write the failing fixtures import test**

Append to `engine/tests/unit/test_smoke.py`:
```python
def test_fixtures_uuids_present():
    from tests import fixtures
    for name in ("KAEL", "GOBLIN", "IRON_SWORD", "ASH_MARKET", "RIVER_GATE"):
        val = getattr(fixtures, name)
        assert isinstance(val, str) and len(val) == 24  # 24-hex ObjectId shape
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd engine && python -m pytest tests/unit/test_smoke.py::test_fixtures_uuids_present -q`
Expected: FAIL — `AttributeError: module 'tests.fixtures' has no attribute 'KAEL'`.

- [ ] **Step 3: Fill `engine/tests/fixtures.py` with agreed fixture UUIDs**

```python
"""Shared test fixtures (UUIDs, entity docs) for the cxn control system.

UUIDs are valid 24-hex ObjectId shapes so they round-trip through the same
id validation graph-memory uses for bonfire/actor ids.
"""

# Characters
KAEL = "6650000000000000000000a1"        # player-agent
GOBLIN = "6650000000000000000000a2"      # NPC patient

# Items
IRON_SWORD = "6650000000000000000000b1"  # instrument (Weapon, damage attr)

# Locations
ASH_MARKET = "6650000000000000000000c1"  # starting room
RIVER_GATE = "6650000000000000000000c2"  # MOVE destination (exit of ASH_MARKET)

BONFIRE_ID = "6650000000000000000000f1"  # mm-world-v1 namespace
```

- [ ] **Step 4: Run the fixtures test to confirm it passes**

Run: `cd engine && python -m pytest tests/unit/test_smoke.py -q`
Expected: 2 passed.

- [ ] **Step 5: Create the four headed doc placeholders**

Each file gets a heading + a one-line "filled by Task N / Track X" note and a status banner `> **Status:** placeholder — see plan task.` Content:
- `docs/START-HERE.md` → `# Memento-Mori — Start Here (cxn control system)` (filled by Task 5 / Track D)
- `docs/cxn/reuse-inventory.md` → `# cxn Reuse Inventory` (filled by Task 4 / Track B)
- `docs/cxn/thread-sheet.md` → `# cxn Thread / Ownership Sheet` (filled by Task 7 / Track F)
- `docs/cxn/gm-contract.md` → `# graph-memory Contract & Decommission Inventory` (filled by Tasks 6 / Track C+E)

- [ ] **Step 6: Add the cxn env slice to `example.env`**

Append a documented block (match existing `example.env` comment style):
```bash
# --- cxn control system (Day-1 skeleton) ---
KERNEL_BASE_URL=http://localhost:8001   # graph-memory service base URL
GM_INTERNAL_TOKEN=                       # shared internal bearer for kernel/index|search
MONGO_URI=mongodb://localhost:27017      # transactional StateRepository (optional Day 1; default is in-memory)
MONGO_DB=memento                         # state db name
CHAIN_ENABLED=false                      # NoopChainMirror when false
```

- [ ] **Step 7: Create `scripts/kernel_smoke.py`**

A standalone, dependency-light (`httpx`) script: reads `KERNEL_BASE_URL`/`GM_INTERNAL_TOKEN` from env, POSTs a tiny `kernel/index` for a fixture bonfire then a `kernel/search`, prints the two status codes, exits non-zero on any non-2xx. Guard the network calls behind `if __name__ == "__main__":` so `import scripts.kernel_smoke` (or `py_compile`) stays side-effect-free. Include a module docstring documenting the one-command usage.

- [ ] **Step 8: Verify the script imports cleanly and collection still passes**

Run: `cd engine && python -m pytest --collect-only -q` → no errors.
Run: `python -m py_compile scripts/kernel_smoke.py` → exit 0.

- [ ] **Step 9: Commit**

```bash
git add docs/START-HERE.md docs/cxn engine/tests/fixtures.py engine/tests/unit/test_smoke.py example.env scripts/kernel_smoke.py
git commit -m "feat(cxn): Part 0 — doc placeholders, env slice, fixtures, kernel smoke script"
```

---

### Task 3: Track A — Shared seam `cxn/types.py`

**Files:**
- Create: `engine/src/memento/cxn/types.py`
- Test: `engine/tests/unit/test_types.py`

**Interfaces:**
- Consumes: nothing (pure types).
- Produces: the DTO module every other component imports — `RoleTag`, `SemanticFrame`, `StatePrimitive`, `SelectionRestriction`, `CxnDef`, `MatchedCxn`, `StateDelta`, `EpisodeIn`, `ExecutionContext`, `ConstructionError`, `Constructicon` (Protocol). Exact field sets are pinned by spec §3.2, §3.3, §4.1, §5.4, §8.2 — copy verbatim, do not invent fields.

- [ ] **Step 1: Write the failing import/shape test**

```python
# engine/tests/unit/test_types.py
def test_types_importable_and_shaped():
    from memento.cxn import types as t
    # TypedDicts expose __annotations__ with the spec field sets
    assert set(t.StatePrimitive.__annotations__) == {"substrate", "op", "args", "if_condition"}
    assert set(t.SemanticFrame.__annotations__) == {"predicate", "roles", "confidence", "raw_text"}
    assert set(t.CxnDef.__annotations__) == {
        "name", "predicate", "mcp_tool_name", "description", "semantic_roles",
        "restrictions", "guards", "chain_mirror", "effect_template", "episode_template",
    }
    assert set(t.MatchedCxn.__annotations__) == {"cxn", "bound_roles"}
    assert set(t.StateDelta.__annotations__) == {"op", "target_uuid", "field", "before", "after"}
    assert issubclass(t.ConstructionError, Exception)


def test_constructicon_is_protocol():
    from memento.cxn import types as t
    assert hasattr(t.Constructicon, "match") and hasattr(t.Constructicon, "all_cxns")
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd engine && python -m pytest tests/unit/test_types.py -q`
Expected: FAIL — `ModuleNotFoundError` / `cannot import name 'types'`.

- [ ] **Step 3: Write `engine/src/memento/cxn/types.py`**

Transcribe the DTOs from spec §3.2 / §4.1 / §8.2 verbatim. `StatePrimitive`, `RoleTag`, `SemanticFrame`, `SelectionRestriction`, `CxnDef`, `MatchedCxn`, `Constructicon` (Protocol) are given in the spec exactly. Add the three the spec names but does not inline — pin them to their spec descriptions:
```python
class StateDelta(TypedDict):
    op: str
    target_uuid: str
    field: str
    before: Any
    after: Any

class EpisodeIn(TypedDict):
    bonfire_id: str
    actor_id: str
    content: str
    metadata: dict[str, Any]

class ExecutionContext(TypedDict):
    bound_roles: dict[str, str]       # role label → UUID
    entities: dict[str, dict]         # UUID → loaded entity doc
    transients: dict[str, Any]        # computed_hp, damage, etc.
    world_tick: int

class ConstructionError(Exception):
    """Typed failure from binding/guard/transactional phases (see spec §7.4 prefixes)."""
```
Use `from __future__ import annotations` and `from typing import Any, Literal, Protocol, TypedDict`.

- [ ] **Step 4: Run the test to confirm it passes**

Run: `cd engine && python -m pytest tests/unit/test_types.py -q`
Expected: 2 passed.

- [ ] **Step 5: Verify the public import path**

Run: `cd engine && python -c "import memento.cxn.types; print('ok')"`
Expected: `ok`.

- [ ] **Step 6: Commit**

```bash
git add engine/src/memento/cxn/types.py engine/tests/unit/test_types.py
git commit -m "feat(cxn): Track A — shared DTO seam cxn/types.py"
```

---

### Task 4: Track B — Reuse inventory (verified signatures)

**Files:**
- Modify: `docs/cxn/reuse-inventory.md` (fill the placeholder)

**Interfaces:**
- Consumes: nothing (documentation against current code).
- Produces: the verified-signature inventory that Tasks 5 and 7 cross-link.

This is a documentation task. There is no unit test; verification is a content checklist (Step 4). The implementer MUST open each named file and record the **actual current** signature and `file:line` — not the spec's claim.

- [ ] **Step 1: Verify each reuse target against current code**

Read and record actual signatures + `file:line` for:
- `engine/src/memento/tools/chain.py` — `record_death(...)` (confirm it takes **no `killer_id`**), `transfer_item(...)` (confirm arity), `is_enabled()`.
- `engine/src/memento/tools/mechanics.py` — `calculate_damage`, `roll_skill_check`: confirm `@tool`-decorated, string-arg, prose-returning, `random.randint` usage → label **DON'T REUSE**, replaced by `cxn/arithmetic.py` (spec §3.5).
- `engine/src/memento/tools/tool_labels.py` — the `KITS` tables and which legacy tool names sit in the `NPC`/`Player` kits (spec §7.5 capability-kit edit target).
- `engine/src/memento/models/state_update.py` — `StateUpdate` and its event models.
- `gateway/src/gateway/mcp_server.py` — `_check_tool_access`, `broadcast_tool_event`, and the `FastMCP`/`build_mcp_app` registration factory.

- [ ] **Step 2: Write the inventory**

For each target: a row/section with **what the spec says to reuse**, the **verified current signature**, the **`file:line`**, and **how the cxn layer consumes it** (which component C1–C6, which spec section). Flag every signature mismatch between spec and code as a callout (e.g. if `transfer_item` arity differs from the §6.2 unified signature, say so explicitly). Each reuse entry must let a reader jump straight to the code.

- [ ] **Step 3: Cross-link**

Add a top-of-doc backlink to `docs/START-HERE.md` and a forward link to `docs/cxn/thread-sheet.md`. Remove the placeholder status banner.

- [ ] **Step 4: Verify content completeness**

Confirm: every file named in Step 1 has a verified `file:line`; no signature is quoted from the spec without confirming against code; the `record_death` no-`killer_id` and `mechanics.py` DON'T-REUSE facts are present.

Run: `grep -n "file:line\|chain.py\|mechanics.py\|tool_labels.py\|state_update.py\|mcp_server.py" docs/cxn/reuse-inventory.md` → all five files referenced.

- [ ] **Step 5: Commit**

```bash
git add docs/cxn/reuse-inventory.md
git commit -m "docs(cxn): Track B — reuse inventory with verified signatures"
```

---

### Task 5: Track D — START-HERE + legacy banners

**Files:**
- Modify: `docs/START-HERE.md` (fill the placeholder)
- Modify: `engine/src/memento/crews/__init__.py`, `engine/src/memento/flows/__init__.py`, `engine/src/memento/round_controller.py` (one-line LEGACY banner each — confirm exact paths exist first; if a target is a directory without `__init__.py`, banner the package's primary module)

**Interfaces:**
- Consumes: the reuse inventory (Task 4) and thread sheet (Task 7 — forward link is fine; Task 7 lands after, link is one-directional from START-HERE).
- Produces: the single onboarding entry point.

This is a documentation + comment task. Verification is a content checklist + a no-behavior-change check.

- [ ] **Step 1: Write `docs/START-HERE.md`**

Source the "what's being built / what's reusable / what's legacy" map from spec §9. Sections: (1) one-paragraph what-this-is; (2) the 30-second setup check (`pip install -e 'engine[dev]' && pytest --collect-only`); (3) a legibility map — links to the spec, reuse-inventory, thread-sheet, gm-contract; (4) "which thread is mine" → point at the thread sheet. Keep it skimmable in under 5 minutes.

- [ ] **Step 2: Add LEGACY banners**

A single comment line at the top of each legacy module, e.g.:
```python
# LEGACY (cxn control system): replaced for the 3 skeleton actions (MOVE/ATTACK/TAKE),
# retained as fallback for all other turns. See spec §9.1.
```
No code change beyond the comment. Confirm each target path exists before editing; record any that don't in the commit body.

- [ ] **Step 3: Verify no behavior change + links resolve**

Run: `cd engine && python -m pytest -q` → still green (banners are comments).
Run: `python -c "import memento.crews, memento.flows, memento.round_controller"` → imports clean (or note which module path is correct if a name differs).
Confirm START-HERE links to spec, reuse-inventory, thread-sheet, gm-contract.

- [ ] **Step 4: Commit**

```bash
git add docs/START-HERE.md engine/src/memento/crews engine/src/memento/flows engine/src/memento/round_controller.py
git commit -m "docs(cxn): Track D — START-HERE onboarding + legacy banners"
```

---

### Task 6: Track E — Decommission clarity (kg.py inventory)

**Files:**
- Modify: `docs/cxn/gm-contract.md` (add the decommission inventory section)

**Interfaces:**
- Consumes: nothing (documentation against current code).
- Produces: the labeled `tools/kg.py` call-site inventory; START-HERE links to it.

- [ ] **Step 1: Inventory the `tools/kg.py` Delve call-sites**

Grep for importers/callers of `engine/src/memento/tools/kg.py`; for each call-site record `file:line` and label it **replaced-for-3-actions** (MOVE/ATTACK/TAKE now go through cxn) vs **fallback-for-rest** (other turns still use it). Confirm Delve itself is archived (note where).

Run: `grep -rn "tools.kg\|from .kg\|import kg\|kg\." engine/src/memento --include='*.py'` (refine as needed).

- [ ] **Step 2: Write the inventory section**

Add a `## Decommission inventory (tools/kg.py)` section to `docs/cxn/gm-contract.md` with the labeled call-site table and the Delve-archived confirmation.

- [ ] **Step 3: Verify the env slice boots import + collect**

Confirm the Task-2 `example.env` cxn slice does not break engine import:
Run: `cd engine && python -c "import memento" && python -m pytest --collect-only -q` → clean.

- [ ] **Step 4: Commit**

```bash
git add docs/cxn/gm-contract.md
git commit -m "docs(cxn): Track E — kg.py decommission inventory"
```

---

### Task 7: Track F — Thread / ownership sheet

**Files:**
- Modify: `docs/cxn/thread-sheet.md` (fill the placeholder)

**Interfaces:**
- Consumes: the reuse inventory (Task 4) and the gm-contract (Tasks 6 + Track C). Lands last because owners need B/C's verified facts.
- Produces: the page you walk the team through — one card per thread.

- [ ] **Step 1: Write a thread card per component**

Operationalize spec §8.1 into cards for **C1 StateRepository, C2 MemoryClient, C3 Constructicon, C4 EffectExecutor, C6 McpToolBridge** plus **C5/Milestone-2 Comprehension** and **graph-memory comprehend route** (Track C). Each card: owner (TBD), files, depends-on, stub, acceptance test, and a pointer into the Track-B reuse inventory. The C5 + comprehend cards must reflect the reframe — "expose the existing capability," with pointers to `FCGBridgeClient.comprehend(_scoped)` / `_comprehend_loaded_grammar` and the gm-contract.

- [ ] **Step 2: Cross-link and de-placeholder**

Backlink to START-HERE; each card's reuse pointer links into `docs/cxn/reuse-inventory.md`. Remove the placeholder banner.

- [ ] **Step 3: Verify the onboarding path**

Confirm the chain resolves: START-HERE → reuse-inventory → thread-sheet, and each thread card names a startable first step. Confirm all seven threads (C1–C6 minus C5-as-M2, plus comprehend) are present.

Run: `grep -c "## " docs/cxn/thread-sheet.md` → ≥ 7 cards.

- [ ] **Step 4: Commit**

```bash
git add docs/cxn/thread-sheet.md
git commit -m "docs(cxn): Track F — thread / ownership sheet"
```

---

## Appendix — Track C (cross-repo, NOT an SDD task on this branch)

Track C lives in **bonfires-ai-core** (`services/graph-memory`), is a separate PR to **`staging`**, and runs independently of this memento-mori branch. It is recorded here so the thread sheet (Task 7) can point at it, but it is executed in its own repo/branch with its own review.

**Deliverable 1 (verify):** run `scripts/kernel_smoke.py` against the live graph-memory service; record actual `kernel/index` + `kernel/search` request/response shapes and the internal-token auth into `docs/cxn/gm-contract.md`.

**Deliverable 2 (expose comprehend):** add a `kernel/comprehend` route over the existing capability:
- `kernel_dto.py` — `KernelComprehendRequest`/`Response` + `SemanticFrameDTO` (spec §5.3).
- `kernel_service.py` — `comprehend()` delegating to the backend protocol.
- `kernel_controller.py` — DTO mapping.
- `kernel_routes.py` — `@router.post("/comprehend")` (mirrors `/index`/`/search`).
- `src/adapters/memory_kernel/client.py` — `comprehend()`: local → `_comprehend_loaded_grammar(...)`; remote → `FCGBridgeClient.comprehend_scoped(...)`; map `(meanings, diagnostics.activated_cxns)` → frame.
- **Smoke:** a live `comprehend("attack the goblin")` returning `predicate` + `activated_cxns`. Game-grammar authoring is explicitly out of prep scope (the substantive Milestone-2 task).

Repo rules: `docs/migration/CHANGELOG.md` update + a testcontainers test, PR to `staging`.

---

## Critique → unlocked-by map

| Finding | Unlocked by |
|---|---|
| B1 (mechanics RNG/prose) | Task 4 (DON'T-REUSE note) + spec §3.5 |
| B2 (chain signatures) | Task 4 (verified `record_death`/`transfer_item`) |
| **B3 (comprehend "missing")** | Spec edit (done) + Track C (expose route over existing fn) |
| B4 (surface→UUID) | Engine Day-1 = UUID-args-only (spec); M2 thread in Task 7 |
| I8 (capability kit) | Task 4 inventory of `tool_labels.py KITS` |
| "repo entirely referential" | Tasks 1–3 (real code) + Task 5 (START-HERE + banners) |
| async tests unrunnable | Task 1 (toolchain) |

---

## Self-Review notes

- Spec coverage: Part 0 (Tasks 1–2), Track A (Task 3), Tracks B/D/E/F (Tasks 4–7), Track C (appendix, separate repo). Spec edit completed before this plan.
- Type consistency: `cxn/types.py` field sets in Task 3 match spec §3.2/§4.1/§8.2 exactly; `StateDelta`/`EpisodeIn`/`ExecutionContext` pinned to their spec descriptions (§3.3/§5.4/§8.2).
- The doc tasks (4–7) have content checklists, not unit tests, because their deliverable is prose; each still ends with a concrete grep/verification step and a commit.
