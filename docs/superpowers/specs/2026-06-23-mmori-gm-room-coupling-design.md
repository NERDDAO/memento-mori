# mmori GM-Room Coupling — Design (Sub-project #3)

**Status:** Design / approved at the architecture + decomposition level (2026-06-23). The third and final sub-project of the GM-Rooms vision (`bonfires-ai-core-agentsvc/docs/superpowers/specs/2026-06-22-gm-rooms-active-episodes-vision.md`). #1 (active-episode kernel) and #2 (RoomRuntime + self-roster + FCG persona qualifier) are BUILT + MERGED (local) — this couples them to memento-mori.

**Repos touched:** `memento-mori` (gateway inbound tool-exec route + room-driver) and `bonfires-ai-core` `services/agent-runtime` (inbound room route + room-backend memento enablement). No new graph-memory/memory_kernel code (consumes #1's shipped active-episode routes).

---

## Goal

Make the GM-Room `RoomRuntime` (#2) the way memento-mori NPCs run: **one GM agent per room voices a roster of NPC "selves" on a single shared backend**, drives memento-mori tools through an inbound HTTP tool-exec route, and produces episodes into the bonfire via #1's active episodes — superseding the per-NPC-agent model (shipped in PR #123). The thinnest end-to-end proof is one room, a GM beat-turn, one NPC self executing **`mm_move`**, and that episode draining to the bonfire.

---

## Context: what already exists (verified 2026-06-23)

This sub-project is mostly **reconciliation + thin net-new orchestration**, not greenfield. The reconciliation matters because the two repos have drifted; the verified current state:

### agent-runtime side (the migration is nearly free here)
- `RoomRuntime`/`RoomManager` (#2, `services/agent-runtime/src/app/runtime/room/`) already: hold a roster of `Self`s, run `take_turn` (lease-gated) on ONE shared `DSPyAgentBackend`, and drive #1's active episodes (`open_episode` → GM beat-turn → `_add_utterance`; `close_episode`).
- **Per-self authentication already works by construction.** `_frame_for` (`room_runtime.py`) stamps `msg.agent_id = Self.embodiment_agent_id`; the shared backend mints the cxn JWT *per turn* from `msg.agent_id` (`_build_cxn_ctx`, `backend.py`), `sub = msg.agent_id`. So one GM voicing NPC X mints `sub=X`, voicing Y mints `sub=Y` — one backend, correctly per-self-authenticated, with **no signing change** (`sign_npc_jwt(sub, …)` is already fully parameterized).
- The cxn loop (`_comprehend_and_activate` → `push_activation`/`tools_for_turn` → ReAct → `mm_*` closure → `CxnGatewayClient.call_tool(bearer)`) is already wired into `DSPyAgentBackend`.
- **The two gaps:** (a) `RoomManager.open_room` calls `build_agent_pipeline` WITHOUT `agent_skills`, so `cxn_enabled = False` → the room backend gets `cxn_gateway=None` and the `mm_*` tools excluded; fix = pass `agent_skills=["memento"]`. (b) Each roster `Self.embodiment_agent_id` must hold the NPC's memento/KG entity UUID (the value the gateway understands as the NPC's identity), not the GM's id.
- `Self.embodiment_agent_id` is the only Self→entity mapping field; `_frame_for` already routes it to `msg.agent_id`.

### memento-mori gateway side (the drift)
- Tool-exec is now **FastMCP-only over `/mcp`**, gated by `_BearerAuthMiddleware` → `_current_identity` ContextVar → `check_tool_access(entity_id, tool_name)`. The legacy HTTP route layer (`POST /v1/tools/{tool}`, `POST /v1/agents/{id}/activation`) was **removed** ("phase 2 — MCP is the only transport").
- The agent-runtime `CxnGatewayClient` still POSTs to those removed HTTP routes over plain HTTP with a Bearer JWT. **So the per-NPC integration as built would 404 against the current `opening/engine-core` gateway** — the contract the client speaks no longer exists. #3 reconciles by re-exposing that HTTP contract (decided: inbound HTTP route on the gateway, not switching agent-runtime to MCP).
- The reusable core is intact: `_run(cxn, agent_id, bound_roles, summary)` → `EffectExecutor.execute(cxn, caller_id, bindings)` (`engine/src/memento/cxn/executor.py`); `check_tool_access` + `validate_jwt`/`sign_jwt`/`identity_from_authorization` (`gateway/src/gateway/engine_auth.py`). There is currently **no FastAPI `Depends` JWT verifier** — only the ASGI `_BearerAuthMiddleware` wrapping `/mcp`. That thin `Depends` is the net-new auth piece.
- **Corrections to stale notes:** no `deps.py`/`require_jwt`, no `activation_store`, no `active_construct_ids` kw-arg on `EffectExecutor.execute` (signature is `(cxn, caller_id, bindings)` positional). `npc_registry` (`agent_id → NpcEntry(name, location, kg_uuid)`) + `seed_from_db()` + the `register_npc`/`update_npc_location` hooks DO exist.

### memento-mori room/world model
- Rooms are `EntityDoc` with `kind == "location"`; occupants carry a mutable `location_uuid`. `get_entities_at_location(location_uuid)` returns occupants (NPCs/players, `kind != "item"`). `RoomManifest` snapshots a room. The Matrix bridge maps `location_name → Matrix room_id` (`bridge.location_to_room`) — one Matrix room per location, one narrator bot per room today.
- `mm_move` end-to-end: tool → `_check_tool_access` → `_run` → `EffectExecutor.execute` → Phase-1 `exit_exists` guard → Phase-2 `repo.move_entity(agent_uuid, destination_uuid)` → Phase-3 `memory.ingest_episode`. The only durable mutation is `entity.location_uuid`.

---

## Architecture

### The end-to-end turn (target state)
```
player msg in a Matrix room
  → memento-mori Matrix bridge: room → location_uuid; who-acts policy picks the acting NPC
  → memento-mori ROOM-DRIVER calls agent-runtime ROOM ROUTE (open / turn / close) over HTTP (X-Internal-Token)
      → RoomManager / RoomRuntime: GM beat-turn or NPC self-turn on the ONE shared backend
          → _frame_for stamps msg.agent_id = Self.embodiment_agent_id (acting NPC's KG UUID)
          → backend: comprehend(profile=that uuid) → activate → ReAct → mm_move tool closure
              → CxnGatewayClient.call_tool(tool="mm_move", bearer=<per-self JWT, sub=that uuid>)  [HTTP]
                  → memento-mori gateway INBOUND TOOL-EXEC ROUTE (net-new Depends JWT verifier)
                      → check_tool_access → _run → EffectExecutor.execute → repo.move_entity
      → RoomRuntime close_episode → #1 active-episode drain → persists to the bonfire
```

### Three work surfaces

**1 · agent-runtime — inbound room route** (`services/agent-runtime`, branch off the `self-spine/slice-4-coupling` line where #2 merged)
- New internal-only HTTP route module (existing `X-Internal-Token` auth), a thin controller over the `RoomManager` programmatic API (#2 deliberately shipped no routes; this is its deferred "inbound room route is #3's job"):
  - `POST /v1/rooms/{room_id}/open` → `RoomManager.open_room` (idempotent if already open) + `RoomRuntime.open_episode`. Body: `bonfire_id`, `room_actor_id`, the GM self spec, and the **roster** of NPC self specs (`embodiment_agent_id` = NPC KG UUID, `names`, seat=LLM). *mmori passes the roster in; agent-runtime never queries the world (stays world-agnostic).*
  - `POST /v1/rooms/{room_id}/turn` → a **new public `RoomRuntime.voice_turn(self_id, intent, pipeline_input) -> PipelineOutput`** that pairs `take_turn` with utterance-routing via `_add_utterance` (the public pair-method #2's final review flagged as missing — finding M3). Body names the acting `self_id` + the player intent/message.
  - `POST /v1/rooms/{room_id}/close` → `RoomRuntime.close_episode` (+ optional `close_room`).
- One-line enablement: `RoomManager.open_room` passes `agent_skills=["memento"]` to `build_agent_pipeline` so the shared backend has `cxn_gateway` wired and the `mm_*` tools un-excluded.

**2 · memento-mori gateway — inbound HTTP tool-exec route** (`memento-mori/gateway`, branch off `opening/engine-core`)
- Re-expose the contract `CxnGatewayClient` speaks, as FastAPI routes alongside the existing `/mcp` mount (MCP stays for direct callers):
  - `POST /v1/tools/{tool}` — verify JWT (net-new `Depends`), resolve `entity_id = claims["sub"]`, `check_tool_access(entity_id, tool)`, dispatch to the same `_run`/cxn machinery the MCP tool handlers use, return the `StateUpdate` dict.
  - `POST /v1/agents/{id}/activation` — verify JWT, record/return the unlocked tool set (mirrors the activation semantics the agent-runtime client expects). **Note:** under `in_loop_activation=True` the room backend gates tools locally (`tools_for_turn`) and never calls `push_activation`, so this route is **inert in the Phase-1 proof** — the proof's critical path is `POST /v1/tools/{tool}`. Build `/activation` to complete the contract, but the `mm_move` proof does not depend on it.
- **Net-new auth:** a FastAPI `Depends` JWT verifier wrapping `engine_auth.validate_jwt` (the ASGI middleware only covers `/mcp`). `sub` = acting NPC's KG UUID; reuse the existing HS256 `ENGINE` secret. No engine changes.

**3 · memento-mori room-driver** (`memento-mori`, Matrix-bridge side)
- Maps Matrix room → `location_uuid`; builds the GM-room roster from `get_entities_at_location`/`npc_registry` for that location (each NPC → a self spec with `embodiment_agent_id = kg_uuid`); runs the **who-acts policy**; calls agent-runtime's room route (open/turn/close). Owns the per-beat orchestration. A `gm_room_registry: dict[location_uuid → gm_entity_id]` slots beside `npc_registry`.

---

## Key decisions

- **GM identity.** The GM is a roster `Self` whose `embodiment_agent_id` = the room's narrator/GM KG entity. In Phase 1 its beat-turn uses #2's existing A3 beat-turn (an LLM narration utterance through the shared backend); **coupling the beat-turn to the engine's `SceneDirector` beat machinery is deferred** (Phase 2 / the immersive-opening arc, `2026-06-21-mmori-immersive-opening-design.md`). NPC selves are the only roster members that call gateway tools in the proof; the GM narrates.
- **Episodes → bonfire.** Reuses #2's `open_episode`/`close_episode`, which call #1's shipped active-episode client methods. **Deployment dependency (config, not code):** the graph-memory active-episode routes must be enabled (`GM_ACTIVE_EPISODE_ROUTES_ENABLED`) for the drain to land; absent that, the room still runs but episodes don't persist. The `room_actor_id` (room/GM actor = the active-episode owner) is the scope key — no new "room dimension" in the kernel.
- **Per-self JWT.** No signing change: `_frame_for` → `msg.agent_id = Self.embodiment_agent_id` → per-turn mint `sub = that uuid`. The gateway's `Depends` verifier treats `sub` as the acting entity. (Known limitation, accepted for #3: any holder of a self's token can act as that self — a caller↔room ownership/delegation check is Phase-2 hardening, the same open note 4b raised for the inner channel.)
- **who-acts (Phase 1 = trivial).** The mmori room-driver picks the addressed NPC (or the only NPC in the room). A real turn-selection policy is Phase 2.
- **Room route auth.** Internal-token service-to-service only. Ownership/authz hardening is Phase 2.
- **Roster source.** mmori builds and passes the roster; agent-runtime never queries memento-mori for world state.

---

## Phasing

**Phase 1 — thin vertical proof (this spec's plan target).** One room, GM beat-turn opens an episode, one NPC self drives **`mm_move`** through the new inbound route, episode drains to the bonfire. Driven through the *real* room route + gateway route, trivial who-acts, the per-NPC path left untouched alongside (gated off — `room_runtime_enabled` and the per-NPC provisioning coexist during transition).

**Phase 2 — full migration (later plan).** Real Matrix message-entry → room-driver; a real who-acts policy; full roster provisioning; retire the per-NPC agent/Matrix-bot provisioning in favor of GM-per-room; `SceneDirector` beat coupling; room ownership/authz hardening.

---

## Data contracts (Phase 1)

- **Room-open body (agent-runtime):** `{ bonfire_id, room_actor_id, gm_self: {id, embodiment_agent_id, names}, roster: [{id, embodiment_agent_id, names, seat: "LLM"}] }`.
- **Room-turn body:** `{ self_id, intent | message, correlation_id? }` → returns the routed `PipelineOutput` (narration/tool result).
- **Gateway tool-exec body (`POST /v1/tools/{tool}`):** the existing `CxnGatewayClient.call_tool` shape — `{ <tool args> }`, `Authorization: Bearer <per-self JWT>`. Response = `StateUpdate` dict (or `{status: "rejected", cause}` for `ConstructionError`).

---

## Error handling
- Gateway tool route: `capability_missing` (from `check_tool_access`) → 403; `ConstructionError` → `{status: "rejected", cause}` (200, matching `_run`); invalid/expired JWT → 401.
- Room route: `GraphMemoryUnavailable`/`GraphMemoryAuthError` from #1's client surface as domain errors → mapped by middleware; a failed turn does not corrupt the roster (already true from #2); unknown `self_id` → `SelfNotInRoster` → 404; duplicate `open` of an already-open room is idempotent.
- Room-driver: world-state read failures and unreachable agent-runtime/gateway surface to the Matrix narrator as a graceful in-room error, not a crash.

---

## Testing (Rule-16 per surface)
- **agent-runtime room route** vs a real `RoomManager` (recording backend / ASGI-loopback gateway stub) — asserts open→turn→close drives the roster and stamps the acting self's identity; `voice_turn` pairs `take_turn` + utterance-routing.
- **gateway inbound tool-exec route** vs the real `EffectExecutor` + `InMemoryStateRepository` (and a real JWT decoded back to `sub`) — asserts `mm_move` mutates `location_uuid`, capability-gate rejects an unauthorized verb, bad JWT → 401.
- **End-to-end `mm_move` proof** — mmori room-driver → agent-runtime room route → shared backend (stub LM) → gateway tool route → state change → episode present in the bonfire (active-episode drain). Skip-when-unavailable on the real backends (env-gated), recording-mode otherwise.

---

## Out of scope (→ Phase 2 / later specs)
Real who-acts/turn-selection policy; retiring the per-NPC agent + Matrix-bot provisioning; `SceneDirector` beat-machinery coupling; multi-LM-per-self / per-self memory partitions; cross-room reasoning beyond shared-bonfire awareness; room ownership/authz hardening; the full immersive-opening arc (its own plan, consumes this).
