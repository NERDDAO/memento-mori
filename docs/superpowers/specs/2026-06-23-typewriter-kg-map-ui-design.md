# Typewriter + KG-Map UI — Design (Phase 1: the core loop)

**Date:** 2026-06-23
**Status:** Design approved; spec for review.
**Branch:** `ui/typewriter-kg-map` (off `opening/engine-core`).

## 1. Why this exists

The immersive opening has an engine + a live gateway (`/api/opening/{start,act}`) and now a working KG substrate (`KgProjection` → the bonfires SDK → graph-memory → Neo4j, verified end-to-end 2026-06-23). What it lacks is a **face**. This spec designs that face: a typewriter-pretext UI where prose types itself out as you play and a text-based map of the world **accretes as you say things** — each room and the things `LOCATED_IN` it appearing as the knowledge graph lights up.

The long-term intent is to reimagine the **whole** play UI in this typewriter+map idiom. That is too large for one spec, so this spec covers only **Phase 1: the core loop**, proven on the opening arc. Once the primitive feels right, later phases pour the rest of play (ongoing WS loop, inventory, quests, combat) through it.

## 2. Decisions locked in brainstorming

1. **Map mechanic = layered.** A spatial skeleton of rooms/exits, with the entities discovered in each room **docked inside** that room's box. Saying/looking grows both places and things.
2. **Map data source = live view of the KG.** "Things in a room" are read from the knowledge graph (the `LOCATED_IN` edges `KgProjection` writes). The KG is the source of truth for room *contents*; the map renders the lit subgraph. (Room **adjacency** comes from the room manifest — see §6.)
3. **Input = free text + affordances.** The player types natural language (the soul of "say things"); the UI also surfaces the legible moves (exits, takeable things) as chips. When comprehension returns `clarify`, those chips appear as suggestions, never a dead end.
4. **Layout = split prose │ map**, both always visible. Prose left, map right.
5. **Code home = the existing `memento-mori/client/`** TS app — reuse its session/transport/build; add new units + a new primary split layout. The old panel layout is untouched in Phase 1 (retired in a later phase).
6. **Scope = Phase 1 only** (the core loop on the opening arc). Later phases are noted in §10, not specced here.

## 3. What the gateway already gives us (consumed contracts)

From `gateway/src/gateway/routes/opening.py`:

- `POST /api/opening/start` → `StartOpeningResponse`: `{player_id, epigraph, location_id, location_name, description, exits: [ {direction, ...destination...} ]}`. The KG seed (player + room entities + `LOCATED_IN`) happens server-side during `/start` (un-gated).
- `POST /api/opening/act` body `{player_id, text}` → the `TurnOutcome` dict: `{status, narration?, won?, reason?, ...}`. Observed statuses: `narrated` (look), `executed` (take), `won` (final beat), `clarify` (no comprehension match). On `won`, the per-player session is dropped (a subsequent `/act` → 404).

These shapes are the integration boundary; the implementation plan pins exact field names by reading the route + `room_manifest`.

## 4. Architecture — inside `memento-mori/client/`

Reuse `state/session.ts`, the gateway transport, `state/game-state.ts`, and the existing build pipeline (output to `client/` root per the established convention). Add three new, independently-testable units, one read-port, one new root layout, and one thin gateway read route.

```
client/src/
  panels/typewriter.ts   (new)  — prose column: type segments char-by-char, skippable
  panels/kgmap.ts        (new)  — map column: accreting {rooms,exits,current} → box-drawing
  state/opening-loop.ts  (new)  — orchestrator: /start, /act → routes to the two panels
  state/kg-read-port.ts  (new)  — KgReadPort: getRoomContents(roomUuid) → things[]
  layouts/opening.ts     (new)  — split prose│map primary view (mounts the three units)

gateway/src/gateway/routes/opening.py (modify)
  + GET /api/opening/room/{room_uuid}/contents  — server-side SDK get_edges(incoming) → things[]
```

Each unit has one job and a narrow interface:

- **`Typewriter`** — *what it does:* renders a queue of text segments character-by-character; instant-completes the current segment on keypress; echoes the player's submitted input line. *Interface:* `enqueue(segment: {text, kind})`, `skip()`, `onInputSubmit(cb)`. *Depends on:* nothing game-related (pure render unit).
- **`KgMap`** — *what it does:* holds an accreting client model `{rooms: Map<uuid, Room>, exits: Edge[], currentRoom: uuid}` where `Room = {uuid, name, things: Thing[], entered: bool}`, and renders it as the layered box-drawing map (current room marked, unentered rooms shown as `?`, things docked inside each room). *Interface:* `visitRoom(room, exits)`, `setContents(roomUuid, things[])`, `render()`. *Depends on:* `KgReadPort` (to fetch contents).
- **`opening-loop`** — *what it does:* the only unit that talks to the gateway. Calls `/start`, then on each input calls `/act`; routes `narration` → `Typewriter`, `location/exits` → `KgMap.visitRoom` + a `KgReadPort` contents read → `KgMap.setContents`, and `clarify` → affordance chips (built from the map's current exits + the room's takeable things). *Interface:* `start()`, `submit(text)`. *Depends on:* gateway transport, `Typewriter`, `KgMap`, `KgReadPort`.
- **`KgReadPort`** — *what it does:* `getRoomContents(roomUuid) → Thing[]` via `fetch` to the new gateway read route. Wraps the call so `KgMap` is testable against a fake. *The browser never holds the graph-memory internal token* — the gateway route holds it server-side.

## 5. The render loop (data flow)

```
start()
  POST /start
  → Typewriter.enqueue: epigraph → location_name → description   (types out)
  → KgMap.visitRoom(currentRoom, exits)                          (skeleton appears)
  → KgReadPort.getRoomContents(currentRoom) → KgMap.setContents  (things dock in)

submit("take the iron blade")
  POST /act {player_id, text}
  status=narrated|executed
    → Typewriter.enqueue(narration)
    → KgReadPort.getRoomContents(currentRoom) → KgMap.setContents (new things light up)
  status=clarify
    → Typewriter.enqueue(soft prompt)
    → render chips: exits (from KgMap) + takeable things (from KG contents)
  won=true
    → Typewriter.enqueue(coda); loop ends (session dropped server-side)
```

When the player moves to a new room, `/act` (or the manifest in the response) yields the new `location_id` + `exits`; `opening-loop` calls `KgMap.visitRoom(newRoom, exits)` (accreting the skeleton) then reads its contents.

## 6. The map's KG read — the one nuanced split

The map is a live view of the KG, but two pieces come from two places, deliberately:

- **Room contents (things)** → the **KG**, via `get_edges(roomUuid, direction="incoming")` (the `LOCATED_IN` edges), behind the new gateway read route `GET /api/opening/room/{room_uuid}/contents`. This is the lit subgraph and the source of truth for what's in a room.
- **Room adjacency (exits / spatial layout)** → the **room manifest** the gateway already returns. `KgProjection` does not currently write room→room exit edges, so the client accretes the spatial skeleton from the `exits` it sees as it visits rooms. (Promoting exits to KG edges is a possible later unification — out of scope.)
- **Fog-of-war** → Phase 1 is single-player / single-session, so the client tracks visited rooms locally in the `KgMap` model. A real multi-player "known subgraph" KG query is deferred.

## 7. Robustness / degradation

Comprehension is currently unreliable (returns `clarify` without a working FCG + indexed world), so degradation is a first-class concern:

- **`clarify` is a normal path**, not an error: soft prompt + chips (exits + takeable things). The player is never stuck.
- **KG read fails / empty**: `KgMap` still draws the spatial skeleton (rooms + exits) with empty room interiors; the failure is logged, never thrown to the UI.
- **Typewriter is always skippable** (keypress instant-completes the current segment) so prose never feels slow or blocking.
- **`won` then `/act` → 404**: `opening-loop` treats a 404 after `won` as "session ended", not an error.

## 8. Testing

- **`typewriter.ts`** — unit, no backend: enqueue segments, assert progressive render then complete; assert `skip()` instant-completes; assert input submit fires the callback.
- **`kgmap.ts`** — unit with a **fake `KgReadPort`**: feed a model, assert the box-drawing output contains the rooms, the current-room marker, unentered rooms as `?`, and the docked things; assert `setContents` re-renders with new things.
- **`opening-loop.ts`** — unit against a **fake gateway**: assert `narration` routes to the typewriter, `location/exits` to `KgMap.visitRoom`, a contents read follows, and `clarify` produces chips from exits + contents.
- **Gateway read route** — unit against a fake SDK/projection: `GET .../room/{uuid}/contents` returns the `LOCATED_IN` things; plus the repo-standard handling (404 on unknown room).
- **One thin live smoke** against the running gateway + graph-memory (the stack stood up 2026-06-23): `start()` → the map shows "the deep roads" with its `LOCATED_IN` things read from the KG. (Skips cleanly if the gateway env isn't set, mirroring `opening_smoke.py`.)

## 9. File structure summary

| File | New/Mod | Responsibility |
|---|---|---|
| `client/src/panels/typewriter.ts` | new | Prose column: char-by-char render, skip, input echo |
| `client/src/panels/kgmap.ts` | new | Map column: accreting model → layered box-drawing map |
| `client/src/state/opening-loop.ts` | new | Orchestrator: gateway `/start`+`/act` → the two panels + chips |
| `client/src/state/kg-read-port.ts` | new | `getRoomContents(uuid)` via the gateway read route |
| `client/src/layouts/opening.ts` | new | Split prose│map primary view |
| `gateway/src/gateway/routes/opening.py` | mod | `+ GET /api/opening/room/{room_uuid}/contents` (server-side `get_edges`) |
| tests for each unit + read route + one live smoke | new | as in §8 |

## 10. Out of scope (later phases, noted not specced)

- Swapping the opening HTTP loop for the **WS game loop** for ongoing (post-opening) play.
- Reimagining **inventory / quests / combat / NPC dialogue** as typewriter-native surfaces.
- **Retiring the old panel layout** (`panels/worldmap.ts`, `map.ts`, etc.).
- Promoting **room adjacency to KG edges** and a real multi-player **fog-of-war** known-subgraph query.
- Anything requiring the kernel **`/comprehend`** to actually parse free text (a working FCG + indexed world) — the UI is designed to degrade gracefully until that lands, but does not fix it.
- Visual polish beyond the box-drawing/typewriter idiom (theming, animation tuning).

## 11. Relationship to other specs

Consumes the opening arc (`2026-06-23-kg-native-event-sourced-opening-design.md`) and the KG-CRUD backend (`bonfires-ai-core/.../2026-06-23-kg-crud-graph-memory-design.md`, the `get_edges`/`LOCATED_IN` path this map reads). The "lit subgraph" framing is the UI expression of the same KG the world-ledger PoC and GM-rooms work write into.
