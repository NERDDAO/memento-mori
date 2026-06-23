# mmori GM-Room Coupling — Phase 1 (mm_move vertical proof) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (per repo/surface). Steps use checkbox (`- [ ]`) tracking.

**Goal:** Prove the GM-Room game loop end-to-end: a room-driver opens a room, a self-turn drives **`mm_move`** through agent-runtime's new inbound room route → the shared backend (per-self JWT) → memento-mori's re-exposed inbound HTTP tool-exec route → the real `EffectExecutor` → a durable `location_uuid` mutation, with the episode draining to the bonfire.

**Architecture:** Three surfaces joined by two HTTP contracts. Spec: `memento-mori/docs/superpowers/specs/2026-06-23-mmori-gm-room-coupling-design.md`. Consumes #1 (active episodes) + #2 (RoomRuntime/self-roster), both merged.

**Tech stack:** memento-mori (Python/FastAPI engine+gateway, `PYTHONPATH=src pytest`, asyncio auto); agent-runtime (Python 3.14/FastAPI/dspy, `uv run` from `services/agent-runtime/`, asyncio auto, py314 toolchain is correct there).

## Global Constraints
- **Branches:** memento-mori work on `gm-room/coupling` (off `opening/engine-core`, already has the spec). agent-runtime work on a NEW branch off `self-spine/slice-4-coupling` (where #2 merged, @ 553bdab) — call it `room-route/mmori-coupling`. NEVER `git add -A` — stage only touched files (both trees carry unrelated modified AGENTS.md/CLAUDE.md/skills).
- **Commit trailer (exact, every commit):**
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01TmmDb5v2f2mae5pmRWtqBZ`
- **UUIDs/opaque ids, never names.** `Self.embodiment_agent_id` / JWT `sub` / `actor_id` are opaque entity-UUID strings.
- **agent-runtime:** gates via `uv run` from `services/agent-runtime/`; no `Any` in src/ signatures; domain exceptions not `HTTPException`; env reads only in `app/config.py`; `asyncio_mode=auto`. Do NOT modify pyproject (py314 correct).
- **memento-mori:** gates via `PYTHONPATH=src python -m pytest` from `engine/` and `gateway/` (asyncio auto); per-file ruff; do NOT run blanket `ruff format src`.
- **Backward-compat:** everything additive + flag/route-gated. The per-NPC path (PR #123) and the existing `/mcp` transport stay intact; #3 ADDS routes, doesn't remove. `room_runtime_enabled` stays default-off.
- **Reuse, don't reinvent** (verified references):
  - gateway: `_run` (`gateway/src/gateway/cxn_tools.py:84`), `EffectExecutor.execute(cxn, caller_id, bindings)` (`engine/src/memento/cxn/executor.py:151`), `check_tool_access` + `validate_jwt`/`identity_from_authorization` (`gateway/src/gateway/engine_auth.py`), `move_cxn` (`gateway/src/gateway/cxn_tools.py` / `definitions.py`), `get_entities_at_location` (`engine/src/memento/state/repository.py:133`), `npc_registry` (`gateway/src/gateway/npc_registry.py`).
  - agent-runtime: `RoomManager.open_room`/`RoomRuntime` (`services/agent-runtime/src/app/runtime/room/`), `build_agent_pipeline` (`runtime/agent_runtime.py:77`, `cxn_enabled = "memento" in agent_skills`), `CxnGatewayClient.call_tool` (`adapters/cxn_gateway/client.py:40`), `_frame_for`/`take_turn`/`_add_utterance` (`runtime/room/room_runtime.py`), the existing `X-Internal-Token` route auth pattern.

---

# SURFACE 2 — memento-mori gateway: inbound HTTP tool-exec route (branch `gm-room/coupling`)

### Task G1: FastAPI Depends JWT verifier + `POST /v1/tools/{tool}` + `POST /v1/agents/{id}/activation`

**Files:**
- Create: `gateway/src/gateway/routes/tools_http.py` (the two routes + the `Depends` verifier)
- Modify: `gateway/src/gateway/app.py` (mount the new router on the existing FastAPI app, alongside the `/mcp` mount)
- Test: `gateway/tests/test_tools_http_route.py`

**Interfaces:**
- Produces (the contract agent-runtime's `CxnGatewayClient` already speaks):
  - `POST /v1/tools/{tool}` — header `Authorization: Bearer <jwt>`; body = the tool's args dict (e.g. `{"destination": "<room_uuid>"}` for `mm_move`); returns the `StateUpdate` dict (or `{"status":"rejected","cause":...}` for `ConstructionError`).
  - `POST /v1/agents/{agent_id}/activation` — header `Authorization: Bearer <jwt>`; body `{"cxn_ids": [...]}`; returns `{"unlocked": [...]}`. (Inert in the proof under `in_loop_activation`; build it for contract completeness.)
- Consumes: `validate_jwt` (returns claims or None), `check_tool_access(entity_id, tool_name)` (raises `HTTPException(403)` on capability miss), `_run(cxn, agent_id, bound_roles, summary)`, and the cxn lookup the MCP handlers use to map `tool` → `CxnDef` + build `bound_roles` (read `cxn_tools.py` for `mm_move`'s `bound_roles = {"agent": agent_id, "location": destination}`).

**Steps:**
- [ ] **G1.1 — Write the failing tests.** In `test_tools_http_route.py`, use `httpx.ASGITransport` against the gateway FastAPI app with a real `InMemoryStateRepository` seeded with two adjacent `kind="location"` rooms (an exit from A→B) and a `kind="character"` NPC in room A. Mint a real JWT via `sign_jwt(sub=<npc_uuid>, type="npc")`. Assert:
  - `POST /v1/tools/mm_move` with `{"destination": "<room_B_uuid>"}` + valid Bearer → 200, the NPC's `location_uuid` is now room B (read it back via the repo).
  - Missing/expired/garbage Bearer → 401 (verifier rejects).
  - A capability the NPC lacks (or a forbidden verb) → 403 (`capability_missing`).
  - `POST /v1/agents/{npc}/activation` with `{"cxn_ids":[]}` + valid Bearer → 200 `{"unlocked": [...]}`.
- [ ] **G1.2 — Run, verify RED** (`cd gateway && PYTHONPATH=src python -m pytest tests/test_tools_http_route.py -q` → fails: route 404 / module missing).
- [ ] **G1.3 — Implement** `tools_http.py`: a `require_jwt` `Depends` calling `validate_jwt(token)` → 401 on None, returns `claims["sub"]`; `POST /v1/tools/{tool}` resolves the `CxnDef` for `tool` (mirror the MCP handler's tool→cxn map; for the proof `mm_move` suffices but build the general lookup), builds `bound_roles` from the body + `entity_id`, calls `check_tool_access(entity_id, tool)` then `_run(cxn, entity_id, bound_roles, summary)`, returns its dict; map `ConstructionError`→`{"status":"rejected","cause":str(e)}`, `HTTPException(403)`→403. `POST /v1/agents/{id}/activation` records/returns the unlocked set (reuse whatever the MCP activation path uses; minimal record is fine). Mount the router in `app.py`.
- [ ] **G1.4 — Run, verify GREEN**, ruff the two files, commit (trailer).

---

# SURFACE 1 — agent-runtime: room route + enablement + public voice_turn (branch `room-route/mmori-coupling` off `self-spine/slice-4-coupling`)

### Task R1: enable memento on the room backend + public `RoomRuntime.voice_turn`

**Files:**
- Modify: `services/agent-runtime/src/app/runtime/room/room_manager.py` (pass `agent_skills=["memento"]` to `build_agent_pipeline` in `open_room`)
- Modify: `services/agent-runtime/src/app/runtime/room/room_runtime.py` (add public `voice_turn`)
- Test: extend `services/agent-runtime/tests/test_room_runtime.py` (or a new `test_room_runtime_voice_turn.py`)

**Interfaces:**
- Produces: `async RoomRuntime.voice_turn(self_id: str, intent: str, pipeline_input: PipelineInput) -> PipelineOutput` — calls `take_turn(self_id, intent, pipeline_input)` then routes the produced utterance via `_add_utterance(self_id, <output text>)` (mirror how A3's `open_episode` extracts `PipelineOutput.response_text` and routes the GM utterance). This is the public pair-method #2's final review flagged as missing (M3).
- Produces: `RoomManager.open_room` now builds a memento-enabled shared backend.

**Steps:**
- [ ] **R1.1 — Failing tests.** Assert: `voice_turn` calls `take_turn` AND routes the resulting utterance via the graph-memory client (`_add_utterance`) with `subagent_instance=self_id`; the original roster is intact after. For the enablement: assert `RoomManager.open_room` calls `build_agent_pipeline` with `agent_skills=["memento"]` (so `cxn_gateway` is wired, not None) — use a spy/recording on `build_agent_pipeline` or assert the resulting backend has cxn enabled. Mirror the existing room tests' fakes (`_RecordingBackend`, AsyncMock graph-memory).
- [ ] **R1.2 — RED** (`uv run pytest tests/test_room_runtime_voice_turn.py -q`).
- [ ] **R1.3 — Implement** `voice_turn` (take_turn + `_add_utterance(self_id, output.response_text)`); change `open_room`'s `build_agent_pipeline(...)` call to pass `agent_skills=["memento"]`. Keep both additive — `voice_turn` is new; the `agent_skills` arg only affects rooms (per-agent path unchanged).
- [ ] **R1.4 — GREEN**, `uv run ruff check src tests`, `uv run pyright src` (new errors only), commit (trailer).

### Task R2: inbound room route (`open` / `turn` / `close`)

**Files:**
- Create: `services/agent-runtime/src/app/modules/rooms/rooms_routes.py` (+ controller/dto as the codebase's vertical-slice convention requires; mirror an existing internal route module e.g. the inner-channel route from 4b)
- Modify: route registration + AppContext access to `room_manager` (already on AppContext from #2)
- Test: `services/agent-runtime/tests/test_rooms_routes.py`

**Interfaces:**
- Produces (the contract the mmori room-driver calls; internal-token auth, mirror the existing `X-Internal-Token` dependency):
  - `POST /v1/rooms/{room_id}/open` body `{bonfire_id, room_actor_id, gm_self:{id,embodiment_agent_id,names}, roster:[{id,embodiment_agent_id,names,seat:"LLM"}]}` → opens the room (idempotent) via `RoomManager.open_room`, adds each roster self via `add_self`, calls `open_episode`; returns `{source_episode_id}`.
  - `POST /v1/rooms/{room_id}/turn` body `{self_id, message|intent, correlation_id?}` → builds a `PipelineInput` from the message, calls `voice_turn(self_id, intent, pipeline_input)`; returns the routed output text/result.
  - `POST /v1/rooms/{room_id}/close` → `close_episode`; returns the close result.
- Consumes: `ctx.room_manager` (None when `room_runtime_enabled` off → route returns 503/`feature_disabled`).

**Steps:**
- [ ] **R2.1 — Failing tests** (ASGITransport against the agent-runtime app with `room_runtime_enabled=True` + a stub backend/LM): open→turn→close round-trip; the turn routes an utterance under the acting `self_id`; flag-off → 503; missing internal token → 401; unknown `self_id` → 404 (`SelfNotInRoster`).
- [ ] **R2.2 — RED.**
- [ ] **R2.3 — Implement** the route module (thin controller → `RoomManager`/`RoomRuntime`; domain exceptions, middleware maps to HTTP; no business logic in controller). Build the `PipelineInput` minimally (mirror A3's beat-input synthesis but with the player message as text).
- [ ] **R2.4 — GREEN**, ruff, pyright (new only), commit (trailer).

---

# SURFACE 3 — memento-mori room-driver (branch `gm-room/coupling`)

### Task D1: room-driver (room→location, roster build, trivial who-acts, calls agent-runtime room route)

**Files:**
- Create: `gateway/src/gateway/room_driver.py` (+ `gm_room_registry` beside `npc_registry.py`)
- Modify: the Matrix bridge entry point to call the driver on a player message (minimal wiring; the full Matrix-entry is Phase 2 — here expose a driver method the bridge/test calls)
- Test: `gateway/tests/test_room_driver.py`

**Interfaces:**
- Produces: `RoomDriver` with `async open_room(location_uuid)` (build roster from `get_entities_at_location(location_uuid)` minus the player → NPC self specs with `embodiment_agent_id=<entity uuid>`; pick/mint the GM self; POST agent-runtime `/v1/rooms/{location_uuid}/open`), `async drive_turn(location_uuid, player_message)` (trivial who-acts = the addressed/only NPC; POST `/v1/rooms/{location_uuid}/turn` with that `self_id`), `async close_room(location_uuid)`.
- Consumes: an HTTP client to agent-runtime's room route (new thin client; base url from gateway config/env; internal token).

**Steps:**
- [ ] **D1.1 — Failing tests** (against an ASGI-loopback stub of agent-runtime's room route that records calls): `open_room` builds the roster from a seeded in-memory repo (2 NPCs at a location) and POSTs `open` with both NPC self specs carrying `embodiment_agent_id`=the entity UUIDs; `drive_turn` picks the addressed NPC and POSTs `turn` with that `self_id`; `close_room` POSTs `close`.
- [ ] **D1.2 — RED.**
- [ ] **D1.3 — Implement** `room_driver.py` + `gm_room_registry` + the thin agent-runtime room-route HTTP client. Trivial who-acts (addressed NPC name→uuid via `npc_registry`, else the single NPC). Keep Matrix-bridge wiring to a single call site (a method the bridge invokes); do not rebuild message handling.
- [ ] **D1.4 — GREEN**, per-file ruff, commit (trailer).

---

# E2E — the game-loop proof

### Task E1: live multi-process `mm_move` smoke + deterministic stitched proof

**Files:**
- Create: `memento-mori/scripts/gm_room_smoke.py` (live multi-process smoke, mirrors `scripts/kernel_smoke.py` style)
- Create: `gateway/tests/test_gm_room_loop_e2e.py` (deterministic stitched proof)

**What it proves:** room-driver → agent-runtime room route → shared backend (stub LM deterministically emitting an `mm_move` tool call) → `CxnGatewayClient` (per-self JWT, `sub=<npc uuid>`) → gateway `/v1/tools/mm_move` → real `EffectExecutor` → the NPC's `location_uuid` mutates → an episode is produced (active-episode drain or the `memory.ingest_episode` call recorded).

**Steps:**
- [ ] **E1.1 — Deterministic stitched proof** (`test_gm_room_loop_e2e.py`): the two HTTP contracts are stitched with `ASGITransport` loopback. Because the two services live in different packages, run this from the **gateway** venv driving the real gateway app, and stand in for agent-runtime's room route + backend with a faithful harness that performs the *agent-side* behavior the contract guarantees: on `turn`, mint a per-self JWT (`sub=<npc uuid>`, same HS256 secret) and POST `/v1/tools/mm_move` to the REAL gateway app. Assert the real `EffectExecutor` moved the NPC and an episode was emitted. This proves the gateway half + the per-self-JWT contract deterministically, in CI.
- [ ] **E1.2 — Live multi-process smoke** (`scripts/gm_room_smoke.py`): boot the gateway app and (if reachable) a real agent-runtime instance with `room_runtime_enabled=True` + a stub LM, seed two adjacent rooms + an NPC, drive `open → turn(mm_move) → close` over real HTTP, assert the move + the episode. Skip-with-clear-message when agent-runtime/graph-memory aren't reachable (mirror the env-skip pattern). This is the full-loop proof when the stack is up.
- [ ] **E1.3 — Run** the deterministic test (must pass in CI) and the smoke (passes live / skips cleanly); commit (trailer).

---

## Sequencing & Right-sizing
- G1, R1, R2, D1 are largely independent (two contracts fixed above). Suggested order: G1 (gateway, self-contained) → R1+R2 (agent-runtime) → D1 (driver, needs the room-route contract) → E1 (stitches them). Each task ends with an independently testable deliverable; execute each surface via SDD (fresh implementer + per-task review; one final whole-branch review per branch).

## Verification
1. **Gateway:** `cd gateway && PYTHONPATH=src python -m pytest tests/test_tools_http_route.py tests/test_room_driver.py tests/test_gm_room_loop_e2e.py -q` green; `/mcp` path + existing tests untouched.
2. **agent-runtime:** `cd services/agent-runtime && uv run pytest tests/test_room_runtime_voice_turn.py tests/test_rooms_routes.py -q` green; `uv run ruff check src tests`; `uv run pyright src` (new errors only). Flag-off proof: `room_runtime_enabled` unset → room route 503, per-agent path unchanged.
3. **Game-loop proof:** `test_gm_room_loop_e2e.py` passes deterministically; `scripts/gm_room_smoke.py` passes against a live stack (or skips cleanly).

## Out of scope (→ Phase 2)
Real who-acts/turn-selection; retiring the per-NPC provisioning; `SceneDirector` beat coupling; room ownership/authz; multi-LM-per-self; cross-room reasoning; full Matrix message-entry wiring.
