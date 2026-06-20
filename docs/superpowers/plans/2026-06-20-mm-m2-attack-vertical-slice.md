# Milestone 2 — Free-Text ATTACK Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute **Task K first** (cross-repo, in `memory_kernel`) — it pins the FCG load regime the engine pipeline depends on.

**Goal:** A player types `"attack the goblin with the iron sword"` and the turn resolves through the unchanged Day-1 `EffectExecutor` to an exact `StateDelta`, via a hand-authored FCG game grammar + an in-engine comprehend→resolve→execute pipeline.

**Architecture:** Comprehension lives behind an HTTP `ComprehensionClient` seam (graph-memory `kernel/comprehend`, shipped). A new public `MemoryKernel.author_grammar` seam bakes the ATTACK construction into a PyFCG grammar image and seeds it into the `mm-world-v1` bonfire. In-engine, `EntityResolver` turns surface spans into UUIDs and `TurnRouter` orchestrates comprehend-or-clarify, producing the same `MatchedCxn` the Day-1 executor already runs.

**Tech Stack:** Python 3.13, `httpx`, `pytest`/`pytest-asyncio` (`asyncio_mode="auto"`), FastMCP, PyFCG (memory_kernel), MongoDB-backed kernel store.

## Global Constraints

- **UUIDs are identity; names are display-only** matching keys (never identity).
- **Engine ↔ kernel is HTTP only.** Auth headers = `X-Internal-Token: <GM_INTERNAL_TOKEN>` + `X-Permission: read` (NOT `Authorization: Bearer`). No-match = `frame: null` on HTTP 200. Engine code never imports `memory_kernel`/`pyfcg`; only the deploy-time seed script does.
- **No LLM and no NLP in unit tests.** Comprehension is faked behind `ComprehensionClient`; real pyfcg runs only in CI-gated integration tests. In `memory_kernel`, pyfcg is faked via `sys.modules` injection (pattern: `tests/test_fcg_grammar_store.py:519-529`).
- **Reuse Day-1 unchanged:** `EffectExecutor` (`engine/src/memento/cxn/executor.py`), `ConstructiconRegistry`/`CONSTRUCTION_REGISTRY` (`constructicon.py`/`definitions.py`), `InMemoryStateRepository`, `types.py` DTOs, `arithmetic.py`, the executor guards, `conditions.py`, `CapturingMemoryClient`/`NoopChainMirror`.
- Constructor DI; raise domain exceptions (never `HTTPException`); pyright clean.
- `bonfire_id = "mm-world-v1"` (fixed). `actor_id ← JWT sub`.

---

## File Structure

**memory_kernel (Task K):**
- Modify: `src/memory_kernel/runtime/kernel.py` — add `author_grammar`, `ConstructionSpec`, `GrammarManifest`.
- Create: `src/memory_kernel/construction/fcg/game_grammar.py` — `build_attack_grammar()`.
- Create: `scripts/seed_game_grammar.py`.
- Create: `tests/test_author_grammar.py` (unit), `tests/integration/test_game_grammar_comprehend.py` (gated).

**memento-mori engine (Tasks 1–3):**
- Modify: `engine/src/memento/cxn/types.py` — add `FrameRole`, `ComprehendedFrame`, `TurnOutcome`, `ResolutionFailure`.
- Create: `engine/src/memento/cxn/kernel_client.py` (`ComprehensionClient`), `entity_resolver.py`, `turn_router.py`.
- Modify: `gateway/src/gateway/cxn_tools.py` — register `mm_act`.
- Create: `engine/tests/unit/test_comprehension_client.py`, `test_entity_resolver.py`, `test_turn_router.py`.

---

## Verified interfaces (reuse — do not re-derive)

```python
# engine/src/memento/cxn/types.py  (EXISTING)
class SemanticFrame(TypedDict):       # the POST-resolution object
    predicate: str
    roles: dict[str, str]             # role → entity UUID (resolved)
    confidence: float
    raw_text: str

# constructicon.py — ConstructiconRegistry.match keys ONLY on predicate:
def match(self, frame: SemanticFrame) -> MatchedCxn | None:
    for cxn in CONSTRUCTION_REGISTRY.values():
        if cxn["predicate"] == frame["predicate"]:
            return MatchedCxn(cxn=cxn, bound_roles=dict(frame["roles"]))
    return None

# executor.py — constructor + entry (agent←caller, location/instrument auto-filled):
EffectExecutor(repo: StateRepository, memory: MemoryClient, chain: ChainMirror, bonfire_id="mm-world-v1")
async def execute(self, cxn: CxnDef, caller_id: str, bindings: dict[str, str]) -> dict[str, Any]
# returns dict with ["state_deltas"], ["location"], ["events"]; raises ConstructionError on guard fail.

# state/repository.py (StateRepository Protocol) — relevant reads:
async def get_entity(uuid) -> EntityDoc | None
async def get_entities_at_location(location_uuid) -> list[EntityDoc]     # non-item entities
async def get_actor_snapshot(uuid) -> dict   # {location, inventory:[uuid], equipped:{main_hand:uuid}, ...}

# ATTACK CxnDef (definitions.py): predicate="attack", semantic_roles=["agent","patient","instrument","location"],
# guards=["agent_armed","target_damageable","same_room"], chain_mirror=True.
```

graph-memory comprehend contract (`services/graph-memory`): `POST /v1/bonfires/{bonfire_id}/kernel/comprehend`; request `{actor_id, utterance, entity_hints:[], allowed_construct_ids:[]}`; response `{bonfire_id, actor_id, utterance, frame: SemanticFrameDTO | null, diagnostics}`; `SemanticFrameDTO{predicate, confidence, roles:[{role, filler, entity_id}], applied_cxn_ids, matched, raw_meaning}`. Headers `X-Internal-Token` + `X-Permission: read`. Statuses to handle: 200 (frame may be null), 400/401/403/422/503.

memory_kernel building blocks (`construction/fcg/`, `runtime/kernel.py`): `MemoryKernel.__init__(*, store, ...)`, `self._store: MemoryKernelStorageProtocol`, default profile `"baseline"`. Build recipe template `grammar_store.probe_hashed_lemma_grammar_image` (`:1375`); `_primitive_sequence_cxn(...)` (`:2097`); `_sha256_file` (`:2430`); `write_profile_surface_rows(*, bonfire_id, profile, surface, rows) -> int` (`mongo_surface_store.py:258`); `read_grammar_items(*, bonfire_id, profile, limit, item_type=...)`. Manifest selection skips rows with empty route signature (`kernel.py:2337`); `load_from_payload` hard-requires `grammar_image_path` (`backend.py:703`); `validate_hashed_lemma_manifest` requires `cxn_supplier_mode`/`hash_mode`. Store dir from `HYPERMEM_FCG_STORE_DIR` (`/tmp` needs `HYPERMEM_FCG_ALLOW_TMP_STORE=1`). Unit-test pyfcg fake: `_FakeGrammar`/`_FakeConstruction`/`_FakeAgent` + `monkeypatch.setitem(sys.modules,"pyfcg",fake)`.

---

## Task K — `author_grammar` seam + ATTACK construction + gated comprehend proof  [memory_kernel]

**Run in `/home/at0x/Vaults/Bonfires/memory_kernel`, new branch off `feat/comprehend-utterance`.**

**Interfaces produced:**
```python
@dataclass(frozen=True)
class ConstructionSpec:
    construct_id: str        # "mm.attack.v1"
    name: str                # "attack-cxn"
    lemmas: list[str]        # ["attack", "strike", "hit"]
    predicate: str           # "attack"
    roles: list[str]         # ["agent", "patient", "instrument"]

@dataclass(frozen=True)
class GrammarManifest:
    bonfire_id: str; profile: str
    grammar_image_path: str; grammar_image_sha256: str
    construct_ids: list[str]

async def author_grammar(self, *, bonfire_id: str, constructions: list[ConstructionSpec],
                         profile: str | None = None, store_dir: str | None = None) -> GrammarManifest
```

- [ ] **Step 1 — Failing unit test for the manifest write.** `tests/test_author_grammar.py`: inject a fake pyfcg via `sys.modules` (reuse `_FakeGrammar`/`_FakeConstruction` shapes) and a fake store capturing `write_profile_surface_rows` args. Call `await kernel.author_grammar(bonfire_id="mm-world-v1", constructions=[ATTACK_SPEC], store_dir=tmp_path)`. Assert: exactly one row written with `surface=="grammar_items"`, `rows[0]["item_type"]=="fcg_manifest"`, `data["grammar_image_path"]` set, `data["grammar_image_sha256"] == sha256(image_bytes)`, `data` has non-empty `route_keys` (or `lexical_anchors`) AND `cxn_supplier_mode`/`hash_mode` keys, and the returned `GrammarManifest.construct_ids == ["mm.attack.v1"]`.
- [ ] **Step 2 — Run, expect failure** (`author_grammar` undefined). Run: `pytest tests/test_author_grammar.py -q`.
- [ ] **Step 3 — Implement `build_attack_grammar()`** in `construction/fcg/game_grammar.py`: build a `pyfcg.Grammar`, register the hashed-lemma inventory, add the ATTACK construction via `_primitive_sequence_cxn(...)` (form pole = sequence over the lemmas; meaning pole emits `("attack", "?ev")` + role edges naming `agent`/`patient`/`instrument`), apply hashed-lemma configuration + query feature types, `save_grammar_image(path)`. Return `(image_path, sha, construct_ids)`. Templates: `dog-cxn` (`scripts/pyfcg_tutorials/grammar_formalisation.py:35`), `resultative-cxn`/`demo-resultative.json` (argument structure), `probe_hashed_lemma_grammar_image` (`grammar_store.py:1375`).
- [ ] **Step 4 — Implement `author_grammar`** in `runtime/kernel.py`: resolve `profile or "baseline"`; `await asyncio.to_thread(build_attack_grammar-driver, constructions, store_dir or HYPERMEM_FCG_STORE_DIR)`; assemble the manifest `data` dict (image path/sha, `cxn_supplier_mode`/`hash_mode` from the hashed-lemma constants, `route_keys`/`lexical_anchors` derived from the lemmas, `manifest_id`, `grammar_id`); `await self._store.write_profile_surface_rows(bonfire_id=..., profile=..., surface="grammar_items", rows=[{ "item_type":"fcg_manifest", "item_id":manifest_id, "episode_id":"", "text":..., "data":data }])`. Add `ConstructionSpec`/`GrammarManifest` dataclasses.
- [ ] **Step 5 — Run unit test, expect pass.** `pytest tests/test_author_grammar.py -q`.
- [ ] **Step 6 — Gated integration test** `tests/integration/test_game_grammar_comprehend.py` (mark `@pytest.mark.integration`, skip if real pyfcg unavailable). Set `HYPERMEM_FCG_STORE_DIR=tmp_path`, `HYPERMEM_FCG_ALLOW_TMP_STORE=1`. `await kernel.author_grammar("mm-world-v1", [ATTACK_SPEC])` then `meaning, diag = await kernel.comprehend_utterance(bonfire_id="mm-world-v1", utterance="attack the goblin with the iron sword", config=...)`. Assert the meaning yields predicate `attack` with bound `patient`/`instrument` spans and `diag["applied_construct_ids"]` contains `mm.attack.v1`.
- [ ] **Step 7 — Iterate the construction to green.** This is the regime-pinning step. Run the gated test; adjust the construction's poles / config until comprehend binds. **If `validate_hashed_lemma_manifest` (or the loader) rejects the authored grammar**, apply the minimal accommodation: set the hashed-lemma config on the authored grammar so the manifest validates, OR add an `authored: true` manifest flag honored by the load path to bypass `validate_hashed_lemma_manifest`. Keep the change minimal and covered by the gated test.
- [ ] **Step 8 — Seed script** `scripts/seed_game_grammar.py`: construct the `ATTACK_SPEC`, build a `MemoryKernel` against the configured store, `await author_grammar("mm-world-v1", [ATTACK_SPEC])`, print the manifest. Docstring cross-references `memento-mori` spec §5.
- [ ] **Step 9 — Commit.** `git add` the touched files; message `feat(kernel): author_grammar seam + ATTACK game grammar`.

---

## Task 1 — `ComprehensionClient`  [memento-mori engine]

**Run in `/home/at0x/Vaults/Bonfires/memento-mori`, branch `cxn/m2-attack-slice`.**

**Interfaces produced (add to `engine/src/memento/cxn/types.py`):**
```python
class FrameRole(TypedDict):
    role: str            # "agent"|"patient"|"instrument"|"location"
    filler: str          # surface span, e.g. "the goblin"

class ComprehendedFrame(TypedDict):     # raw comprehend output (surface spans)
    predicate: str
    roles: list[FrameRole]
    matched: bool
    raw_text: str

class TurnOutcome(TypedDict):
    status: str                  # "executed" | "clarify"
    update: dict[str, Any] | None
    message: str | None
    reason: str | None           # "no_match"|"unknown_predicate"|"unresolved_role:<r>"|"ambiguous_role:<r>"
```

- [ ] **Step 1 — Failing test** `engine/tests/unit/test_comprehension_client.py`: a fake httpx transport returning a canned `KernelComprehendResponse` with a populated `frame` → assert `HttpComprehensionClient.comprehend("attack the goblin")` returns `ComprehendedFrame{predicate:"attack", matched:True, roles:[{role:"patient",filler:"the goblin"}]}`. Second case: `frame:null` → `matched:False`. Third: transport returns 503 → raises `ComprehendError`.
- [ ] **Step 2 — Run, expect failure.** `pytest engine/tests/unit/test_comprehension_client.py -q`.
- [ ] **Step 3 — Implement** `engine/src/memento/cxn/kernel_client.py`: `ComprehensionClient` Protocol; `HttpComprehensionClient(base_url, token, bonfire_id, client: httpx.AsyncClient)` POSTing `/v1/bonfires/{bonfire_id}/kernel/comprehend` with headers `X-Internal-Token`, `X-Permission: read`; map response `frame` → `ComprehendedFrame` (`frame is None ⇒ matched=False, roles=[]`); raise `ComprehendError` (new domain exception) on non-200. Add `FakeComprehensionClient(canned: dict[str, ComprehendedFrame])`. Mirror header/env conventions of the existing `engine/src/memento/memory/kernel_client.py` (`KernelMemoryClient`); if they diverge, the graph-memory `InternalAuthMiddleware` is authoritative.
- [ ] **Step 4 — Run, expect pass.** `pytest engine/tests/unit/test_comprehension_client.py -q`.
- [ ] **Step 5 — Commit.** `feat(engine): ComprehensionClient over kernel/comprehend`.

---

## Task 2 — `EntityResolver`  [memento-mori engine]

**Interfaces produced:**
```python
class ResolutionFailure(TypedDict):
    reason: str   # "unresolved_role:<r>" | "ambiguous_role:<r>"

class EntityResolver:
    def __init__(self, state: StateRepository) -> None: ...
    async def resolve(self, frame: ComprehendedFrame, actor_id: str,
                      cxn: CxnDef) -> dict[str, str] | ResolutionFailure: ...
```

- [ ] **Step 1 — Failing tests** `engine/tests/unit/test_entity_resolver.py` over `InMemoryStateRepository` seeded from `tests/fixtures.py` (KAEL in ASH_MARKET, GOBLIN in ASH_MARKET, IRON_SWORD in KAEL inventory): (a) `frame` with `patient:"the goblin"`, `instrument:"the iron sword"` → `{"patient": GOBLIN, "instrument": IRON_SWORD}`; (b) `patient:"the dragon"` (absent) → `{"reason":"unresolved_role:patient"}`; (c) two goblins in room + `patient:"goblin"` → `{"reason":"ambiguous_role:patient"}`; (d) actor itself never a patient candidate.
- [ ] **Step 2 — Run, expect failure.**
- [ ] **Step 3 — Implement** `engine/src/memento/cxn/entity_resolver.py`: read `get_actor_snapshot(actor_id)` for `location`/`inventory`; `patient` candidates = `get_entities_at_location(location)` minus actor; `instrument` candidates = inventory item docs (only if the frame carries an instrument span). `_normalize(s)` = lowercase, strip leading `the/a/an`, collapse whitespace. Match: exact normalized name, else unique substring over name/labels. `0 → unresolved_role`, `>1 → ambiguous_role`. Return role→UUID dict (only the text-supplied roles; `agent`/`location`/`instrument`-default are the executor's job).
- [ ] **Step 4 — Run, expect pass.**
- [ ] **Step 5 — Commit.** `feat(engine): deterministic EntityResolver (room/inventory-scoped)`.

---

## Task 3 — `TurnRouter` + `mm_act` MCP tool  [memento-mori engine + gateway]

**Interfaces produced:**
```python
class TurnRouter:
    def __init__(self, comprehension: ComprehensionClient, constructicon: ConstructiconRegistry,
                 resolver: EntityResolver, executor: EffectExecutor, bonfire_id: str) -> None: ...
    async def handle(self, utterance: str, actor_id: str) -> TurnOutcome: ...
```

- [ ] **Step 1 — Failing tests** `engine/tests/unit/test_turn_router.py` (FakeComprehensionClient + InMemoryStateRepository + real EffectExecutor + CapturingMemoryClient + NoopChainMirror, ATTACK fixture world): (a) canned `attack` frame + resolvable roles → `status=="executed"`, `update["state_deltas"]` shows `hp 9→0`, 1 captured episode; death sub-case sets `is_dead`/`DIED_IN`/chain kill (reuse Day-1 ATTACK assertions); (b) `matched=False` frame → `status=="clarify"`, `reason=="no_match"`, store untouched, 0 ingests; (c) frame predicate `"sing"` (no cxn) → `clarify`, `reason=="unknown_predicate"`; (d) `patient:"the dragon"` → `clarify`, `reason=="unresolved_role:patient"`, store untouched.
- [ ] **Step 2 — Run, expect failure.**
- [ ] **Step 3 — Implement `TurnRouter`** `engine/src/memento/cxn/turn_router.py`: comprehend → `if not frame["matched"]: clarify(no_match)` → `cxn = next predicate match in CONSTRUCTION_REGISTRY else clarify(unknown_predicate)` → `resolved = await resolver.resolve(frame, actor_id, cxn)`; on `ResolutionFailure` → `clarify(reason)` → build `SemanticFrame{predicate, roles=resolved, confidence=1.0, raw_text=utterance}` → `matched = constructicon.match(frame)` → `update = await executor.execute(matched["cxn"], caller_id=actor_id, bindings=matched["bound_roles"])` → `executed(update)`. Clarify messages are player-facing strings; `reason` is the machine tag.
- [ ] **Step 4 — Run, expect pass.**
- [ ] **Step 5 — Register `mm_act`** in `gateway/src/gateway/cxn_tools.py`, mirroring the existing `register_cxn_tools` handler shape: `@mcp.tool(name="mm_act") async def mm_act(text: str) -> dict`, `actor_id = await _check_tool_access("mm_act")`, build a `TurnRouter` (shared executor + a `ComprehensionClient` from env; `NullMemoryClient`/`Capturing` as wired), `outcome = await router.handle(text, actor_id)`; on `ConstructionError` return `{"status":"rejected","cause":str(exc)}`; on `clarify` return `{"status":"clarify","message":...}`; on `executed` `broadcast_tool_event(...)` and return the update. Wire the `ComprehensionClient` construction in `build_mcp_app` alongside the existing `memory` client.
- [ ] **Step 6 — Run engine unit suite.** `cd engine && pytest tests/unit -q` (all green, zero NLP/LLM).
- [ ] **Step 7 — Commit.** `feat(engine,gateway): TurnRouter + mm_act free-text ATTACK path`.

---

## Task 4 (stretch) — full e2e gated test  [memento-mori]

- [ ] Gated test: against a seeded `mm-world-v1` grammar + fixture world, `mm_act("attack the goblin with the iron sword")` → exact hp `StateDelta`. Skip when real pyfcg/live kernel unavailable. Commit if green.

---

## Verification

- **Engine unit:** `cd engine && pytest tests/unit -q` — exact `StateDelta`s, zero LLM/NLP.
- **Kernel unit:** `pytest tests/test_author_grammar.py -q` (fake pyfcg + fake store).
- **Gated (regime proof):** `pytest tests/integration/test_game_grammar_comprehend.py` with real pyfcg + `HYPERMEM_FCG_STORE_DIR` set — green = load regime pinned and ATTACK binds roles. This is the single most important signal in the slice.
- **Manual e2e:** `python scripts/seed_game_grammar.py` against a live graph-memory/kernel, then `mm_act("attack the goblin with the iron sword")` → hp delta.

## PR plan

- **memory_kernel:** new branch (Task K) stacked on `feat/comprehend-utterance`; rebase onto `canon` after PR #1 lands.
- **memento-mori:** `cxn/m2-attack-slice` (Tasks 1–4 + the already-committed spec).
- **graph-memory:** untouched (comprehend route PR #121 is the contract).

## Self-review notes

- Spec coverage: §4 author_grammar → Task K; §5 game grammar → Task K Step 3/7; §6.1 ComprehensionClient → Task 1; §6.2 EntityResolver → Task 2; §6.3/6.4 TurnRouter+mm_act → Task 3; §7 tests distributed across tasks; §3.1 TurnOutcome → Task 1 types.
- Type consistency: `ComprehendedFrame` (surface spans, pre-resolution) is distinct from the existing `SemanticFrame` (UUID roles, post-resolution) — the resolver bridges them; `constructicon.py` is untouched.
- Known iterate-to-green: Task K Step 7 (FCG load regime). It is bounded to setting hashed-lemma config or one `authored` manifest flag, proven by the gated test.
