# Typewriter + KG-Map UI — Design (Phase 1: the layered-canvas baseline)

**Date:** 2026-06-23
**Status:** Design approved; spec for review.
**Branch:** `ui/typewriter-kg-map` (off `opening/engine-core`).

## 1. Why this exists

The immersive opening has an engine + a live gateway (`/api/opening/{start,act}`) and a working KG substrate (`KgProjection` → the bonfires SDK → graph-memory → Neo4j, verified end-to-end 2026-06-23). What it lacks is a **face**.

This spec designs that face — and makes it the **new baseline** for the whole client: a single z-composited canvas where prose types itself out as you play and a text-based map **accretes as you say things** (each room and the things `LOCATED_IN` it appearing as the knowledge graph lights up). The client boots into this layered shell, and every future capability is **added as a layer, slowly** — not bolted on as another panel.

The whole play UI is reimagined in this idiom, which is too large for one spec. This spec covers **Phase 1: the layered-canvas baseline** — the compositor boot + the two base layers (prose, map) + the input loop, proven on the opening arc. Everything else (inventory, quests, combat, NPC dialogue) becomes a later layer on this same baseline.

## 2. Decisions locked in brainstorming

1. **Map mechanic = layered.** A spatial skeleton of rooms/exits, with the entities discovered in each room **docked inside** that room's box. Saying/looking grows both places and things.
2. **Map data source = live view of the KG.** "Things in a room" are read from the knowledge graph (the `LOCATED_IN` edges `KgProjection` writes). The KG is the source of truth for room *contents*; the map renders the lit subgraph. (Room **adjacency** comes from the room manifest — see §6.)
3. **Input = free text + affordances.** The player types natural language (the soul of "say things"); the UI also surfaces the legible moves (exits, takeable things) as chips. When comprehension returns `clarify`, those chips appear as suggestions, never a dead end.
4. **Rendering model = z-composited layers on one canvas.** Reuse the existing `canvas/unified-canvas.ts` (a CharCell grid = z0 base) and `canvas/modal-manager.ts` (stacked overlays = z1+). Every capability is a **Layer**: *base layers* render CharCell regions into the z0 grid; *overlay layers* are ModalManager modals at z1+ that composite over and dim beneath. The Phase-1 layout — prose │ map — is **two base layers tiling z0** (prose left, map right); summonable capabilities composite over later.
5. **This UI is the new baseline.** The client boots into a slim layered shell (compositor + prose + map), **not** the current panel-heavy `app.ts`. The existing panel/modal files stay in the tree but are no longer the default boot; they get re-expressed as layers, incrementally, in later phases.
6. **Growth = register a layer ("add slowly").** New capabilities (codex, inventory, dialogue — the existing `ui/*-renderer.ts` are seeds) arrive as new layers on the compositor, one at a time, without touching the base loop. The `Layer` contract is the single extensibility seam.
7. **Code home = `memento-mori/client/`**, reusing `state/session.ts` + gateway transport, `UnifiedCanvas` / `ModalManager` / `renderer/canvas-text.ts`, and the build.
8. **Scope = Phase 1 only**: the compositor baseline + prose & map base layers + the input loop on the opening arc. Later phases in §10.

## 3. What the gateway already gives us (consumed contracts)

From `gateway/src/gateway/routes/opening.py`:

- `POST /api/opening/start` → `StartOpeningResponse`: `{player_id, epigraph, location_id, location_name, description, exits: [ {direction, ...destination...} ]}`. The KG seed (player + room entities + `LOCATED_IN`) happens server-side during `/start` (un-gated).
- `POST /api/opening/act` body `{player_id, text}` → the `TurnOutcome` dict: `{status, narration?, won?, reason?, ...}`. Observed statuses: `narrated` (look), `executed` (take), `won` (final beat), `clarify` (no comprehension match). On `won`, the per-player session is dropped (a subsequent `/act` → 404).

These shapes are the integration boundary; the implementation plan pins exact field names by reading the route + `room_manifest`.

## 4. Architecture — the layered-canvas baseline, inside `memento-mori/client/`

Reuse the rendering substrate that already exists: `canvas/unified-canvas.ts` (CharCell grid + z0 base), `canvas/modal-manager.ts` (z1+ stacked overlays + per-z hit regions), `renderer/canvas-text.ts` (text into cells), `state/session.ts` + gateway transport, and the build. Phase 1 adds a thin `Layer` contract, two base layers, the orchestrator, a read-port, a slim baseline boot, and one gateway read route.

```
client/src/
  canvas/layer.ts        (new)  — Layer contract (unifies base + overlay)
  layers/prose-layer.ts  (new)  — base layer (z0, left): typewriter prose into its CharCell region; skippable; echoes input
  layers/map-layer.ts    (new)  — base layer (z0, right): accreting {rooms,exits,current} → layered box-drawing map
  state/opening-loop.ts  (new)  — orchestrator: /start, /act → routes to the layers; clarify → chips
  state/kg-read-port.ts  (new)  — KgReadPort: getRoomContents(roomUuid) → things[] via the gateway read route
  boot/opening-shell.ts  (new)  — THE NEW BASELINE boot: build UnifiedCanvas, register prose+map base layers, start the loop
gateway/src/gateway/routes/opening.py (modify)
  + GET /api/opening/room/{room_uuid}/contents — server-side SDK get_edges(incoming) → things[]
```

**The `Layer` contract** (`canvas/layer.ts`) unifies base and overlay so the compositor treats them uniformly and the system grows by registration:
- `{ id, z, region, visible, render(grid), onInput?(event) }`.
- **Base layer** — owns a region of the z0 CharCell grid; `render(grid)` writes its cells; takes input when focused. Phase 1: `ProseLayer` (left), `MapLayer` (right).
- **Overlay layer** — backed by a `ModalManager` modal at z1+, composites over the base and dims beneath. **None in Phase 1** — this is the seam future capabilities plug into (the existing `ui/codex-renderer.ts` / `ui/inventory-renderer.ts` adapt to this contract incrementally).
- The compositor renders bottom-up (z0 base layers, then z1+ overlays); input routes to the top focused layer (reuse `ModalManager`/`hitRegistry` z-routing).

Each unit, one job, narrow interface:

- **`ProseLayer`** — *does:* renders a queue of text segments character-by-character into its CharCell region; instant-completes the current segment on keypress; echoes the player's submitted input line. *Interface:* `enqueue({text, kind})`, `skip()`, `onInputSubmit(cb)`. *Depends on:* `canvas-text` only (no game knowledge).
- **`MapLayer`** — *does:* holds an accreting model `{rooms: Map<uuid,Room>, exits: Edge[], currentRoom}` (`Room = {uuid, name, things: Thing[], entered}`) and renders it as the layered box-drawing map (current room marked, unentered rooms as `?`, things docked inside each room). *Interface:* `visitRoom(room, exits)`, `setContents(roomUuid, things[])`, `render(grid)`. *Depends on:* the CharCell grid only; contents are pushed in by the loop.
- **`opening-loop`** — *does:* the only unit that talks to the gateway. Calls `/start`, then per input calls `/act`; routes `narration` → `ProseLayer`, `location/exits` → `MapLayer.visitRoom` + a `KgReadPort` read → `MapLayer.setContents`, and `clarify` → affordance chips (from the map's exits + the room's takeable things). *Interface:* `start()`, `submit(text)`. *Depends on:* gateway transport, the two layers, `KgReadPort`.
- **`KgReadPort`** — *does:* `getRoomContents(roomUuid) → Thing[]` via `fetch` to the gateway read route, so `MapLayer` is testable against a fake. *The browser never holds the graph-memory internal token* — the gateway route holds it server-side.
- **`opening-shell` (the new baseline boot)** — builds `UnifiedCanvas`, registers `ProseLayer` + `MapLayer` as z0 base layers (split regions), wires input → `opening-loop`, and calls `start()`. This replaces the panel-heavy `app.ts` as the client's default entry.

## 5. The render loop (data flow)

```
start()
  POST /start
  → ProseLayer.enqueue: epigraph → location_name → description     (types out)
  → MapLayer.visitRoom(currentRoom, exits)                         (skeleton appears)
  → KgReadPort.getRoomContents(currentRoom) → MapLayer.setContents (things dock in)

submit("take the iron blade")
  POST /act {player_id, text}
  status=narrated|executed
    → ProseLayer.enqueue(narration)
    → KgReadPort.getRoomContents(currentRoom) → MapLayer.setContents (new things light up)
  status=clarify
    → ProseLayer.enqueue(soft prompt)
    → render chips: exits (from MapLayer) + takeable things (from KG contents)
  won=true
    → ProseLayer.enqueue(coda); loop ends (session dropped server-side)
```

On a move, `/act` (or the manifest in the response) yields the new `location_id` + `exits`; the loop calls `MapLayer.visitRoom(newRoom, exits)` (accreting the skeleton) then reads its contents.

## 6. The map's KG read — the one nuanced split

The map is a live view of the KG, but two pieces come from two places, deliberately:

- **Room contents (things)** → the **KG**, via `get_edges(roomUuid, direction="incoming")` (the `LOCATED_IN` edges), behind the new gateway read route `GET /api/opening/room/{room_uuid}/contents`. This is the lit subgraph and the source of truth for what's in a room.
- **Room adjacency (exits / spatial layout)** → the **room manifest** the gateway already returns; the client accretes the spatial skeleton from the `exits` it sees as it visits rooms. (`KgProjection` does not currently write room→room exit edges; promoting them is a later unification, out of scope.)
- **Fog-of-war** → Phase 1 is single-player / single-session, so the client tracks visited rooms locally in the `MapLayer` model. A real multi-player "known subgraph" KG query is deferred.

## 7. Robustness / degradation

Comprehension is currently unreliable (returns `clarify` without a working FCG + indexed world), so degradation is a first-class concern:

- **`clarify` is a normal path**, not an error: soft prompt + chips (exits + takeable things). The player is never stuck.
- **KG read fails / empty**: `MapLayer` still draws the spatial skeleton (rooms + exits) with empty interiors; logged, never thrown to the UI.
- **Typewriter is always skippable** (keypress instant-completes the current segment) so prose never feels slow or blocking.
- **`won` then `/act` → 404**: the loop treats a post-`won` 404 as "session ended", not an error.

## 8. Testing

- **`prose-layer.ts`** — unit, no backend: enqueue segments, assert progressive then complete render; `skip()` instant-completes; input submit fires the callback.
- **`map-layer.ts`** — unit: feed a model, assert the box-drawing output contains the rooms, current-room marker, unentered rooms as `?`, and docked things; `setContents` re-renders with new things.
- **`opening-loop.ts`** — unit against a **fake gateway + fake `KgReadPort`**: `narration` → prose layer, `location/exits` → `MapLayer.visitRoom` + a contents read, `clarify` → chips from exits + contents.
- **`canvas/layer.ts` + `opening-shell`** — unit: registering two base layers composites both regions on one canvas; input routes to the focused layer. (Overlay z-stacking is exercised when the first overlay layer lands in a later phase.)
- **Gateway read route** — unit against a fake SDK/projection: `GET .../room/{uuid}/contents` returns the `LOCATED_IN` things; 404 on unknown room.
- **One thin live smoke** against the running gateway + graph-memory (the stack stood up 2026-06-23): `start()` → the map shows "the deep roads" with its `LOCATED_IN` things read from the KG. Skips cleanly if the gateway env isn't set (mirrors `opening_smoke.py`).

## 9. File structure summary

| File | New/Mod | Responsibility |
|---|---|---|
| `client/src/canvas/layer.ts` | new | `Layer` contract unifying base + overlay layers |
| `client/src/layers/prose-layer.ts` | new | Base layer (z0): typewriter prose, skip, input echo |
| `client/src/layers/map-layer.ts` | new | Base layer (z0): accreting model → layered box-drawing map |
| `client/src/state/opening-loop.ts` | new | Orchestrator: gateway `/start`+`/act` → layers + chips |
| `client/src/state/kg-read-port.ts` | new | `getRoomContents(uuid)` via the gateway read route |
| `client/src/boot/opening-shell.ts` | new | New baseline boot: UnifiedCanvas + register prose/map layers + start loop |
| `gateway/src/gateway/routes/opening.py` | mod | `+ GET /api/opening/room/{room_uuid}/contents` (server-side `get_edges`) |
| tests per unit + read route + one live smoke | new | as in §8 |

Reused as-is (not modified): `canvas/unified-canvas.ts`, `canvas/modal-manager.ts`, `renderer/canvas-text.ts`, `state/session.ts` + transport.

## 10. Out of scope (later phases, noted not specced)

- Adapting the **existing overlay renderers** (`ui/codex-renderer.ts`, `ui/inventory-renderer.ts`, `ui/dialog-renderer.ts`) to the `Layer` contract as z1+ overlay layers — the first proof of "add a capability = add a layer", but a later phase.
- Swapping the opening HTTP loop for the **WS game loop** for ongoing (post-opening) play.
- Reimagining **inventory / quests / combat / NPC dialogue** as layers.
- **Deleting** the old panel boot (`app.ts` panel stack, `panels/worldmap.ts`, `map.ts`, …). Phase 1 only changes the *default boot* to `opening-shell`; the old files stay dormant until re-expressed as layers.
- Promoting **room adjacency to KG edges** and a real multi-player **fog-of-war** known-subgraph query.
- Fixing the kernel **`/comprehend`** (working FCG + indexed world). The UI degrades gracefully until that lands; it does not fix it.
- Visual polish beyond the box-drawing/typewriter idiom (theming, animation tuning).

## 11. Relationship to other specs

Consumes the opening arc (`2026-06-23-kg-native-event-sourced-opening-design.md`) and the KG-CRUD backend (`bonfires-ai-core/.../2026-06-23-kg-crud-graph-memory-design.md`, the `get_edges`/`LOCATED_IN` path this map reads). Builds on the unified-canvas work (single full-screen CharCell canvas, box-drawing borders, z-layered modals, map compositing) — this spec turns that compositor into the client's default baseline and the `Layer` contract its growth seam. The "lit subgraph" framing is the UI expression of the same KG the world-ledger PoC and GM-rooms work write into.
