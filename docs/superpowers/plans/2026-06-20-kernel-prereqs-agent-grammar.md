# Kernel Prerequisites — Per-Agent Grammar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the kernel able to give each agent its own FCG grammar — seed it (an `author_grammar` HTTP route), comprehend against it (`profile`-threaded comprehend exposing activated cxn ids), and keep it cheap (hashed-lemma-native, no `:all-cxns` bloat ×N agents). This is the upstream piece of the mmori agent-runtime integration.

**Architecture:** Two repos. (1) `memory_kernel` — make `author_grammar`/`build_attack_grammar` produce a **hashed-lemma** grammar image and drop the `authored:true` validation bypass. (2) `bonfires-ai-core/services/graph-memory` — expose `author_grammar` as a write route and thread a per-agent `profile` through the existing `comprehend` route. `comprehend` already returns `applied_cxn_ids` (the activated constructions), so the activation→unlock loop's kernel half is satisfied by exposing it per-agent.

**Tech Stack:** Python, PyFCG (memory_kernel), FastAPI + Pydantic (graph-memory), pytest/pytest-asyncio, httpx/ASGITransport.

## Global Constraints

- **Repos/branches:** `memory_kernel` on `cxn/author-grammar`; `bonfires-ai-core` graph-memory on `feat/kernel-comprehend-route`.
- **graph-memory:** pyright strict via the 3.13 venv (`pyright --pythonversion 3.13`, 0 errors); services raise domain exceptions, never `HTTPException`; no `Any` in service signatures (DTOs may use `Any`); auth = `X-Internal-Token` + `X-Permission` (`author-grammar` is **write** → `require_write`); the py314-target vs 3.13-runtime ruff tension — keep parenthesized `except (A, B):`, never run blanket `ruff format src` (format only touched files); gates: `ruff check src`, `pyright --pythonversion 3.13`, `lint-imports`, `python ../../scripts/check-boundaries.py`.
- **memory_kernel:** its own pyright/ruff; pyfcg is faked via `sys.modules` injection in unit tests, real pyfcg only in the gated integration test (`HYPERMEM_FCG_STORE_DIR=<tmp>` + `HYPERMEM_FCG_ALLOW_TMP_STORE=1`).
- Commit trailer exactly: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Stage only files you touch (memory_kernel working tree has pre-existing noise — `AGENTS.md`/`CLAUDE.md`/`.fcg-store/`; never `git add -A`).
- TDD: failing test → see it fail → minimal impl → see it pass → commit.

## Verified interfaces (reuse — do not re-derive)

```python
# memory_kernel/src/memory_kernel/runtime/kernel.py
@dataclass(frozen=True)
class ConstructionSpec: construct_id: str; name: str; lemmas: list[str]; predicate: str; roles: list[str]
@dataclass(frozen=True)
class GrammarManifest: bonfire_id: str; profile: str; grammar_image_path: str; grammar_image_sha256: str; construct_ids: list[str]
async def author_grammar(self, *, bonfire_id, constructions: list[ConstructionSpec], profile=None, store_dir=None) -> GrammarManifest
async def comprehend_utterance(self, *, bonfire_id, utterance, config, profile=None, activation_scope=None) -> tuple[list, dict]
# profile resolves to (profile or "baseline").strip() or "baseline"

# grammar_store.py (hashed-lemma machinery to reuse)
HASHED_LEMMA_CXN_SUPPLIER_MODE = ":hashed-categorial-network"; HASHED_LEMMA_HASH_MODE = ":hash-lemma"
def apply_hashed_lemma_configuration(grammar_or_agent) -> dict      # writes HASHED_LEMMA_GRAMMAR_CONFIG
def _register_hashed_lemma_inventory(grammar) -> None               # grammar.hashed=True; register_grammar() — BEFORE add_cxn
def _set_query_sequence_feature_types(grammar) -> None
# reference build/save order = probe_hashed_lemma_grammar_image (grammar_store.py:1409-1413)

# graph-memory kernel module (services/graph-memory/src/modules/kernel/)
# kernel_dto.py: SemanticFrameDTO ALREADY has `applied_cxn_ids: list[str]` (line 96) ← diagnostics["applied_construct_ids"]
# KernelComprehendRequest{actor_id, utterance, entity_hints, allowed_construct_ids}
# kernel_routes.py: prefix /bonfires/{bonfire_id}/kernel, mounted at /v1; /index is the require_write template
# adapter: MemoryKernelGraphAdapter.comprehend calls kernel.comprehend_utterance(profile=self._profile)  (client.py:299-305)
```

---

## Task 1: Hashing fix — authored grammar becomes hashed-lemma-native  [memory_kernel]

Make `build_attack_grammar` save a hashed-lemma image and drop the `authored:true` bypass so per-agent grammars hash into lemma buckets (no `:all-cxns`). The gated comprehend test is the empirical gate.

**Files:** Modify `src/memory_kernel/construction/fcg/game_grammar.py`, `src/memory_kernel/runtime/kernel.py:475`, `src/memory_kernel/construction/fcg/grammar_store.py:1048-1079,1734-1740`; Test `tests/test_author_grammar.py`, `tests/integration/test_game_grammar_comprehend.py`.

- [ ] **Step 1 — Extend the fake grammar so hashed calls don't explode.** In `tests/test_author_grammar.py`, add to `_FakeGrammar`: a `hashed` attr, `register_grammar()` (no-op), and `configuration` dict support so `apply_hashed_lemma_configuration`/`_register_hashed_lemma_inventory` run against the fake. (Mirror what `_set_live_grammar_configuration`/`register_grammar` touch.) Run `pytest tests/test_author_grammar.py -q` — still green (no behavior change yet).
- [ ] **Step 2 — Drop the manifest bypass flag (RED).** In `runtime/kernel.py` remove `"authored": True` from the manifest `data` dict (line 475) and rewrite the method docstring (lines 416-430) to state the grammar is now hashed-lemma-native. Run the gated test `HYPERMEM_FCG_STORE_DIR=$(mktemp -d) HYPERMEM_FCG_ALLOW_TMP_STORE=1 .venv/bin/python -m pytest tests/integration/test_game_grammar_comprehend.py -q` — expect FAIL (the saved `:all-cxns` image now goes through hashed-lemma validation / NIL-bucket checks and either fails validation or yields no comprehension).
- [ ] **Step 3 — Apply hashed-lemma inventory + config in the builder.** In `game_grammar.py build_attack_grammar`, import `apply_hashed_lemma_configuration, _register_hashed_lemma_inventory, _set_query_sequence_feature_types` from `grammar_store`. Right after the grammar is created + `categorial_network` seeded (after line ~190, before the `add_cxn` loop) call `_register_hashed_lemma_inventory(grammar)`. Before `save_grammar_image` (line ~238) call `apply_hashed_lemma_configuration(grammar)` then `_set_query_sequence_feature_types(grammar)` — mirroring `probe_hashed_lemma_grammar_image` (grammar_store.py:1409-1413). Ensure each verb cxn (`mm-verb-<lemma>-cxn`) carries a **lemma** so it lands in the `attack`/`strike`/`hit` bucket (the `_lexical_cxn` helper currently stamps no lemma attribute — add a `lemma` to its attributes, or build the verb cxns via `_primitive_sequence_cxn`, which stamps the lemma bucket key). The anchorless `mm-attack-cxn` stays anchorless — it co-activates via `add_link("attack-verb-cxn","attack-clause")` (do NOT give it a lemma).
- [ ] **Step 4 — Remove the loader bypass.** In `grammar_store.py load_bonfire_grammar`, delete the `authored = _is_authored_manifest(manifest)` branch (lines 1048-1056 → always `validate_hashed_lemma_manifest(manifest)`) and the `if authored: …return grammar` early-return (lines 1070-1079), so control falls through to the normal hashed-lemma path (validate config → inventory → `inspect_hashed_lemma_buckets` → health probes). Delete `_is_authored_manifest` (lines 1734-1740; only caller was line 1054).
- [ ] **Step 5 — Make the gated test pass (GREEN, iterate).** Re-run the gated test from Step 2. It must end green: `applied_construct_ids` contains `mm.attack.v1`, and the meaning binds `attack`/`patient`/`instrument` with `goblin`/`sword` fillers — **under the hashed-lemma supplier**. If `inspect_hashed_lemma_buckets` raises NIL-only, or comprehension is empty, iterate the verb-cxn lemma anchoring (Step 3) until the buckets populate and the clause comprehends. This is the empirical heart of the fix.
- [ ] **Step 6 — Update the unit-test manifest assertions.** In `tests/test_author_grammar.py`, remove `assert data["authored"] is True` (line 127) and rewrite the comment; keep the `cxn_supplier_mode`/`hash_mode`/`route_keys|lexical_anchors` assertions (still valid). Run `pytest tests/test_author_grammar.py -q` — green.
- [ ] **Step 7 — Commit.** `git add` the touched files only; message `fix(kernel): hashed-lemma-native authored grammar (drop :all-cxns bypass)`.

---

## Task 2: `author_grammar` graph-memory route  [bonfires-ai-core / graph-memory]

Expose `POST /v1/bonfires/{bonfire_id}/kernel/author-grammar` mirroring `/index` (write), delegating to the kernel's `author_grammar`.

**Files:** Modify `services/graph-memory/src/modules/kernel/kernel_dto.py`, `kernel_service.py`, `kernel_controller.py`, `kernel_routes.py`, `src/adapters/memory_kernel/client.py`; Test `tests/modules/kernel/test_kernel_controller.py`, `tests/adapters/memory_kernel/test_client.py`.

**Interfaces produced:**
```python
class ConstructionSpecDTO(BaseModel): construct_id: str; name: str; lemmas: list[str]; predicate: str; roles: list[str]
class KernelAuthorGrammarRequest(BaseModel): constructions: list[ConstructionSpecDTO]; profile: str | None = None
class KernelAuthorGrammarResponse(BaseModel): bonfire_id: str; profile: str; grammar_image_path: str; grammar_image_sha256: str; construct_ids: list[str]
# KernelBackendProtocol.author_grammar(*, bonfire_id, constructions, profile=None) -> Mapping[str, object]
```

- [ ] **Step 1 — Failing route test.** In `tests/modules/kernel/test_kernel_controller.py`, mirror `test_kernel_routes_expose_comprehend_endpoint` (lines 147-185): mock `service.author_grammar` (AsyncMock returning `{"bonfire_id":"bf-1","profile":"agent-7","grammar_image_path":"/x.store","grammar_image_sha256":"abc","construct_ids":["mm.attack.v1"]}`), override `require_write`, POST `/bonfires/bf-1/kernel/author-grammar` with `{"profile":"agent-7","constructions":[{"construct_id":"mm.attack.v1","name":"attack","lemmas":["attack"],"predicate":"attack","roles":["agent","patient","instrument"]}]}`, assert 200 + payload + `service.author_grammar.assert_awaited_once_with(bonfire_id="bf-1", constructions=<specs>, profile="agent-7")`.
- [ ] **Step 2 — Run, expect fail.** `pytest tests/modules/kernel/test_kernel_controller.py -q` (route 404 / DTO import error).
- [ ] **Step 3 — DTOs.** Add `ConstructionSpecDTO`, `KernelAuthorGrammarRequest`, `KernelAuthorGrammarResponse` to `kernel_dto.py` (use the `KernelIndexResponse` profile-bearing shape as the template).
- [ ] **Step 4 — Service + protocol.** Add `author_grammar` to `KernelBackendProtocol` and `KernelService` (delegate to `self._backend.author_grammar(...)`), keyword-only, returning `Mapping[str, object]`.
- [ ] **Step 5 — Controller.** Add `author_grammar(self, bonfire_id, request)` mirroring `index` (lines 26-34): call `self._service.author_grammar(bonfire_id=bonfire_id, constructions=request.constructions, profile=request.profile)`, `return KernelAuthorGrammarResponse.model_validate(result)`.
- [ ] **Step 6 — Route.** In `kernel_routes.py` add `@router.post("/author-grammar", response_model=KernelAuthorGrammarResponse, dependencies=[Depends(require_write)])` → `controller.author_grammar(bonfire_id, request)`, with the `# pyright: ignore[reportUnusedFunction]` + justification comment.
- [ ] **Step 7 — Adapter.** In `adapters/memory_kernel/client.py` add `async def author_grammar(self, *, bonfire_id, constructions, profile=None) -> Mapping[str, object]`: `kernel = self._require_kernel()`; map each `ConstructionSpecDTO` → `ConstructionSpec` (import `from memory_kernel.runtime.kernel import ConstructionSpec, GrammarManifest` — they are NOT re-exported at package level); `manifest = await kernel.author_grammar(bonfire_id=bonfire_id, constructions=specs, profile=profile or self._profile)`; return `{"bonfire_id": manifest.bonfire_id, "profile": manifest.profile, "grammar_image_path": manifest.grammar_image_path, "grammar_image_sha256": manifest.grammar_image_sha256, "construct_ids": list(manifest.construct_ids)}`. Add an adapter unit test in `tests/adapters/memory_kernel/test_client.py` with a fake kernel exposing `async def author_grammar(self, **_kwargs)` (mirror the comprehend fake at test_client.py:61-72 + the `adapter._kernel = FakeKernel()` injection).
- [ ] **Step 8 — Run tests, expect pass.** `pytest tests/modules/kernel/test_kernel_controller.py tests/adapters/memory_kernel/test_client.py -q`.
- [ ] **Step 9 — Gates.** From `services/graph-memory`: `ruff check src`; `pyright --pythonversion 3.13` (0 errors); `lint-imports`; `python ../../scripts/check-boundaries.py`.
- [ ] **Step 10 — Commit.** `feat(graph-memory): kernel/author-grammar route (per-agent grammar seeding)`.

---

## Task 3: Thread per-agent `profile` through comprehend  [bonfires-ai-core / graph-memory]

Add an optional `profile` to the comprehend request so an agent comprehends against its own grammar; `applied_cxn_ids` (already in `SemanticFrameDTO`) is the exposed activation set.

**Files:** Modify `kernel_dto.py`, `kernel_service.py`, `kernel_controller.py`, `src/adapters/memory_kernel/client.py`; Test `tests/modules/kernel/test_kernel_controller.py`, `tests/adapters/memory_kernel/test_client.py`.

- [ ] **Step 1 — Failing/updated tests.** Add a controller test: POST `/bonfires/bf-1/kernel/comprehend` with `{"actor_id":"a","utterance":"u","profile":"agent-7"}` asserts `service.comprehend.assert_awaited_once_with(bonfire_id="bf-1", utterance="u", entity_hints=[], allowed_construct_ids=[], profile="agent-7")`. Also UPDATE the three existing `assert_awaited_once_with(...)` calls (test_kernel_controller.py:105-110, 180-185) to include `profile=None` (they will break otherwise).
- [ ] **Step 2 — Run, expect fail.** `pytest tests/modules/kernel/test_kernel_controller.py -q` (new assertion + the unparameterised existing ones).
- [ ] **Step 3 — DTO.** Add `profile: str | None = None` to `KernelComprehendRequest` in `kernel_dto.py` (no `Field` constraints; backward-compatible — bodies without `profile` validate to `None`).
- [ ] **Step 4 — Service + protocol.** Add `profile: str | None = None` to `KernelBackendProtocol.comprehend` and `KernelService.comprehend`; forward `profile=profile` to `self._backend.comprehend(...)`.
- [ ] **Step 5 — Controller.** Pass `profile=request.profile` in the controller's `self._service.comprehend(...)` call (kernel_controller.py:47-58).
- [ ] **Step 6 — Adapter.** Change `MemoryKernelGraphAdapter.comprehend` to accept `profile: str | None = None` and pass `profile=profile or self._profile` to `kernel.comprehend_utterance(...)` (client.py:299-305) instead of the fixed `self._profile`. Add/extend an adapter test asserting the per-call profile is forwarded.
- [ ] **Step 7 — Run, expect pass.** `pytest tests/modules/kernel/test_kernel_controller.py tests/adapters/memory_kernel/test_client.py -q`.
- [ ] **Step 8 — Gates.** `ruff check src`; `pyright --pythonversion 3.13`; `lint-imports`; `check-boundaries.py`.
- [ ] **Step 9 — Commit.** `feat(graph-memory): thread per-agent profile through kernel/comprehend`.

---

## Verification

- **memory_kernel:** `pytest tests/test_author_grammar.py -q` (fake pyfcg) green; the gated `HYPERMEM_FCG_STORE_DIR=<tmp> HYPERMEM_FCG_ALLOW_TMP_STORE=1 pytest tests/integration/test_game_grammar_comprehend.py -q` green — the authored grammar comprehends `"attack the goblin with the iron sword"` to `attack`/`patient`/`instrument` + `applied_construct_ids=[mm.attack.v1]` **under hashed-lemma** (no `authored` bypass anywhere in the manifest or loader).
- **graph-memory:** `pytest tests/modules/kernel tests/adapters/memory_kernel -q` green; all four gates clean.
- **Manual end-to-end (per-agent grammar):** `POST /v1/bonfires/mm-world-v1/kernel/author-grammar` (`X-Permission: write`) with `profile="npc:goblin-1"` + the ATTACK construction → 200 with `construct_ids`; then `POST …/kernel/comprehend` (`X-Permission: read`) with `profile="npc:goblin-1"` + `"attack the goblin with the iron sword"` → frame with `predicate:"attack"` and `applied_cxn_ids:["mm.attack.v1"]`. A different `profile` with no seeded grammar returns a null frame — proving per-agent isolation.

## PR plan

- **memory_kernel:** Task 1 on `cxn/author-grammar` (or a stacked `kernel/hashing-fix`); it supersedes the M2 `authored:true` accommodation.
- **bonfires-ai-core:** Tasks 2–3 on `feat/kernel-comprehend-route` (or a stacked branch); the adapter depends on the kernel's `author_grammar` (editable path dep — already present from M2; Task 1's hashing fix lands in the same dep).

## Execution

On approval, materialise as `memento-mori/docs/superpowers/plans/2026-06-20-kernel-prereqs-agent-grammar.md` (kept beside the integration spec), then execute via subagent-driven-development — **Task 1 first** (the hashing fix is the riskiest, iterate-to-green on the gated test), then Tasks 2 and 3 (independent; either order).
