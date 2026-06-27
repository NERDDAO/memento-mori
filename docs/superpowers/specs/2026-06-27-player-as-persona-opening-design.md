# Player-as-Persona Opening — Component B (Slice 1, Plan 5) — Design Spec

**Date:** 2026-06-27
**Status:** Design (brainstorming) — pending user review before planning
**Lineage:** branch `opening/cxn-catch` (memento-mori) — gateway-only; no bonfires-ai-core change (the agent-runtime already accepts an arbitrary `seat=LLM` self and forces no NPC-only gate — verified).
**Parent:** `2026-06-26-agent-driven-opening-cxn-catch-design.md` Component B. Builds on Plans 1–4 (reveal/deepen ECS, gateway `mm_look`, `cxn_fired`, `mm_look` free-in-manifest + innate + LOOK grammar).

## Goal

The player, on entering the Deep Roads, is a **self-agent** whose auto-issued "look around" turn comprehends → fires LOOK (the catch beat) → calls `mm_look` (draws the room, accretive) → narrates — all over the connected client's WebSocket. This is the piece that makes `mm_look` callable end-to-end on a *real* comprehend.

## Decisions (locked)

1. **The player is the scene's `gm_self`** (single-self scene, empty roster). The scene manifest is built from `gm_self`'s capabilities; `mm_look` is free so it's retained. No phantom narrator GM.
2. **Client-triggered, post-WS-connect.** A new `/opening/look` endpoint drives the player turn after the client's WebSocket is connected, so the `cxn_fired` / `room_draw` / narration events have a recipient.

## Verified ground truth (the corrections that shape this design)

- **The turn machinery picks an NPC responder; the player can never act today.** `RoomDriver._resolve_actor_uuid` (`room_driver.py:153-183`) returns only UUIDs from `_last_roster_uuids`, populated in `open_room` (`:200-211`) from entities filtered by `kind=="character"` AND `not _is_player(...)`. `drive_turn` POSTs `/turn` with `self_id = actor_uuid` (`:263-266`) and has **no** forced-`self_id` knob. → a new "drive player turn" call is required.
- **No path opens a scene with a chosen entity as `gm_self`.** `_gm_self_spec` (`room_driver.py:139-147`) always builds the synthetic `gm:<location_uuid>` with no `capabilities`. → a new "open player scene" call is required.
- **The opening player lives only in `opening_repos[player_uuid]` (`opening.py:191,196-206,250`), NOT in `app.state.cxn_repo`** (set at `app.py:65`). The gateway `mm_look` reads `app.state.cxn_repo` (`look_tool.py:92`, repo from `mcp_server.py:1298`). → `mm_look` for the opening player would degrade to "nothing to see" unless the player is also seeded into `app.state.cxn_repo`.
- **`mm_look` is innate (Plan 4) →** an entity labelled `["Character"]` already gets `mm_look` from `get_allowed_tools`. No new label needed; the player just needs to *exist* in `app.state.cxn_repo` at the Deep Roads.
- **The agent-runtime imposes no NPC-only / seat gate** on scene-open roster members or the turn path (verified Plan 5 exploration of `scene_runtime`/`scene_manager`): a `seat="LLM"` human-less player self is accepted as `gm_self` and can take turns. So Component B is **gateway-only**.
- **`/opening/act` drives NPC turns (or the legacy TurnRouter)** (`opening.py:268-310`) — it is NOT reusable to make the player act. Component B adds a distinct `/opening/look` path.

## Architecture (the corrected flow)

```
[client] name box → POST /api/opening/start {player_name}
   ├─ (existing) seed player into opening_repos[player_uuid]; register TurnRouter
   ├─ B1: ALSO seed player into app.state.cxn_repo at LOC_DEEP_ROADS (labels ["Character", ...] → mm_look innate)
   └─ B2: open a scene with the player as gm_self:
          POST /v1/scenes/{LOC_DEEP_ROADS}/open
             gm_self = SelfDto(id=player_uuid, seat="LLM",
                               capabilities=sorted(get_allowed_tools(player_labels)) ∋ mm_look)
             roster = []   (single-self scene)
[client] connect WebSocket (existing opening WS)
   └─ B4: POST /api/opening/look {player_id}
          └─ B3: drive_player_turn(LOC_DEEP_ROADS, player_uuid, "look around"):
                   POST /v1/scenes/{LOC_DEEP_ROADS}/turn {self_id=player_uuid, message="look around"}
                     ── inside the agent-runtime player-self ReAct turn ──
                     ├─ comprehend "look around" → applied_cxn_ids ∋ mm.look.v1
                     │     └─▶ turn response fired_cxns=["mm.look.v1"]  (Plan 3)
                     ├─ ReAct calls mm_look (gateway tool; player now resolvable in app.state.cxn_repo)
                     │     ├─▶ reveal/deepen the room ECS → WS room_draw delta  (Plan 2)
                     │     └─▶ returns the delta summary into the trajectory
                     └─ LLM narrates → response_text
                 gateway relays:
                   ├─ cxn_fired WS  ("◇ caught: LOOK")  (Plan 3, via fired_cxns)
                   └─ narration WS  (mm_npc_response-style, attributed to the PLAYER self)
```

## Components

### B1 — player in `app.state.cxn_repo` (store reconciliation)
In `/opening/start`, after the existing per-player seed, ALSO seed the player into `app.state.cxn_repo` at `LOC_DEEP_ROADS`: an `EntityDoc` `{uuid: player_uuid, name, kind:"character", labels:["Character"], location_uuid:LOC_DEEP_ROADS, attrs:{}, is_dead:False}`. This is what lets gateway `mm_look` resolve the player's location. Best-effort/non-fatal if `app.state.cxn_repo` is absent (e.g. a degraded boot). The player carries no `reveal_level`, so it is NOT a reveal candidate (correct — the player isn't a thing you "look at").

### B2 — open the player scene (player as `gm_self`)
A new gateway helper `open_player_scene(app_state, location_uuid, player_uuid, player_name, player_labels) -> bool` that POSTs `/v1/scenes/{location_uuid}/open` (via the existing agent-runtime httpx client / `build_agent_runtime_client`) with:
- `bonfire_id = app_state.bonfire_id`
- `scene_actor_id = player_uuid`
- `gm_self = {id: player_uuid, embodiment_agent_id, names:[player_name], seat:"LLM", capabilities: sorted(get_allowed_tools(player_labels))}` (capabilities ∋ `mm_look`)
- `roster = []`
Idempotent-ish (re-open is tolerated server-side); best-effort/non-fatal at start (a persona/agent-runtime outage must not break `/opening/start`). Called from `/opening/start` after B1.

### B3 — drive the player turn (forced `self_id`)
A new gateway call — either `RoomDriver.drive_self_turn(location_uuid, self_id, message) -> dict` or a standalone helper — that POSTs `/v1/scenes/{location_uuid}/turn {self_id, message}` with a **caller-supplied `self_id`** (the player), bypassing `_resolve_actor_uuid`, and returns the turn dict (incl. `fired_cxns`, `response_text`, `should_respond`, plus `self_id`). Reuses the same httpx client + headers as `drive_turn`. (`drive_turn`'s NPC-resolution path is unchanged.)

### B4 — `/opening/look` endpoint (client-triggered orchestration)
A new route `POST /api/opening/look {player_id}` that, for an opening player whose scene is open:
- resolves `LOC_DEEP_ROADS`,
- calls B3 `drive_self_turn(LOC_DEEP_ROADS, player_id, "look around")`,
- broadcasts `cxn_fired` (reuse `SceneCoordinator._broadcast_cxn_fired`-style logic / the `CXN_DISPLAY_NAMES` map) for each `fired_cxns` id,
- broadcasts the narration over WS as a player-attributed line (the persona-in-typewriter adapter renders `mm_npc_response` → prose; attribute it to the player name),
- returns `{ok, fired_cxns, response_text}`.
`mm_look`'s own `room_draw` broadcast happens inside the tool (Plan 2), so the draw reaches the client without extra plumbing. Best-effort; a turn failure returns a benign payload (never a 500), and the room can still be drawn by a fallback (deferred).

### B-client — trigger the look (client)
After the opening WS connects (existing `connectOpeningWs`), the client POSTs `/api/opening/look {player_id}` once. The resulting `cxn_fired` (catch beat), `room_draw` (map), and narration (prose) render via the existing handlers (Plans 2–3 + the persona adapter). *(The cinematic intro that gates the name box is Plan 6; B-client here is just the one-shot look trigger.)*

## Error handling

- **B1 seed failure** (no `app.state.cxn_repo`): logged, non-fatal; `mm_look` later degrades to "nothing to see" rather than crashing.
- **B2 open failure** (agent-runtime down): logged, non-fatal; `/opening/start` still returns; `/opening/look` then no-ops gracefully (no open scene).
- **B3/B4 turn failure** (kernel/agent-runtime hiccup): `/opening/look` returns a benign `{ok:false}`; no `cxn_fired`/narration; never a 500. The opening stays playable.
- **No comprehension match** (kernel grammar missing / closure-balloon): no LOOK fires → no catch beat; the ReAct agent may still call `mm_look` (it's available) and draw the room, or degrade. Plan 4 (grammar authoring) de-risks the match.

## Testing

- **B1:** `/opening/start` seeds the player into `app.state.cxn_repo` at `LOC_DEEP_ROADS` (assert `get_entity(player_uuid).location_uuid == LOC_DEEP_ROADS`); non-fatal when the repo is absent.
- **B2:** `open_player_scene` POSTs `/open` with `gm_self.id == player_uuid`, `gm_self.seat == "LLM"`, `mm_look` in `gm_self.capabilities`, empty roster (assert against a stubbed agent-runtime `/open`).
- **B3:** `drive_self_turn` POSTs `/turn` with the supplied `self_id` (not an NPC-resolved one) and returns the turn dict incl. `fired_cxns` (stubbed `/turn`).
- **B4:** `/opening/look` drives the player turn and broadcasts `cxn_fired` + a player-attributed narration (assert WS broadcasts via a fake hub + stubbed turn carrying `fired_cxns`).
- **Integration / live demo (bring-up):** with the KG stack + `OPENING_AUTHOR_LOOK_GRAMMAR` set, name → start → connect → `/opening/look` → "◇ caught: LOOK" + room drawn + LLM narration in prose; re-look accretes (reveal → deepen).

## Out of scope (Plan 6 / later)

- The cinematic intro (epigraph fade + name box) and the client `room_draw` glyph rendering refinement — Plan 6.
- Multi-NPC who-acts, `npc_left`, TTL scene eviction.
- The opening→main-loop handoff; cross-session persistence of reveal-state.
- Reconciling the legacy `/opening/act` TurnRouter path with the player-self path (they coexist; the player-self path is additive).

## Open question for review

The player-self ReAct turn relies on the LLM choosing to call `mm_look` given the utterance "look around" + `mm_look` available. The comprehension firing LOOK (catch beat) is deterministic (grammar authored), but the *tool call* is the agent's decision. If empirically the agent doesn't reliably call `mm_look`, a fallback (the gateway directly invokes the reveal on the look turn) would make the draw deterministic — noted as a possible Plan-5 hardening, not built up front.
