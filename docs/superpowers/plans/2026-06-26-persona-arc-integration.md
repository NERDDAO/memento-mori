# Persona Arc Integration — Consolidate + Test-Level Chain Proof — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Fresh implementer per task, per-task review, whole-branch opus review at the end. Steps use `- [ ]` checkboxes. Spec: `bonfires-ai-core/docs/superpowers/specs/2026-06-25-persona-arc-integration-design.md`.

## Context

The persona/FCG-reframe arc (#4) was built on **two disjoint branches** that descend separately from merge-base `6f851f0` and were never integrated:

- **`persona/npc-capabilities`** (8ca61fb) — adds the `capabilities` field on `RoomDriver._npc_self_spec` (#4-A). Has NO event-sourced state infra.
- **`opening/engine-core`** (c75e531) — carries #4-B-A: `KgProjection`/`EventSourcedStateRepository`, `kg_uuid_for`, the `RoomDriver` `projection` param + KG-uuid `_embodiment_id` resolution, the env-gated KG-backed cxn repo. Has NO `capabilities` field.

Because they're disjoint, **nothing runs end-to-end**: #4-A's capability gating and #4-B-A's KG-uuid identity each sit "ready but inert." This slice merges the two arcs into one trunk and **proves the integrated chain at the test level**: labels → roster `capabilities` + KG-uuid `embodiment_agent_id` → per-self JWT → the gateway's **un-stubbed** `check_tool_access` reading the **same** label store → capability enforcement (allowed tool 200, revoked tool 403).

**Goal:** One integrated trunk where a persona's labels drive both its capability set and the KG-uuid both gates key on, proven by an extended gateway e2e that un-stubs the real capability gate and shares one label store between the roster spec-builder and that gate.

**Architecture:** (1) Merge `persona/npc-capabilities` into a new branch off `opening/engine-core`; git auto-merges `_npc_self_spec` to carry BOTH `capabilities` and the KG-uuid `embodiment_agent_id` — only two trivial conflicts (an import block + an additive test file). (2) Add one deterministic e2e test that drives a real `mm_move` through the real gateway tool route with the real `check_tool_access` reading the same mutable label store the roster spec-builder reads; a label revocation in that one store flips the gate from allow (200) to deny (403). (3) Document the integration + a surfaced executor identifier gap.

**Decision (resolved with the user): identity-uuid proof.** The gate keys on the JWT `sub` (the KG uuid post-#4-B-A) while the `EffectExecutor` resolves the acting agent by **engine** uuid. To avoid that identifier-space split, the proof runs with **KG uuid == engine uuid** (one id). This lets both the gate and the executor resolve the same entity, and drives a REAL `mm_move` to 200. The distinct engine≠KG-uuid property stays covered by the #4-B-A keystone (`test_gate_label_parity.py`); the `kg_uuid→engine` resolution the executor would need for a *distinct*-uuid sub is a real gap, recorded and deferred to the live-stack slice (Task 3).

**Tech Stack:** Python 3.12 (memento-mori engine + gateway). Tests via the repo's pytest invocation (mirror existing files): `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest <path> -q`.

## Branch & base

- **mmori branch:** `persona/arc-integration`, **based on `opening/engine-core` (c75e531)**, with `persona/npc-capabilities` (8ca61fb) merged in.
- Use an **isolated worktree** so the user's checkout is untouched:
  `git worktree add -b persona/arc-integration <scratchpad>/mmori-arc-wt opening/engine-core`, then `git -C <worktree> merge persona/npc-capabilities`.
- **Pre-flight check (before Task 2, after the Task 1 merge):** confirm the merged `gateway/src/gateway/room_driver.py` `_npc_self_spec` returns BOTH `"capabilities": sorted(get_allowed_tools(entity.get("labels", [])))` AND `"embodiment_agent_id": self._embodiment_id(entity_uuid)`, and that `__init__` still has the `projection` kwarg. If either feature is missing after the merge, STOP and escalate (the merge resolution dropped a feature).

## Global Constraints

- Commit trailer (exact): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Never `git add -A`** — stage only the files each task touches. PR targets the mmori repo's base for this lineage (coordinate with the #4-A branches), **never main**.
- UUIDs, not names. Never write test entities to the production KG.
- No `Any` in new public signatures (the pre-existing `repo: Any` on `RoomDriver.__init__` is not widened; no new signatures are added by this slice).
- No cross-service Python imports (plain dicts on the wire). Services raise domain exceptions, not `HTTPException`, except where existing code already does so (the route's 403/404 are pre-existing).
- Ruff-format only the files each task touches (not the whole tree). The base isn't ruff-clean; whole-file format pollutes the diff.
- The integration is a `memento-mori`-only merge + test extension; the agent-runtime side (`persona/service-revision`) is untouched and joins only in the deferred live run.

## Key existing symbols (reuse, don't reinvent)

- **Proof vehicle** — `gateway/tests/test_gm_room_loop_e2e.py` (418 lines, 2 tests): autouse `_jwt_env` fixture sets `JWT_SECRET` (L62–65); `world` fixture (L68–127) seeds via `InMemoryStateRepository().seed_entity(...)` — room A (`labels: ["Location"]`, north exit → room_b_id), room B (`["Location"]`), NPC (`kind: "character"`, `labels: ["Character", "NPC"]`, `location_uuid: room_a_id`, `attrs: {"hp": 10, "max_hp": 10, "inventory": []}`); returns `{"repo", "room_a_id", "room_b_id", "npc_id"}`. `capturing_memory` fixture (L135–140) → `CapturingMemoryClient()`. The existing tests patch `gateway.routes.tools_http.check_tool_access` and `...broadcast_tool_event` to `AsyncMock` no-ops and POST `/v1/tools/mm_move` with `json={"destination": room_b_id}` + `Authorization: Bearer <token>`.
- `sign_jwt(sub, *, type, ttl_seconds, extra_claims=None)` — `gateway/src/gateway/engine_auth.py` L43–66. Keyword-only `type`/`ttl_seconds`.
- `check_tool_access(npc_id: str, tool_name: str) -> None` — `engine_auth.py` L115–159. Innate tools (`INNATE_TOOLS`) bypass the gate. Otherwise resolves `entity_id = resolve_npc_kg_uuid(npc_id) or npc_id`, then (inside the function) `from memento.bonfires_client import get_client; client = await asyncio.to_thread(get_client); entity = await asyncio.to_thread(client.kg.get_entity, entity_id)`, swallows exceptions to `labels = []`, unwraps a `{"entity": {...}}` envelope, then `labels = entity.get("labels", [])`. Denies with `HTTPException(status_code=403, detail={"error": "capability_missing", ...})` when `tool_name not in get_allowed_tools(labels)`.
- The tool route `exec_tool` — `gateway/src/gateway/routes/tools_http.py` L161–215: `POST /v1/tools/{tool}`; `entity_id = Depends(require_jwt)` (the JWT `sub`); unknown tool → 404; `await check_tool_access(entity_id, tool)` (raises 403); on allow runs `executor.execute(cxn, caller_id=entity_id, bindings=bound_roles)` from `request.app.state.cxn_executor`. Body key `destination` → role `location`; `agent` role is always `entity_id`. `ConstructionError` → 200 `{"status": "rejected"}`.
- `get_allowed_tools(labels: list[str]) -> set[str]` — `engine/src/memento/tools/tool_labels.py` L155–166. `INNATE_TOOLS` (L16–30) does NOT include `mm_move`. `KITS["NPC"]` (L36–53) grants `mm_move`, `mm_attack`, `mm_take`, etc. So `labels=["Character","NPC"]` grants `mm_move`; dropping to `labels=["Character"]` removes `mm_move` (no kit → only innate left).
- `RoomDriver` (merged) — `gateway/src/gateway/room_driver.py`: `__init__(*, repo, agent_runtime_client, bonfire_id, internal_token="", player_labels=None, projection=None)`; `_npc_self_spec(entity)` (post-merge) returns `{"id", "embodiment_agent_id": self._embodiment_id(entity_uuid), "names", "seat", "capabilities": sorted(get_allowed_tools(entity.get("labels", [])))}`; `_embodiment_id(engine_uuid)` returns `self._projection.kg_uuid_for(engine_uuid)` if a projection resolves it, else `engine_uuid`. `_npc_self_spec` does NOT call `agent_runtime_client`.
- `EffectExecutor(repo, memory, chain)` — `engine/src/memento/cxn/executor.py` L151; the existing `gateway_app` fixture builds `EffectExecutor(repo=repo, memory=capturing_memory, chain=NoopChainMirror())` and sets `app.state.cxn_repo` / `app.state.cxn_executor`. The route reads `ws_hub` via `getattr(app.state, "ws_hub", None)` so it need not be set.
- **Merge facts** (from `git merge-tree --write-tree opening/engine-core persona/npc-capabilities`): exactly two conflicting files, each one conflict region resolved by **keeping both sides**:
  - `room_driver.py` — the import block only: keep BOTH `if TYPE_CHECKING:\n    from memento.state.kg_projection import KgProjectionProtocol` AND `from memento.tools.tool_labels import get_allowed_tools` (and `from typing import TYPE_CHECKING, Any`). The method bodies (`_npc_self_spec`, `__init__`, `_embodiment_id`) auto-merge correctly.
  - `test_room_driver.py` — keep BOTH sides' added tests: opening's `_FakeProjection` helper + `test_npc_self_spec_ships_kg_uuid_when_projection_resolves`, `test_npc_self_spec_falls_back_to_engine_uuid_without_projection`, `test_npc_self_spec_falls_back_when_projection_has_no_mapping`, AND persona's `test_roster_self_spec_carries_resolved_capabilities`. 11 tests total + `_FakeProjection`; no name collisions.

---

# Movement 1 — consolidate the two arcs

## Task 1 — Merge `persona/npc-capabilities` into the integration branch

**Files:**
- Resolve: `gateway/src/gateway/room_driver.py` (one conflict, the import block)
- Resolve: `gateway/tests/test_room_driver.py` (one conflict, additive tests)

**Interfaces:**
- Produces: a merged `RoomDriver._npc_self_spec` carrying BOTH `capabilities` and the KG-uuid `embodiment_agent_id`; the merged `RoomDriver.__init__` keeping the `projection` kwarg. Task 2 consumes both.

- [ ] **Step 1 — create the worktree + branch and start the merge:**
```bash
WT=<scratchpad>/mmori-arc-wt
git -C /home/at0x/Vaults/Bonfires/memento-mori worktree add -b persona/arc-integration "$WT" opening/engine-core
git -C "$WT" merge --no-commit --no-ff persona/npc-capabilities || true   # expect 2 conflicts
git -C "$WT" status --short    # expect: UU gateway/src/gateway/room_driver.py, UU gateway/tests/test_room_driver.py
```
Expected: exactly two `UU` (both-modified) files; nothing else conflicted.

- [ ] **Step 2 — resolve `room_driver.py` (keep both imports):** In the conflict region near the top of the file, replace the `<<<<<<< ... ======= ... >>>>>>>` block so BOTH imports survive (delete only the conflict markers):
```python
from typing import TYPE_CHECKING, Any

from memento.tools.tool_labels import get_allowed_tools

if TYPE_CHECKING:
    from memento.state.kg_projection import KgProjectionProtocol
```
Leave the rest of the file (the auto-merged `_npc_self_spec`, `__init__`, `_embodiment_id`) untouched.

- [ ] **Step 3 — resolve `test_room_driver.py` (keep both test sets):** In the single conflict region, delete only the conflict markers so BOTH sides' additions remain: opening's `_FakeProjection` helper class + its three `test_npc_self_spec_*` tests AND persona's `test_roster_self_spec_carries_resolved_capabilities`. Do not delete or merge any test body. After resolution the file defines 11 tests total.

- [ ] **Step 4 — verify the merge preserved both features (pre-flight gate):**
```bash
git -C "$WT" grep -n 'capabilities' -- gateway/src/gateway/room_driver.py
git -C "$WT" grep -n '_embodiment_id\|projection' -- gateway/src/gateway/room_driver.py
```
Expected: `_npc_self_spec` shows the `capabilities` key AND `embodiment_agent_id: self._embodiment_id(...)`; `__init__` shows the `projection` kwarg. If either is missing, STOP and escalate.

- [ ] **Step 5 — run the merged room_driver tests:**
```bash
cd "$WT" && PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_room_driver.py -q
```
Expected: 11 passed (7 shared + 3 projection + 1 capabilities).

- [ ] **Step 6 — run the broader engine + gateway suites for regressions:**
```bash
cd "$WT" && PYTHONPATH=engine/src python3.12 -m pytest engine/tests/state -q
cd "$WT" && PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests -q
```
Expected: engine state tests green (including `test_gate_label_parity.py` keystone + `test_kg_projection.py`); gateway tests green **except** the pre-existing, unrelated `test_round_callback.py::test_send_batch_to_matrix` failure (matrix `room_send` mock) — confirm that is the ONLY failure and that it is unchanged by this merge.

- [ ] **Step 7 — complete the merge commit** (stage only the two resolved files; the merge already staged the auto-merged ones):
```bash
git -C "$WT" add gateway/src/gateway/room_driver.py gateway/tests/test_room_driver.py
git -C "$WT" commit   # keep the default merge message; ensure the trailer below is present
```
Commit message: `merge: integrate persona/npc-capabilities (capabilities field) into opening/engine-core (KG-uuid identity)` + the exact `Co-Authored-By` trailer.

---

# Movement 2 — prove the integrated chain

## Task 2 — Integrated capability-chain e2e (one store, real gate)

**Files:**
- Modify: `gateway/tests/test_gm_room_loop_e2e.py` (add one test, reuse `world` + `capturing_memory` fixtures)

**Interfaces:**
- Consumes: merged `RoomDriver._npc_self_spec` (capabilities + KG-uuid embodiment); `sign_jwt`; the real `check_tool_access`; the real `exec_tool` route; `EffectExecutor`.
- Produces: `test_capability_chain_enforced_over_one_store` — the arc-integration proof.

**Design (identity-uuid, per the user's decision):** the executor runs over the existing **InMemory `world`** so a real `mm_move` reaches 200 (the agent is keyed by `npc_id`, and `JWT sub = kg_uuid = npc_id` identity → the executor finds it). The **one store** shared between the roster spec-builder and the gate is an explicit mutable `label_store` dict: `_npc_self_spec` is fed a doc from it, and the un-stubbed `check_tool_access` reads it via a tiny KG-client adapter pointed at the SAME dict. A label revocation in `label_store` flips both the advertised capabilities and the gate's enforcement together. `check_tool_access` is NOT patched; only `broadcast_tool_event` stays stubbed (it needs an `app.state.ws_hub` the test doesn't wire).

- [ ] **Step 1 — write the failing test** (append to `gateway/tests/test_gm_room_loop_e2e.py`; the autouse `_jwt_env` fixture and the `world`/`capturing_memory` fixtures already exist in this file):
```python
@pytest.mark.asyncio
async def test_capability_chain_enforced_over_one_store(world, capturing_memory):
    """Arc-integration proof: labels -> roster capabilities + KG-uuid embodiment ->
    per-self JWT -> the real check_tool_access reading the SAME label store -> enforcement.

    Identity-uuid: KG uuid == engine uuid (one id behind gate AND executor), so a real
    mm_move reaches 200 and a label revocation in the one store flips allow (200) -> deny (403).
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    import httpx
    import memento.bonfires_client as bonfires_client
    from gateway.app import app
    from gateway.engine_auth import sign_jwt
    from gateway.room_driver import RoomDriver
    from memento.cxn.executor import EffectExecutor
    from memento.state.chain_mirror import NoopChainMirror

    repo = world["repo"]
    npc_id = world["npc_id"]
    room_a_id = world["room_a_id"]
    room_b_id = world["room_b_id"]

    kg_uuid = npc_id  # identity-uuid: KG uuid coincides with engine uuid

    # --- THE ONE STORE: a single mutable label-bearing entity dict, read by BOTH
    #     the roster spec-builder AND the gate.
    label_store: dict[str, dict] = {
        kg_uuid: {"uuid": kg_uuid, "name": "Guard", "labels": ["Character", "NPC"]}
    }

    class _IdentityProjection:
        """KG uuid == engine uuid (identity map), matching #4-B-A's live shape in identity mode."""
        def kg_uuid_for(self, engine_uuid: str) -> str | None:
            return kg_uuid if engine_uuid == npc_id else None

    class _GateKg:
        """The slice of the KG client check_tool_access uses, pointed at the one store."""
        def get_entity(self, uuid: str) -> dict | None:
            return label_store.get(uuid)

    # --- ROSTER HALF: capabilities + KG-uuid embodiment, sourced from the one store ---
    ar_client = httpx.AsyncClient(base_url="http://unused")  # _npc_self_spec never calls it
    try:
        driver = RoomDriver(
            repo=repo,
            agent_runtime_client=ar_client,
            bonfire_id="arc-test-bonfire",
            projection=_IdentityProjection(),
        )
        spec = driver._npc_self_spec(label_store[kg_uuid])
        assert spec["embodiment_agent_id"] == kg_uuid          # KG-uuid embodiment
        assert "mm_move" in spec["capabilities"]               # granted by NPC kit
        assert "mm_attack" in spec["capabilities"]
    finally:
        await ar_client.aclose()

    # --- GATE HALF: real check_tool_access over the SAME store; executor over InMemory world ---
    app.state.cxn_repo = repo
    app.state.cxn_executor = EffectExecutor(
        repo=repo, memory=capturing_memory, chain=NoopChainMirror()
    )
    token = sign_jwt(kg_uuid, type="npc", ttl_seconds=3600)
    auth = {"Authorization": f"Bearer {token}"}

    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    gw = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        with (
            patch.object(bonfires_client, "get_client",
                         lambda: SimpleNamespace(kg=_GateKg())),
            patch("gateway.routes.tools_http.broadcast_tool_event", new_callable=AsyncMock),
        ):
            # ALLOWED: gate reads ["Character","NPC"] -> mm_move allowed -> real move -> 200
            resp = await gw.post(
                "/v1/tools/mm_move", json={"destination": room_b_id}, headers=auth
            )
            assert resp.status_code == 200, resp.text
            moved = await repo.get_entity(npc_id)
            assert moved["location_uuid"] == room_b_id          # real state change

            # REVOKE the NPC kit in the ONE store -> roster source AND gate both lose mm_move
            label_store[kg_uuid]["labels"] = ["Character"]
            assert "mm_move" not in driver._npc_self_spec(label_store[kg_uuid])["capabilities"]

            # DENIED: gate now reads ["Character"] -> mm_move not allowed -> 403 (before executor)
            resp2 = await gw.post(
                "/v1/tools/mm_move", json={"destination": room_a_id}, headers=auth
            )
            assert resp2.status_code == 403
            assert resp2.json()["detail"]["error"] == "capability_missing"

        # IDENTIFIER INVARIANT: the JWT sub == the KG uuid the gate resolved == embodiment id
        assert kg_uuid == npc_id == spec["embodiment_agent_id"]
    finally:
        await gw.aclose()
```

- [ ] **Step 2 — confirm the monkeypatch target is correct before running.** `check_tool_access` does `from memento.bonfires_client import get_client` **inside** the function body (re-imported per call), so patching the attribute on the `memento.bonfires_client` module (`patch.object(bonfires_client, "get_client", ...)`) intercepts it. Verify by reading `engine_auth.py` L140–142 that the import is function-local (not a module-top binding into `engine_auth`'s namespace). If it is bound at `engine_auth` module top instead, patch `gateway.engine_auth.get_client`. Adjust the patch target to match what you read.

- [ ] **Step 3 — run, verify the test passes deterministically:**
```bash
cd "$WT" && PYTHONPATH=engine/src:gateway/src python3.12 -m pytest \
  gateway/tests/test_gm_room_loop_e2e.py::test_capability_chain_enforced_over_one_store -q
```
Expected: PASS. Run it **twice** to confirm determinism (no FCG here, but the e2e mutates module-level `app.state`; a second run catches ordering/state leaks). If the ALLOWED branch returns anything other than 200, read `resp.text`: a 403 there means the gate didn't read `label_store` (wrong patch target — revisit Step 2); a 500 means the executor didn't find the agent (the identity-uuid assumption broke — STOP and escalate). If the DENIED branch is not 403, the revocation didn't reach the gate (the adapter isn't reading the same `label_store` object).

- [ ] **Step 4 — run the full e2e file + a gateway smoke to confirm no regression:**
```bash
cd "$WT" && PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_gm_room_loop_e2e.py -q
cd "$WT" && PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_room_driver.py gateway/tests/test_cxn_repo_wiring.py -q
```
Expected: the two pre-existing e2e tests + the new one green; room_driver (11) + cxn_repo wiring green.

- [ ] **Step 5 — commit** (stage only the e2e test file):
```bash
git -C "$WT" add gateway/tests/test_gm_room_loop_e2e.py
git -C "$WT" commit -m "test(gateway): integrated capability-chain proof over one store"   # + trailer
```

---

# Movement 3 — docs

## Task 3 — Record the integration + the surfaced executor identifier gap

**Files:**
- Modify/Create: a short note in the mmori docs (match where #4-B-A recorded its note: `memento-mori/docs/cxn/2026-06-25-state-store-unification.md`; add a sibling `memento-mori/docs/cxn/2026-06-25-persona-arc-integration.md` or append a section to the existing note).

- [ ] **Step 1 — record:** a note covering (a) the two arcs are now consolidated on `persona/arc-integration` (off `opening/engine-core`, with `persona/npc-capabilities` merged); the merged `_npc_self_spec` carries BOTH `capabilities` and the KG-uuid `embodiment_agent_id`; (b) the integrated chain (labels → roster capabilities + KG-uuid embodiment → per-self JWT → real `check_tool_access` over one store → allow/deny enforcement) is proven at the test level by `test_capability_chain_enforced_over_one_store`, run in **identity-uuid mode** (KG uuid == engine uuid); (c) **SURFACED GAP (deferred):** the gate keys on the JWT `sub` (the KG uuid) while the `EffectExecutor` resolves the acting agent by **engine** uuid — a genuinely *distinct* KG-uuid sub would need a `kg_uuid→engine` resolution at the route/executor boundary that does not exist today; this is deferred to the live-stack slice (engine≠KG-uuid label parity itself stays covered by the `test_gate_label_parity.py` keystone). Also note still-deferred items: first production `RoomDriver` call site + scene-activation trigger; multi-service live-stack e2e (gateway + real `persona/service-revision` + KG); #4-C role→param binding; #4-B remaining (Mongo persistence, gate-reads-through-repo, opening-path repo unification, Approach A single-UUID).

- [ ] **Step 2 — commit** (stage only the doc file):
```bash
git -C "$WT" add docs/cxn/<file>   # path relative to the worktree root
git -C "$WT" commit -m "docs(persona): record arc integration + surfaced executor identifier gap"   # + trailer
```

---

## Verification (end-to-end)

1. **Merge consolidation (Task 1):** `gateway/tests/test_room_driver.py` → 11 passed (7 shared + 3 projection + 1 capabilities); the merged `_npc_self_spec` carries both `capabilities` and the KG-uuid `embodiment_agent_id`; engine state tests (keystone + projection) green.
2. **Integrated chain proof (Task 2):** `test_capability_chain_enforced_over_one_store` passes deterministically (twice): allowed `mm_move` → 200 with a real state change (`location_uuid == room_b_id`); after revoking the NPC kit in the one store, `mm_move` → 403 `capability_missing`; the JWT `sub` == the KG uuid the gate resolved == the roster `embodiment_agent_id`. The real `check_tool_access` runs (NOT patched); only `broadcast_tool_event` is stubbed.
3. **No regression:** the full gateway suite is green except the pre-existing, unrelated `test_round_callback.py::test_send_batch_to_matrix` failure (acknowledged, untouched).
4. **Whole-branch opus review:** the merge preserves BOTH features and all #4-B-A state infra + the `/v1/scenes` repoint; the proof is non-vacuous (the un-stubbed gate genuinely reads the one store — a label revocation in it flips 200→403; the allowed branch is a real move, not a stub); the identity-uuid scope and the surfaced executor identifier gap are documented; no `Any` in new signatures; no cross-service import; no whole-tree ruff churn.
5. **No live-stack run required.** The single-process e2e (real route + real gate + real executor over InMemory, one shared label store) covers the chain without a running kernel/agent-runtime. The deferred live run (Task 3 note) is the next slice.

## Out of scope (later slices)

- **First production `RoomDriver` call site** + the scene-activation trigger that constructs and drives it live.
- **Multi-service live-stack e2e**: gateway + real agent-runtime (`persona/service-revision`) + KG, proving the full chain including real FCG authoring/comprehension and a genuinely distinct KG uuid (with the `kg_uuid→engine` executor resolution).
- **#4-C** role→param binding (`SemanticFrame.roles` → deterministic tool args).
- **#4-B remaining**: Mongo-backed `StateRepository`, gate-reads-through-the-repo (single read path), opening-path repo unification, Approach A (engine uuid == KG uuid via SDK supplied-uuid).

## On approval

Execute via superpowers:subagent-driven-development on the worktree branch `persona/arc-integration` off `opening/engine-core` (T1→T3). Copy this plan to `memento-mori/docs/superpowers/plans/2026-06-25-persona-arc-integration.md` and commit (in the worktree) before dispatching Task 1. Run the Task 1 merge first; gate on the pre-flight feature check before Task 2.
