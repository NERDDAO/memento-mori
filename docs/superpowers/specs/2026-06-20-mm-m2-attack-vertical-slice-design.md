# Memento Mori — Milestone 2: Free-Text ATTACK Vertical Slice (Design)

> **Status:** design / spec. Follows the Day-1 walking skeleton
> (`2026-06-19-mm-construction-control-system-design.md`) and Track C
> (the `kernel/comprehend` route, already shipped). This spec covers the
> **thinnest end-to-end proof** of the free-text comprehension path for a
> **single construction (ATTACK)**. The 3-verb path and the legacy fallback
> fork are explicitly deferred.

---

## 1. Goal & cut line

### 1.1 What this delivers

A player types free text — `"attack the goblin with the iron sword"` — and the
turn resolves through the **same deterministic `EffectExecutor` the Day-1
skeleton already runs**, producing an exact `StateUpdate` (hp delta, optional
death) with zero LLM calls in the effect path.

The slice proves the one unknown the Day-1 skeleton could not: that a
**hand-authored FCG game grammar** activates under `comprehend_utterance`,
binds the action's roles, and that an in-engine deterministic pipeline turns
the resulting frame into a filled `MatchedCxn`.

### 1.2 Cut line (what is in / out)

**In:**
- One new public **kernel seam** — `MemoryKernel.author_grammar(...)` — that
  bakes a hand-authored construction set into a PyFCG grammar image and seeds
  it into a bonfire's store (no LLM / corpus-mining pipeline).
- A **seed script** that authors the ATTACK construction into `mm-world-v1`.
- Three engine components: `ComprehensionClient`, `EntityResolver`,
  `TurnRouter`.
- One MCP entry tool: `mm_act(utterance)`.
- Reuse of the Day-1 `Constructicon`, `EffectExecutor`, `StateRepository`,
  `MemoryClient`, `ChainMirror` — **unchanged**.

**Out (deferred):**
- MOVE and TAKE free-text paths (the slice is ATTACK only; the engine
  components are written verb-agnostic so adding verbs is grammar + registry
  work, not new code paths).
- The **legacy `RoundController` fallback fork** (§2.2/§9.1 of the Day-1 spec).
  On no-match the router returns a clarification; it does **not** fork to the
  CrewAI stack. The "construction ↔ legacy coexistence" story is a later
  milestone.
- A **derived confidence float** and threshold knob. "Confidence" is binary:
  a game construction activated **and** all required roles resolved → execute;
  otherwise clarify.
- `kernel/search`-based entity resolution. `EntityResolver` resolves against
  `StateRepository` (room + actor inventory) only.
- Generative composition / entrenchment (a later spec).

### 1.3 The three decisions that shaped this slice

1. **Scope = thin vertical slice, one verb (ATTACK).** Smallest thing that
   proves the whole seam including the grammar.
2. **Grammar authoring = a public kernel seam + seed script** (mirrors how
   Track C exposed `comprehend_utterance`), not a one-off store poke and not a
   new HTTP route.
3. **TurnRouter = comprehend-or-clarify**, binary confidence, no legacy fork.

---

## 2. Background: what already exists (verified)

### 2.1 The comprehend route (Track C — shipped)

- **graph-memory** exposes `POST /v1/bonfires/{bonfire_id}/kernel/comprehend`
  (PR #121, stacked on the kernel module PR #120). DTOs:
  `KernelComprehendRequest{actor_id, utterance, entity_hints[],
  allowed_construct_ids[]}` →
  `KernelComprehendResponse{bonfire_id, actor_id, utterance,
  frame: SemanticFrameDTO | None, diagnostics}` where
  `SemanticFrameDTO{predicate, confidence, roles: list[BoundRole], applied_cxn_ids,
  matched, raw_meaning}` and `BoundRole{role, filler, entity_id}`.
- **memory_kernel** exposes the public seam
  `MemoryKernel.comprehend_utterance(*, bonfire_id, utterance, config,
  profile=None, activation_scope=None) -> (meaning, diagnostics)` (PR #1, base
  `canon`). It resolves the grammar via
  `read_grammar_items(bonfire_id, profile, item_type="fcg_route_index" | "fcg_manifest")`,
  loads an FCG backend, and comprehends. An **un-indexed** bonfire returns a
  clean `([], {"status": "no_grammar"})` — not an error. A loaded grammar that
  yields no meaning maps to `frame=None` / `status:"no_meaning"` (a normal
  "no match"), **not** a 500.

**Implication:** comprehend only produces meaningful frames against a bonfire
that has a **loaded grammar**. The Day-1 bonfire has none. Authoring + seeding
the game grammar (§4) is therefore the gating prerequisite for the whole slice.

### 2.2 How a grammar enters a bonfire's store (verified)

`comprehend_utterance`'s loader (`PyFCGBackend.load_from_payload`,
`construction/fcg/backend.py:703`) **hard-requires** a `grammar_image_path` (a
binary PyFCG grammar image on disk/`s3://`) plus a `grammar_image_sha256`. It
will **not** read raw construction dicts from a manifest. Therefore authoring is
a **build step**, not a runtime call:

1. Build a `pyfcg.Grammar`, add constructions explicitly. Primitives exist:
   `PyFCGSequenceCxnFactory` / `PyFCGSequenceCxnSpec.from_mapping(...)`
   (`construction/fcg/cxn_factory.py:18,68`) emit real `pyfcg.Construction`s
   with conditional/contributing poles and auto-inject an
   `("fcg-construct-id", construct_id)` meaning predicate; or use raw
   `pyfcg.Construction(...)` + `grammar.add_cxn(...)`
   (`backend.py:160-167`).
2. `agent.save_grammar_image(path)` → the binary image
   (`grammar_store.py:1395`; round-trip template:
   `probe_hashed_lemma_grammar_image`, `grammar_store.py:1375`).
3. Write **one** `grammar_items` row, `item_type:"fcg_manifest"`, whose `data`
   carries `grammar_image_path` + `grammar_image_sha256` (+ optional
   `route_keys` / `lexical_anchors`), via the generic store seam
   `write_profile_surface_rows(bonfire_id=..., profile=..., surface="grammar_items",
   rows=[...])` (`storage/mongo_surface_store.py:258`). This seam is
   **item-type-agnostic and not LLM-coupled** — nothing about it requires the
   `NlpPrimitiveGraph` / mining pipeline.

There is no existing convenience wrapper for "(grammar payload + bonfire_id) →
write manifest." **§4 makes that the new `author_grammar` seam.**

### 2.3 What comprehend returns structurally (verified)

`PyFCGBackend._comprehend_query` returns `(meaning, diagnostics)`. For
PropBank-frame meanings, each frame is
`{"roleset": "<id>", "roles": [["v","<surface>"], ["<role>","<surface>"], ...]}`
(`backend.py:427`). Diagnostics carry `applied_construct_ids`,
`applied_cxn_names`, `meaning_constraints`, etc. The Track C graph-memory
adapter maps this to `SemanticFrameDTO`: predicate ← the `v`-role surface, the
remaining role entries → `BoundRole`s (the `v` slot is dropped),
`applied_cxn_ids` ← `diagnostics.applied_construct_ids`.

**We control the roleset** because we author the constructions: the ATTACK
construction's meaning emits roles labeled `agent` / `patient` / `instrument`
directly, so the engine needs **no PropBank `arg0→agent` remap**.

---

## 3. The free-text agent loop (data flow)

```
player free-text turn
  └─ MCP tool  mm_act(utterance)            [gateway]
        actor_id ← caller JWT `sub`;  bonfire_id = "mm-world-v1" (fixed at deploy)
        │
        ▼  TurnRouter.handle(utterance, actor_id) -> TurnOutcome      [engine]
  1. frame = ComprehensionClient.comprehend(utterance, bonfire_id, actor_id)
        └─ HTTP POST graph-memory /v1/bonfires/mm-world-v1/kernel/comprehend
        ← SemanticFrame{ predicate:"attack", matched:true,
                         roles:[ {role:"patient",     filler:"the goblin"},
                                 {role:"instrument",  filler:"the iron sword"} ] }
  2. if not frame.matched ───────────────► CLARIFY ("I don't understand that action"); STOP — no state touched
  3. cxn = Constructicon.match(frame.predicate)      (reuse Day-1 registry)
        if cxn is None ─────────────────► CLARIFY; STOP
  4. bound = EntityResolver.resolve(frame.roles, actor_id, cxn)      [engine, deterministic, no NLP]
        agent      = actor_id                            (the caller)
        location   = actor.location_uuid                 (from StateRepository)
        patient    = resolve "the goblin"  against entities in actor's room
        instrument = resolve "the iron sword" against actor's inventory/equipped
        if any REQUIRED role unresolved / ambiguous ──► CLARIFY (role-specific); STOP — no state touched
  5. matched = MatchedCxn(cxn=ATTACK, bound_roles={agent, patient, instrument, location})
  6. update = EffectExecutor.execute(matched.cxn, caller_id=actor_id, bindings=matched.bound_roles)
        └─ UNCHANGED Day-1 path → StateUpdate (+ kernel/index episode, non-fatal)
  return TurnOutcome.executed(update)
```

Steps 3, 5, 6 are pure reuse of Day-1 code. Steps 1, 2, 4 are the new pipeline.
Every early-exit (`CLARIFY`) leaves the store **untouched** — resolution and
matching happen strictly before any executor write.

### 3.1 `TurnOutcome`

The router returns a tagged result so the gateway can render either a state
update or a clarification without raising for the (normal) no-match case:

```python
# engine/src/memento/cxn/types.py  (Milestone-2 additions)
class TurnOutcome(TypedDict):
    status: str                    # "executed" | "clarify"
    update: StateUpdate | None     # present iff status == "executed"
    message: str | None            # player-facing clarification iff status == "clarify"
    reason: str | None             # machine tag: "no_match" | "unknown_predicate"
                                   #   | "unresolved_role:<role>" | "ambiguous_role:<role>"
```

`ConstructionError` (a guard failure inside the executor, e.g. `agent_armed`)
still propagates as today — it is a rejected *action*, distinct from a
*non-comprehended* turn. The gateway maps `ConstructionError` to a rejection
message and `clarify` to a clarification; only genuinely unexpected failures
surface as errors.

---

## 4. The kernel seam: `author_grammar`

### 4.1 Why a seam (not a script-only poke)

Track C established the pattern: when memento-mori needs a kernel capability,
expose it as a **thin, tested, public `MemoryKernel` method** rather than
reaching into private internals from a one-off script. "Load a hand-authored
grammar for a bonfire" becomes a first-class, reusable capability — needed
again for MOVE/TAKE and any future game construction.

### 4.2 Signature & behavior

```python
# memory_kernel/src/memory_kernel/runtime/kernel.py
@dataclass(frozen=True)
class ConstructionSpec:
    construct_id: str          # stable id, e.g. "mm.attack.v1"
    name: str                  # cxn name
    surface: list[str]         # trigger lemmas, e.g. ["attack", "strike", "hit"]
    roles: list[str]           # emitted role labels, e.g. ["agent", "patient", "instrument"]
    meaning: dict[str, Any]    # role→slot config the cxn_factory consumes
    # (exact field set finalized against PyFCGSequenceCxnSpec.from_mapping during build)

@dataclass(frozen=True)
class GrammarManifest:
    bonfire_id: str
    profile: str
    grammar_image_path: str
    grammar_image_sha256: str
    construct_ids: list[str]

async def author_grammar(
    self,
    *,
    bonfire_id: str,
    constructions: list[ConstructionSpec],
    profile: str | None = None,
) -> GrammarManifest:
    """Bake hand-authored constructions into a PyFCG grammar image and seed
    it into the bonfire's store as a single fcg_manifest grammar_items row.
    Bypasses the NlpPrimitiveGraph / corpus-mining pipeline entirely.
    Idempotent on (bonfire_id, profile): re-authoring overwrites the manifest
    row and rewrites the image (sha-addressed)."""
```

Implementation (template: `probe_hashed_lemma_grammar_image`,
`grammar_store.py:1375`):
1. `grammar = pyfcg.Grammar(id=<bonfire/profile-derived>)`; set feature types +
   configuration to match what `comprehend_utterance`'s loader expects.
2. For each `ConstructionSpec`: `PyFCGSequenceCxnFactory(pyfcg.Construction).build(
   PyFCGSequenceCxnSpec.from_mapping({...}))`; `grammar.add_cxn(cxn)`.
3. `save_grammar_image(path)` to a configured grammar-image dir; compute sha256.
4. Build the manifest `data` dict (`grammar_image_path`, `grammar_image_sha256`,
   minimal `route_keys`/`lexical_anchors` derived from `surface`).
5. `await self._store.write_profile_surface_rows(bonfire_id=..., profile=...,
   surface="grammar_items", rows=[{item_id, item_type:"fcg_manifest", data}])`.

### 4.3 Seed script

```
memory_kernel/scripts/seed_game_grammar.py
```

Reads the game's construction spec (§5.1), constructs `ConstructionSpec`s, and
calls `kernel.author_grammar(bonfire_id="mm-world-v1", constructions=[ATTACK])`.
Deploy-time op, co-located with pyfcg + the store. Re-runnable (idempotent).

---

## 5. The game grammar (content)

### 5.1 Authoring home

The **declarative construction content is game data, owned by memento-mori**:

```
memento-mori/engine/src/memento/cxn/game_grammar/attack.py   # or attack.json
```

It defines the ATTACK construction declaratively: trigger lemmas
(`attack` / `strike` / `hit`), an SVO + instrument argument structure, and the
roleset mapping subject→`agent`, direct-object→`patient`, with-PP→`instrument`.
The kernel **seed script reads this content**; the kernel seam **bakes** it. The
game owns *what the construction means*; the kernel owns *how it is compiled and
stored*.

> Cross-repo handoff (acknowledged wrinkle): the spec lives in memento-mori and
> is consumed by a script in memory_kernel. For the slice, commit the spec as
> data in memento-mori and have the seed script import/read it (a committed copy
> or a small shared file). Finalize the exact transport in the implementation
> plan; it does not affect the runtime path.

### 5.2 What the construction must produce

On `comprehend_utterance("attack the goblin with the iron sword")` against the
seeded grammar, the meaning must yield a PropBank-style frame whose roles, after
the Track C adapter drops `v`, are:

```
predicate    = "attack"
roles        = [ {role:"patient",    filler:"the goblin"},
                 {role:"instrument", filler:"the iron sword"} ]
applied_cxn_ids ⊇ ["mm.attack.v1"]
matched      = true
```

`agent` is **not** required from text (it is the caller); the construction may
emit an `agent` slot bound to the syntactic subject when present, but the engine
sources `agent` from `actor_id` regardless (§3, §6.2).

---

## 6. Engine components

### 6.1 `ComprehensionClient` (`engine/src/memento/cxn/kernel_client.py`)

A thin async HTTP wrapper over `httpx.AsyncClient`, talking to graph-memory's
comprehend route. The engine **never imports memory_kernel/pyfcg** — substrate
(b) is reached only over HTTP.

```python
class ComprehensionClient(Protocol):
    async def comprehend(self, utterance: str, bonfire_id: str,
                         actor_id: str) -> SemanticFrame: ...

class HttpComprehensionClient:
    """POSTs kernel/comprehend with GM_INTERNAL_TOKEN; maps the response
    SemanticFrameDTO → engine SemanticFrame. frame is None ⇒ matched=False."""

class FakeComprehensionClient:
    """Test double: returns canned SemanticFrames keyed by utterance.
    The ONLY comprehension double unit tests use — keeps NLP out of unit tests."""
```

`SemanticFrame` (already reserved in §8.2 of the Day-1 spec) carries
`predicate: str`, `matched: bool`, `roles: list[FrameRole]` where
`FrameRole{role, filler}`. Failure contract (§5.5 of the Day-1 spec): a
comprehend timeout/5xx raises `ComprehendError` → the gateway renders
"I couldn't process that — try again"; a `matched=False` 200 is a normal
clarification, not an error.

### 6.2 `EntityResolver` (`engine/src/memento/cxn/entity_resolver.py`)

Deterministic surface-span → entity-UUID resolution. **No NLP, no kernel
round-trip.** Scopes each role to the right candidate set and matches by
normalized name/label:

```python
class EntityResolver:
    def __init__(self, state: StateRepository) -> None: ...

    async def resolve(self, roles: list[FrameRole], actor_id: str,
                      cxn: CxnDef) -> ResolvedRoles:
        """Returns bound_roles {role: uuid} or a ResolutionFailure
        (reason="unresolved_role:<r>" | "ambiguous_role:<r>")."""
```

Rules (thin-slice):
- `agent` ← `actor_id` (never resolved from text).
- `location` ← `actor.location_uuid` (from `get_actor_snapshot` /
  `get_entity`).
- `patient` ← candidates = `get_entities_at_location(actor.location_uuid)`
  (excluding the actor); match the filler.
- `instrument` ← candidates = actor inventory + equipped items
  (from the actor snapshot); match the filler.
- **Matching:** normalize (lowercase, strip leading articles `the/a/an`,
  collapse whitespace) → (1) exact name match, else (2) unique substring match
  against name or label. **0 candidates → `unresolved_role`; >1 → `ambiguous_role`.**
  UUIDs are the only identity; names are display-only matching keys
  (per the repo's "Always Use UUIDs, Never Names" rule — names feed matching,
  never identity).
- A role the construction did not bind that the cxn marks **required** →
  `unresolved_role`. (ATTACK requires `agent`, `patient`, `location`;
  `instrument` is required iff the cxn's `agent_armed` guard demands it — keep
  ATTACK's Day-1 guard semantics.)

### 6.3 `TurnRouter` (`engine/src/memento/cxn/turn_router.py`)

The orchestrator of §3. Constructor-DI'd with `ComprehensionClient`,
`Constructicon`, `EntityResolver`, `EffectExecutor`, and the fixed
`bonfire_id`. Pure async function; no crew, no flow graph. Returns
`TurnOutcome`. Contains the binary comprehend-or-clarify logic and **no legacy
fork**.

### 6.4 `mm_act` MCP tool (`gateway/src/gateway/cxn_tools.py`)

One new tool registered via the existing `FastMCP` / `build_mcp_app` factory
(same path as the Day-1 per-cxn tools): `mm_act(utterance: str)`. `actor_id` ←
JWT `sub` (via existing `_BearerAuthMiddleware`); `bonfire_id` fixed. Calls
`TurnRouter.handle`, renders `TurnOutcome` (state update vs clarification),
and `broadcast_tool_event` as the Day-1 tools do. No kit change beyond
registering the tool (the Day-1 §7.5 kit edit pattern).

---

## 7. Test strategy

**Principle (inherited from Day-1): no LLM and no NLP in unit tests.** All real
comprehension lives behind the `ComprehensionClient` seam and is faked in unit
tests; real pyfcg comprehension runs in one CI-gated integration test.

**Unit (deterministic, no NLP/LLM):**
- `EntityResolver` over a fake/`InMemory` `StateRepository`: exact resolve;
  article stripping; `patient` scoped to room; `instrument` scoped to
  inventory; `0 candidates → unresolved_role`; `>1 → ambiguous_role`; actor
  excluded from patient candidates.
- `TurnRouter` with `FakeComprehensionClient` + `InMemoryStateRepository` +
  real `EffectExecutor` + `CapturingMemoryClient` + `NoopChainMirror`:
  - matched + fully resolved ATTACK → exact `StateDelta` (`hp 9 → 0`),
    death sub-case (`is_dead=True`, `DIED_IN` link, `chain_kill` captured) —
    reuses the Day-1 ATTACK assertions verbatim.
  - `matched=False` → `TurnOutcome.status=="clarify"`, `reason=="no_match"`,
    store untouched, zero ingests.
  - unknown predicate → `clarify`, `reason=="unknown_predicate"`.
  - unresolved/ambiguous role → `clarify`, `reason=="unresolved_role:patient"`
    etc., store untouched.
- `HttpComprehensionClient` DTO mapping — against a fake transport returning a
  canned `KernelComprehendResponse` (frame present → `SemanticFrame`;
  `frame:null` → `matched=False`; 5xx → `ComprehendError`).

**Integration (CI-gated on pyfcg/spaCy availability, like Track C's indexed
case):**
- `author_grammar` round-trip (memory_kernel) — seed → exactly one
  `fcg_manifest` row written with `grammar_image_path` + matching sha; the image
  loads via the same loader `comprehend_utterance` uses.
- real comprehend (memory_kernel) — after seeding,
  `comprehend_utterance("attack the goblin with the iron sword")` →
  `predicate=="attack"`, `applied_construct_ids ⊇ ["mm.attack.v1"]`, bound
  `patient`/`instrument` spans present.
- full e2e (memento-mori, stretch) — `mm_act("attack the goblin with the iron
  sword")` against the seeded grammar + a fixture world → exact hp `StateDelta`.

**CI gate (unit):** `pytest engine/tests/unit -q` — exact `StateDelta` values,
zero LLM, zero NLP. The pyfcg integration tests run in the gated job only.

---

## 8. Repo & PR plan

| Repo | Change | Branch / base |
|---|---|---|
| **memory_kernel** | `author_grammar` seam + `ConstructionSpec`/`GrammarManifest` + `scripts/seed_game_grammar.py` + unit + gated integration tests | new branch; follows / stacks on the open `comprehend_utterance` PR #1 (base `canon`) |
| **memento-mori** | `game_grammar/attack` spec; `kernel_client.py` (`ComprehensionClient`); `entity_resolver.py`; `turn_router.py`; `mm_act` tool; `types.py` M2 additions; unit + stretch e2e tests | off `cxn/day1-skeleton` (or `canon` once the skeleton lands) |
| **graph-memory** | none — comprehend route (PR #121) is the contract | — |

Boundary rules honored: the engine talks to the kernel **only** over HTTP
(graph-memory routes); only the deploy-time seed script imports
memory_kernel/pyfcg. The py314-target vs 3.13-runtime ruff tension noted in
Track C applies to any graph-memory edits — but the slice touches no
graph-memory code.

---

## 9. Forward map (after this slice)

- **3-verb path:** author MOVE + TAKE constructions into the same grammar
  image; register their predicates in the `Constructicon`. The engine
  components are already verb-agnostic — no new code paths.
- **Legacy fallback fork:** `TurnRouter` gains the `RoundController.run()`
  branch on `clarify`, turning the legacy stack into a genuine fallback
  (Day-1 spec §2.2/§9.1).
- **Confidence float + threshold:** derive from comprehend diagnostics once a
  multi-verb grammar makes activation ambiguity real.
- **`kernel/search` entity resolution:** add embedding candidate retrieval when
  worlds grow past single-room, deterministic name matching.

---

## 10. Definition of done (the committed slice)

- `MemoryKernel.author_grammar` lands with unit tests; `seed_game_grammar.py`
  seeds `mm-world-v1` with the ATTACK construction.
- `ComprehensionClient`, `EntityResolver`, `TurnRouter`, `mm_act` land with the
  §7 unit suite green (zero LLM, zero NLP).
- The gated integration test proves real `comprehend_utterance` against the
  seeded grammar returns `predicate=="attack"` with bound `patient`/`instrument`.
- A player utterance `"attack the goblin with the iron sword"` resolves through
  the unchanged `EffectExecutor` to the exact Day-1 ATTACK `StateDelta`
  (proven by the `TurnRouter` unit test; end-to-end via `mm_act` is the stretch
  gate).
- No legacy `RoundController` integration, no confidence float, no
  `kernel/search`, no MOVE/TAKE — all explicitly deferred.
