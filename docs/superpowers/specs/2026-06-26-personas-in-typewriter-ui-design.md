# Personas in the Typewriter UI — Design Spec

**Date:** 2026-06-26
**Status:** Approved (brainstorming) — ready for implementation plan
**Lineage:** integration branch `persona/typewriter-ui` off `opening/engine-core` (@ `8d54f7f`, carries persona P1/P2/P3); merges in `ui/typewriter-kg-map` (@ `6e53a96`, the typewriter/KG-map client).

## Context

Two pieces of work evolved on separate branches and never met:

- **The persona/scene stack (P1/P2/P3)** on `opening/engine-core` makes NPCs powered by the agent-runtime reachable through the **main game loop** (`POST /api/action` → `SceneCoordinator` → `RoomDriver` → agent-runtime), delivering NPC dialogue over the WebSocket as `tool_event/mm_npc_response` and NPC presence as `npc_joined`/`npc_left`.
- **The typewriter/KG-map UI** on `ui/typewriter-kg-map` is a new client for the **immersive opening** (prose typed out on the left, an accreting box-drawing room map on the right). It drives the **opening arc** (`POST /api/opening/{start,act}`) over plain HTTP request/response and **opens no WebSocket at all**.

These are parallel, non-overlapping surfaces: the persona machinery lives on `/api/action`, the typewriter UI lives on `/api/opening`. So a persona NPC cannot speak in the typewriter UI today. This spec bridges them **faithfully** — reusing the P1/P2/P3 machinery unchanged and giving the typewriter client a WebSocket so a real agent-runtime-backed NPC speaks into the opening, its line typed out in the prose panel and its presence shown in the room map.

**Goal:** A player in the typewriter opening UI types a message; a persona NPC at the opening room auto-activates (P1/P2/P3), its reply is broadcast over the WebSocket, and the typewriter client renders it — the NPC's line typed into the prose panel (distinct NPC styling) and the NPC shown as a glyph in the KG-map room pane. No persona/agent-runtime failure ever breaks the opening turn.

**Non-goals (this spec):** the opening→main-loop handoff to The Threshold; making the opening repo KG-backed; multi-NPC who-acts (addressed-name targeting); gating the NPC on "is this speech" (the chosen behavior is: **every** opening message triggers a persona turn, mirroring the main loop); turning the typewriter client into a full main-loop client. These are tracked as future work.

## Verified ground truth (from exploration)

- **The merge is conflict-free.** `git merge-tree opening/engine-core ui/typewriter-kg-map` produces a clean tree, **0 conflicts**. The branches are nearly disjoint: engine-core touches `gateway/`+`engine/` (never `client/`); the typewriter branch touches `client/` + adds one opening route. The only file edited on both sides — `gateway/src/gateway/routes/opening.py` — 3-way-merges cleanly (disjoint hunks). After merge: `cd client && bun install && bun run build` (the default `build` script targets `src/boot/opening-shell.ts`; dep set unchanged — `@chenglou/pretext`, lockfiles committed).
- **Opening room identity (stable constants):** `engine/src/memento/opening/deep_roads.py:25` `LOC_DEEP_ROADS = "507f1f77bcf86cd799439011"`, name `"the deep roads"` (`deep_roads.py:96`).
- **Opening arc:** `gateway/src/gateway/routes/opening.py` — `opening_registry: dict[str, TurnRouter]` (`:64`); `POST /opening/start` (`:154`) returns `{player_id (uuid4().hex), epigraph, location_id=LOC_DEEP_ROADS, location_name="the deep roads", description, exits[]}`; `POST /opening/act` (`:271`, signature `async def act_opening(req: ActRequest)` — **no `Request`**) runs `TurnRouter.handle(text, player_id)` and returns the raw `TurnOutcome`. The opening builds its **own per-player** `EventSourcedStateRepository` (`:185-196`); it never imports `ws_hub`/`SceneCoordinator`/`app.state`.
- **TurnRouter** (`engine/src/memento/cxn/turn_router.py:121`) produces player-action `StateUpdate`s / `clarify` / authored describe-prose — **no NPC dialogue, no broadcast**.
- **Persona path:** `routes/action.py:99` `submit_action` does `ws_hub.set_location(player_id, location)` → `SceneCoordinator.from_app_state(request.app.state).handle_player_message(player_id, location_name, action)`. `SceneCoordinator` (`scene_coordinator.py`): reads `app.state.cxn_repo`/`scene_registry`/`scene_locations`/`agent_runtime_client`; `handle_player_message` resolves NAME→uuid via the `scene_locations` cache (cache-first), `ensure_scene` auto-activates when a `kind=="character"` NPC is present + `agent_runtime_client` is set, broadcasts `npc_joined` on first activation (`:108`), then `RoomDriver.drive_turn` → broadcasts `{"type":"tool_event","tool":"mm_npc_response","npc":name,"summary":text,"location":location_name,"channel":"narrative"}` (`:162`). Persona failures are swallowed (logged no-op, never a 500).
- **WS broadcast** (`gateway/src/gateway/ws.py`): `broadcast_to_location(location_name, msg)` sends to every player whose `player_locations[player_id] == location_name`. The opening arc never calls `set_location`, so an opening player has no presence entry today.
- **Typewriter client:** default entry `client/src/boot/opening-shell.ts` — mounts a two-pane `UnifiedCanvas` (`prose` region = `ProseLayer`, `kgmap` region = `RoomViewportAdapter`→`MapRenderer`), drives an inline HTTP loop against `/api/opening/*`, **opens no WS**. `ProseLayer` (`client/src/layers/prose-layer.ts`) holds `Segment{kind: "epigraph"|"location"|"description"|"narration"|"prompt"}` and colors **all** prose uniformly `theme.colors.primary` (`:88`). `RoomViewportAdapter` (`client/src/layers/room-viewport.ts`) takes `setContents(roomUuid, things: {uuid,name}[])`. A complete WS handler already exists but is **unreachable** from this entry: `client/src/state/session.ts` `connectWebSocket()` (`:103`) + `client/src/message-handler.ts` (`tool_event`→`mm_npc_response` render `:253-271`, `npc_joined` `:216-228`, `npc_left` `:206-215`). NPC-dialogue visual model: `client/src/panels/narrative.ts:224-250` (gold `◆ Name` header + indented italic line with a `│` accent bar, `theme.colors.npc`).

## Architecture

Four components, each independently testable. The persona server stack (P1/P2/P3) is **reused unchanged**; the new code is a seed, a ~6-line hook in the opening route, and a client WS adapter.

### Component 1 — Integration branch (merge + build)

Cut `persona/typewriter-ui` off `opening/engine-core`; `git merge ui/typewriter-kg-map` (clean); `cd client && bun install && bun run build`. Deliverable: one branch whose gateway carries the persona stack and whose client is the typewriter UI, building to `app.js` from `boot/opening-shell.ts`. No code changes in this component — it is the substrate the rest builds on.

### Component 2 — Persona reachable in the opening room (server, gated seed)

Generalize `gateway/src/gateway/persona_seed.py` to seed a persona NPC into **`app.state.cxn_repo`** at the **Deep Roads** location, and prime the resolver cache:

- A new helper `seed_opening_persona(repo, cache) -> bool`, gated by env `PERSONA_OPENING_SEED`, parallel to the existing `seed_local_personas`/`provision_kg_personas`. It seeds (into `app.state.cxn_repo`):
  - a location entity `{uuid: "507f1f77bcf86cd799439011", kind:"location", name:"the deep roads", labels:["Location"], ...}`,
  - a persona NPC `{uuid:"opening-wanderer", kind:"character", name:"a dying adventurer", labels:["Character","NPC"], location_uuid:"507f1f77bcf86cd799439011", attrs:{hp,max_hp,inventory}}` (themed to the Deep Roads' existing dying-adventurer beat; exact name is a seed detail),
  - and records `cache["the deep roads"] = "507f1f77bcf86cd799439011"`.
- It follows the established backend-guard pattern: a no-op (returns False) when the repo backend doesn't match the seed's intent, never crashes startup, and (for the in-memory demo path) writes only to the in-memory `app.state.cxn_repo`.
- Lifespan (`app.py`): behind `if os.environ.get("PERSONA_OPENING_SEED")`, `await seed_opening_persona(app.state.cxn_repo, app.state.scene_locations)`, wrapped non-fatal (mirrors the existing seed calls).

**Why this works:** `SceneCoordinator`/`RoomDriver` only ever read `app.state.cxn_repo`. The opening's own per-player repo is never touched by the persona path — the two repos share the uuid string `507f1f77…` by coincidence but operate on disjoint stores (the opening's repo holds the player + room for `TurnRouter`; `app.state.cxn_repo` holds the persona NPC for the scene). `_has_persona_npcs("507f1f77…")` then finds the NPC, and `LocationResolver.uuid_for(player_id, "the deep roads")` hits the primed cache.

### Component 3 — Opening turn invokes the persona path (server)

`gateway/src/gateway/routes/opening.py` `act_opening`:

- Add `request: Request` to the signature.
- After `outcome = await turn_router.handle(req.text, req.player_id)` (unchanged), add a best-effort persona hook (wrapped so it never alters the opening response or raises):
  - `ws_hub.set_location(req.player_id, "the deep roads")` (idempotent; gives this player a presence entry so `broadcast_to_location("the deep roads", …)` reaches them). `ws_hub` from `app.state` / module import as the action route does.
  - `coordinator = SceneCoordinator.from_app_state(request.app.state)`; `await coordinator.handle_player_message(req.player_id, "the deep roads", req.text)`.
- The HTTP `ActResp` is **unchanged** — the player-action narration still returns in the response; NPC content arrives asynchronously over the WS. Every opening message triggers a persona turn (the chosen faithful behavior).
- Failure isolation: the whole persona hook is inside `try/except → log` so a missing `agent_runtime_client`, an agent-runtime outage, or a `SceneCoordinator` error degrades to silence — the opening turn always returns its `TurnOutcome`.

### Component 4 — Client: WebSocket + rendering

`client/src/boot/opening-shell.ts`:

- After `start()` yields `player_id`, open the WebSocket. Reuse `client/src/state/session.ts` `connectWebSocket()` + `setMessageHandler` (already implements `new WebSocket(\`${WS_URL}/${playerId}\`)`, JSON parse, reconnect-free forward). Set the typewriter's own handler rather than the full-build `createMessageHandler`.
- A small **typewriter WS adapter** (new, e.g. `client/src/state/opening-ws.ts`) translates the persona messages to the typewriter render surfaces — lifting the routing logic from `message-handler.ts`:
  - `tool_event` with `tool === "mm_npc_response"` → `prose.enqueue({kind:"npc-dialogue", text: msg.summary, speaker: msg.npc})` then redraw. (Optionally a preceding `{kind:"npc-name", text: msg.npc}` segment.)
  - `npc_joined` → `roomViewport.setContents(currentRoomUuid, [...currentThings, {uuid: msg.npc_id, name: msg.npc_name}])` so the NPC appears as a glyph; optional prose line "<name> is here."
  - `npc_left` → remove that NPC from the viewport's things.
  - `player_joined`/`player_left`/`presence`/other types → ignored.
- `ProseLayer` (`client/src/layers/prose-layer.ts`): extend `Segment.kind` with `"npc-name"` and `"npc-dialogue"` (and carry an optional `speaker`); branch the color in `render()` (currently hardcoded `theme.colors.primary` at `:88`) to use `theme.colors.npc` for NPC kinds, following the `panels/narrative.ts:224-250` model (gold name header + indented italic dialogue). Typewriter reveal behavior is unchanged (NPC lines type out like all prose).

## Data flow (one opening turn with a live NPC)

1. Player types in the typewriter input → `act(text)` → `POST /api/opening/act {player_id, text}`.
2. Server: `TurnRouter.handle` returns the player-action outcome (HTTP response, rendered in prose as today). Then the persona hook: `set_location(player_id, "the deep roads")` + `SceneCoordinator.handle_player_message(player_id, "the deep roads", text)`.
3. `ensure_scene("507f1f77…")` finds the seeded NPC, auto-activates a scene at the agent-runtime (first turn only) → broadcasts `npc_joined`; `RoomDriver.drive_turn` → agent-runtime persona reply → broadcasts `tool_event/mm_npc_response` to `broadcast_to_location("the deep roads", …)`.
4. The player's WS (connected at `/ws/{player_id}`, presence = "the deep roads") receives `npc_joined` (first turn) and `tool_event`.
5. Client adapter: `npc_joined` → NPC glyph in the KG-map pane; `tool_event/mm_npc_response` → the NPC's line typed into the prose pane with NPC styling.

## Error handling

- Persona hook in `act_opening` is fully `try/except → log`; the opening turn's HTTP response is never affected by persona/agent-runtime failure (mirrors `SceneCoordinator`'s own no-op-on-failure contract).
- `seed_opening_persona` is gated + non-fatal at boot; a no-op when its backend guard doesn't match; never writes to the production KG.
- Client WS: an unparseable or unknown message is ignored; a closed WS does not block the HTTP opening loop (the opening remains fully playable without the WS — personas are additive).

## Testing

- **Server (Component 2/3):** a route test — gated seed present, a real `app` with a stub agent-runtime serving `/turn`+`/open` (the `gateway/tests/test_action_persona_branch.py` pattern), a connected fake WS for the opening player at "the deep roads"; assert that `POST /api/opening/act` results in `npc_joined` + `tool_event/mm_npc_response` delivered to that player's WS, and that an agent-runtime failure leaves the opening `ActResp` intact (no 500). Plus a unit test that `seed_opening_persona` seeds the NPC at `507f1f77…` and primes `cache["the deep roads"]`, and no-ops on the wrong backend.
- **Client (Component 4):** `prose-layer` renders an `npc-dialogue` segment with NPC color/styling; the WS adapter routes `tool_event/mm_npc_response`→prose and `npc_joined`→viewport, and ignores presence messages. (bun tests, matching the existing `client/src/*.test.ts` style.)
- **Live browser demo (the actual goal):** with the backend stack up, `PERSONA_OPENING_SEED=1` + agent-runtime wired, boot the merged gateway, open the typewriter UI, type a message, and watch the dying adventurer's reply type into the prose pane + appear in the room map.

## Out of scope / future work

- Opening→main-loop handoff (carry the player into the persistent world / The Threshold via `/api/session` + `/api/action`).
- KG-backed opening repo (the opening stays in-process per-player; the persona NPC is seeded into `app.state.cxn_repo`).
- Multi-NPC who-acts (addressed-name targeting; `RoomDriver._resolve_actor_uuid` already supports it but `drive_turn` is called without `addressed_name`).
- Addressed-only / speech-gated triggering (deferred; chosen behavior is every-message).
- Making the typewriter client a full main-loop client.
