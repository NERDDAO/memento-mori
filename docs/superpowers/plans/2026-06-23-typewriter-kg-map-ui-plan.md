# Typewriter + KG-Map UI — Implementation Plan (Phase 1: layered-canvas baseline)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Fresh implementer per task + per-task review + whole-branch opus review. Steps use checkbox (`- [ ]`) tracking. Spans TWO languages (TS client + Python gateway); each task names its area.

## Context

The memento opening arc works end-to-end (gateway `/api/opening/{start,act}` + the verified `KgProjection` → SDK → graph-memory → Neo4j KG substrate), but has no UI. This plan gives it one — and makes it the client's **new baseline**: a single z-composited canvas where typewriter prose types itself out (left) while a text-map of rooms + the things `LOCATED_IN` them accretes (right) as you play. Components grow as **layers**, not panels. This is Phase 1 of a reimagined whole-play UI: the core loop on the opening arc, proven against the live KG. Spec: `memento-mori/docs/superpowers/specs/2026-06-23-typewriter-kg-map-ui-design.md`.

**Goal:** Boot the client into a split typewriter│KG-map canvas driven by the opening arc, with the map a live view of the lit subgraph.

**Architecture:** New TS units in `memento-mori/client/src` rendered as CharCell-grid panels on the existing `UnifiedCanvas`: a `ProseLayer` (typewriter) + `MapLayer` (box-drawing KG map) registered by a slim new boot (`boot/opening-shell.ts`) that becomes the build entry. An `OpeningLoop` orchestrator drives them off `/api/opening/{start,act}`; a `KgReadPort` reads room contents through a new **player-scoped** route `GET /api/opening/room/{uuid}/contents?player_id=…`.

**Tech Stack:** TypeScript + **Bun** (build + the `bun test` runner this plan introduces); Python + FastAPI + pytest (gateway); the existing `UnifiedCanvas`/`region-manager`/`panel-utils` CharCell substrate.

## Global Constraints

- **Repo / branch:** `memento-mori`, branch `ui/typewriter-kg-map` (already created, off `opening/engine-core`). NEVER `git add -A` — stage only files each task touches (the tree carries unrelated modified `CLAUDE.md` + `engine/data/narration_cooldowns.json`).
- **Commit trailer (every commit), exact:** `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Client build:** `cd client && bun build src/boot/opening-shell.ts --outfile app.js` is the NEW default entry (replacing `src/app.ts`); `client/index.html:391` keeps loading `/app.js`. `app.ts` stays intact (dormant full-boot).
- **Client tests:** `bun test` (built-in, `import { test, expect, mock } from "bun:test"`). Convention: `*.test.ts` colocated beside the unit. Run one file: `cd client && bun test src/<path>.test.ts`. (No runner exists today — Task 1 establishes it.)
- **Gateway/engine tests:** pytest, `asyncio_mode="auto"` (`engine/pyproject.toml:36`). Run one file from repo root: `python -m pytest gateway/tests/<file> -v` (CI uses editable installs, no PYTHONPATH; from source use `PYTHONPATH=engine/src:gateway/src python -m pytest …`).
- **CharCell substrate (reuse, don't reinvent):** `CharCell {char, fg, bg?, attrs?}` (`renderer/canvas-text.ts:11`); a panel is a pure `(cols, rows, …) → PanelResult {cells: CharCell[][], hitRegions?}` (`canvas/types.ts:14`); row helpers `textRow(text,fg,cols,attrs?)` / `coloredRow(segments,cols)` / `emptyRow(cols)` (`panels/panel-utils.ts:10,19,36`); write via `uc.setRegionContent(name, result)` + `uc.markDirty(name)` (`canvas/unified-canvas.ts:138,202`).
- **Gateway base URL:** `GATEWAY_URL` (`client/src/state/session.ts:6`, default port `8081`). All new HTTP goes through the new `state/api.ts`.
- **Player-scoped KG read (load-bearing):** `location_id` from `/start` is the **engine** room uuid; the engine→KG uuid map is per-player + in-memory in `KgProjection`. The contents route MUST resolve via the player's repo (`repo.room_manifest(engine_uuid)` → `manifest.npcs + manifest.items`), NOT a global `get_edges`. A new module-level `opening_repos[player_id] = repo` registry backs it.
- **Degradation:** `clarify` is a normal path (prompt + chips), never an error; KG-read failure leaves the map skeleton intact (log, don't throw); typewriter is always skippable.

## File Structure

| File | New/Mod | Responsibility |
|---|---|---|
| `client/package.json` | mod | add `test` script; repoint `build` to `opening-shell.ts` (+ keep `build:full`) |
| `client/src/state/api.ts` | new | `apiGet`/`apiPost` over `GATEWAY_URL` |
| `client/src/canvas/layer.ts` | new | `Layer` contract (id, regionName, render, onKey?) |
| `client/src/layers/prose-layer.ts` | new | typewriter prose → PanelResult; enqueue/tick/skip |
| `client/src/layers/map-layer.ts` | new | accreting rooms/things/exits → box-drawing PanelResult |
| `client/src/state/kg-read-port.ts` | new | `getRoomContents(playerId, roomUuid)` via `api` |
| `client/src/state/opening-loop.ts` | new | orchestrator: /start, /act → layers + chips |
| `client/src/canvas/region-manager.ts` | mod | add `computeOpeningRegions(cols,rows)` (prose│map + input + status) |
| `client/src/canvas/unified-canvas.ts` | mod | accept an injectable regions fn (default = `computeRegions`) |
| `client/src/boot/opening-shell.ts` | new | NEW BASELINE: build UC(opening), register layers, wire input, tick, start |
| `gateway/src/gateway/routes/opening.py` | mod | `opening_repos` registry + `GET /opening/room/{uuid}/contents` |

Dependency order: **T1** → (T2, T3, T4, T8 independent) → **T5** (needs T2) → **T6** (needs T2–T5) → **T7** (Python, independent — can run any time) → **T9** (needs T3,T4,T6,T8 + T7's route).

---

## Task 1: Establish the `bun test` runner

**Files:** Modify `client/package.json`; Test `client/src/smoke.test.ts`.

**Interfaces — Produces:** the `bun test` convention every later client task relies on; a `test` npm script.

- [ ] **Step 1: Write a trivial failing test** — `client/src/smoke.test.ts`:
```ts
import { test, expect } from "bun:test";
test("bun test runner works", () => {
  expect(1 + 1).toBe(3); // intentionally wrong first
});
```
- [ ] **Step 2: Run → fail** — `cd client && bun test src/smoke.test.ts` → FAIL (`expected 2 to be 3`). Proves the runner executes TS with no config.
- [ ] **Step 3: Fix the assertion to `toBe(2)`** and add to `client/package.json` `"scripts"`: `"test": "bun test"`.
- [ ] **Step 4: Run → pass** — `cd client && bun test src/smoke.test.ts` → PASS; `bun test` (all) → PASS.
- [ ] **Step 5: Commit** — `git add client/package.json client/src/smoke.test.ts`; commit `chore(client): add bun test runner` + trailer.

---

## Task 2: Shared gateway fetch helper (`state/api.ts`)

**Files:** Create `client/src/state/api.ts`; Test `client/src/state/api.test.ts`.

**Interfaces — Produces:**
- `apiPost<T>(path: string, body: unknown): Promise<T>` — POST JSON to `GATEWAY_URL + path`, throws `Error` on non-ok with status + body text.
- `apiGet<T>(path: string): Promise<T>` — GET `GATEWAY_URL + path`, same error contract.
Consumes: `GATEWAY_URL` (`client/src/state/session.ts:6`).

- [ ] **Step 1: Write failing tests** (mock `globalThis.fetch` with `bun:test` `mock`):
```ts
import { test, expect, mock } from "bun:test";
import { apiPost, apiGet } from "./api";
import { GATEWAY_URL } from "./session";

function fakeFetch(status: number, json: unknown) {
  return mock(async (_url: string, _init?: any) =>
    ({ ok: status < 400, status, json: async () => json, text: async () => JSON.stringify(json) }) as any);
}

test("apiPost hits GATEWAY_URL + path with JSON body and returns parsed json", async () => {
  const f = fakeFetch(200, { player_id: "p1" }); (globalThis as any).fetch = f;
  const out = await apiPost<{ player_id: string }>("/api/opening/start", { x: 1 });
  expect(f.mock.calls[0][0]).toBe(`${GATEWAY_URL}/api/opening/start`);
  expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ x: 1 });
  expect(out.player_id).toBe("p1");
});
test("apiGet returns parsed json", async () => {
  (globalThis as any).fetch = fakeFetch(200, { things: [] });
  expect(await apiGet<{ things: unknown[] }>("/api/x")).toEqual({ things: [] });
});
test("non-ok throws with status", async () => {
  (globalThis as any).fetch = fakeFetch(404, { detail: "nope" });
  await expect(apiGet("/api/missing")).rejects.toThrow(/404/);
});
```
- [ ] **Step 2: Run → fail** — `cd client && bun test src/state/api.test.ts` → FAIL (module missing).
- [ ] **Step 3: Implement** `client/src/state/api.ts`:
```ts
import { GATEWAY_URL } from "./session";
async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return (await res.json()) as T;
}
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return handle<T>(await fetch(`${GATEWAY_URL}${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }));
}
export async function apiGet<T>(path: string): Promise<T> {
  return handle<T>(await fetch(`${GATEWAY_URL}${path}`));
}
```
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit** — `git add client/src/state/api.ts client/src/state/api.test.ts`; commit `feat(client): shared apiGet/apiPost over GATEWAY_URL` + trailer.

---

## Task 3: `Layer` contract + `ProseLayer` (typewriter)

**Files:** Create `client/src/canvas/layer.ts`, `client/src/layers/prose-layer.ts`; Test `client/src/layers/prose-layer.test.ts`.

**Interfaces — Produces:**
- `Layer { readonly id: string; readonly regionName: string; render(cols: number, rows: number): PanelResult; onKey?(key: string): void; }` (in `canvas/layer.ts`).
- `Segment = { text: string; kind: "epigraph"|"location"|"description"|"narration"|"prompt" }`.
- `class ProseLayer implements Layer` (`id="prose"`, `regionName="prose"`) with `enqueue(seg: Segment): void`, `skip(): void`, `tick(): boolean` (advance reveal by one char; returns `true` while still revealing), `render(cols, rows): PanelResult`.
Consumes: `PanelResult`/`CharCell` (`canvas/types.ts:14`, `renderer/canvas-text.ts:11`); `textRow`/`emptyRow` (`panels/panel-utils.ts`).

Reveal model: enqueued segments concatenate into one growing stream (each ends with `"\n\n"`); `revealed` counts chars shown; `render` word-wraps the **revealed prefix** into `cols`-wide rows (newest at the bottom; clip to `rows`).

- [ ] **Step 1: Write failing tests:**
```ts
import { test, expect } from "bun:test";
import { ProseLayer } from "./prose-layer";
const joinCells = (r: { cells: { char: string }[][] }) =>
  r.cells.map(row => row.map(c => c.char).join("").trimEnd()).join("\n").trim();

test("enqueue + skip reveals full text wrapped to cols", () => {
  const p = new ProseLayer();
  p.enqueue({ text: "the blade lies still", kind: "narration" });
  p.skip();
  expect(joinCells(p.render(10, 6)).replace(/\n/g, " ")).toContain("the blade lies still");
  expect(p.tick()).toBe(false);
});
test("tick reveals one char at a time", () => {
  const p = new ProseLayer();
  p.enqueue({ text: "ab", kind: "narration" });
  expect(joinCells(p.render(20, 4))).toBe("");
  expect(p.tick()).toBe(true);
  expect(joinCells(p.render(20, 4))).toBe("a");
  p.tick();
  expect(joinCells(p.render(20, 4))).toBe("ab");
});
```
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** `canvas/layer.ts` (the interface) and `layers/prose-layer.ts`: a small word-wrap of the revealed prefix; build rows via `textRow(line, <primary>, cols)`; keep only the last `rows` lines, pad with `emptyRow(cols)`. `tick()` increments `revealed` to the full length, returns `revealed < fullLen`; `skip()` jumps to full.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit** — stage the 3 files; commit `feat(client): Layer contract + ProseLayer typewriter` + trailer.

---

## Task 4: `MapLayer` (accreting box-drawing KG map)

**Files:** Create `client/src/layers/map-layer.ts`; Test `client/src/layers/map-layer.test.ts`.

**Interfaces — Produces:**
- `Thing = { uuid: string; name: string }`.
- `class MapLayer implements Layer` (`id="kgmap"`, `regionName="kgmap"`) with:
  - `visitRoom(room: { uuid: string; name: string }, exits: { direction: string; target_id: string }[]): void` — marks `room` entered + current; registers each exit + an unentered stub neighbor if unknown.
  - `setContents(roomUuid: string, things: Thing[]): void`.
  - `render(cols, rows): PanelResult` — current room as a labeled box with `* things` and an `exits: …` line; other known rooms compactly; unentered rooms show `?`.
  - `currentExits(): { direction: string; targetId: string }[]`, `currentThings(): Thing[]` (for chips).
Consumes: `panel-utils` helpers.

- [ ] **Step 1: Write failing tests:**
```ts
import { test, expect } from "bun:test";
import { MapLayer } from "./map-layer";
const flat = (r: { cells: { char: string }[][] }) => r.cells.map(row => row.map(c => c.char).join("")).join("\n");

test("visited room shows name, things and exits", () => {
  const m = new MapLayer();
  m.visitRoom({ uuid: "r1", name: "the deep roads" }, [{ direction: "down", target_id: "r2" }]);
  m.setContents("r1", [{ uuid: "e1", name: "a dying adventurer" }, { uuid: "e2", name: "an iron blade" }]);
  const out = flat(m.render(40, 20));
  expect(out).toContain("the deep roads");
  expect(out).toContain("a dying adventurer");
  expect(out).toContain("an iron blade");
  expect(m.currentExits()).toEqual([{ direction: "down", targetId: "r2" }]);
});
test("unentered neighbor renders as ?", () => {
  const m = new MapLayer();
  m.visitRoom({ uuid: "r1", name: "deep roads" }, [{ direction: "down", target_id: "r2" }]);
  expect(flat(m.render(40, 20))).toContain("?");
});
```
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** `layers/map-layer.ts` — `Map<string, Room>` (`Room = {uuid,name,things,entered}`) + `exits[]` + `current`; stacked-block render (Phase-1 worlds are tiny).
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit** — stage the 2 files; commit `feat(client): MapLayer accreting box-drawing KG map` + trailer.

---

## Task 5: `KgReadPort` (room contents over HTTP)

**Files:** Create `client/src/state/kg-read-port.ts`; Test `client/src/state/kg-read-port.test.ts`.

**Interfaces — Produces:**
- `interface KgReadPort { getRoomContents(playerId: string, roomUuid: string): Promise<Thing[]>; }` (`Thing` re-exported from `map-layer`).
- `const httpKgReadPort: KgReadPort` — GETs `/api/opening/room/${roomUuid}/contents?player_id=${playerId}` via `apiGet`, returns `resp.things`; on ANY thrown error returns `[]` (degrade: map keeps its skeleton).
Consumes: `apiGet` (Task 2).

- [ ] **Step 1: Failing tests** (mock `fetch` as in Task 2): assert the URL is `${GATEWAY_URL}/api/opening/room/r1/contents?player_id=p1` and returns the `things` array; and a 500 resolves to `[]` (not a throw).
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** — `apiGet` wrapped in try/catch returning `[]`; path built with `encodeURIComponent(playerId)`.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit** — stage the 2 files; commit `feat(client): KgReadPort room-contents read` + trailer.

---

## Task 6: `OpeningLoop` orchestrator

**Files:** Create `client/src/state/opening-loop.ts`; Test `client/src/state/opening-loop.test.ts`.

**Interfaces — Produces:**
- `StartResp = { player_id: string; epigraph: string; location_id: string; location_name: string; description: string; exits: { direction: string; target_id: string }[] }`.
- `ActResp = { status: string; narration?: string | null; won?: boolean; reason?: string | null }`.
- `interface Gateway { start(): Promise<StartResp>; act(playerId: string, text: string): Promise<ActResp>; }` + `const httpGateway: Gateway` (POSTs `/api/opening/start` and `/api/opening/act` via `apiPost`).
- `class OpeningLoop` — `constructor(prose: ProseLayer, map: MapLayer, gateway: Gateway, kg: KgReadPort, onChips: (chips: string[]) => void, redraw: () => void)`; `start(): Promise<void>`; `submit(text: string): Promise<void>`.
Consumes: Tasks 2–5.

Routing: `start()` → prose enqueues epigraph/location/description, `map.visitRoom`, `kg.getRoomContents` → `map.setContents`, stash `playerId`, `redraw`. `submit()` → `gateway.act`: `narrated`/`executed` → enqueue narration + refresh contents; `clarify` → enqueue prompt + `onChips([...exits "go <dir>", ...things "take <name>"])`; `won` → enqueue narration + mark ended (further submit = no-op); always `redraw`. Wrap `kg.getRoomContents` so a rejection never breaks the turn.

- [ ] **Step 1: Write failing tests** (fake gateway + fake KgReadPort + REAL Prose/Map layers):
```ts
import { test, expect } from "bun:test";
import { OpeningLoop } from "./opening-loop";
import { ProseLayer } from "../layers/prose-layer";
import { MapLayer } from "../layers/map-layer";

const startResp = { player_id:"p1", epigraph:"E", location_id:"r1", location_name:"deep roads",
  description:"D", exits:[{ direction:"down", target_id:"r2" }] };
function harness(act: any) {
  const prose = new ProseLayer(), map = new MapLayer(); const chips: string[][] = [];
  let actCalls = 0;
  const gateway = { start: async () => startResp, act: async () => { actCalls++; return act; } };
  const kg = { getRoomContents: async () => [{ uuid:"e1", name:"an iron blade" }] };
  return { prose, map, chips, actCalls: () => actCalls,
    loop: new OpeningLoop(prose, map, gateway as any, kg as any, c => chips.push(c), () => {}) };
}
test("start seeds prose + map + contents", async () => {
  const h = harness({}); await h.loop.start();
  expect(h.map.currentExits()).toEqual([{ direction:"down", targetId:"r2" }]);
  expect(h.map.currentThings().map(t => t.name)).toContain("an iron blade");
});
test("clarify produces chips from exits + things", async () => {
  const h = harness({ status:"clarify", reason:"no_match" });
  await h.loop.start(); await h.loop.submit("flarble");
  const last = h.chips.at(-1)!;
  expect(last).toContain("go down");
  expect(last).toContain("take an iron blade");
});
test("won ends the loop; a later submit is a no-op (no second act call)", async () => {
  const h = harness({ status:"executed", won:true, narration:"you ascend" });
  await h.loop.start(); await h.loop.submit("go on");
  expect(h.actCalls()).toBe(1);
  await h.loop.submit("again"); // post-win submit must be ignored
  expect(h.actCalls()).toBe(1); // gateway.act not called again
});
```
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** `state/opening-loop.ts` (class + `httpGateway`). Guard `submit` after `won`.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit** — stage the 2 files; commit `feat(client): OpeningLoop orchestrator (start/act → layers + chips)` + trailer.

---

## Task 7: Gateway player-scoped room-contents route (Python)

**Files:** Modify `gateway/src/gateway/routes/opening.py`; Test `gateway/tests/test_opening_contents_route.py`.

**Interfaces — Produces:** `GET /api/opening/room/{room_uuid}/contents?player_id=…` → `{"things": [{"uuid": str, "name": str}]}`, backed by a new module-level `opening_repos: dict[str, <repo>] = {}` populated in `start_opening` and dropped on `won` (mirroring `opening_registry`).
Consumes: `repo.room_manifest(engine_uuid)` (`engine/.../event_sourced.py:395`) → `manifest.npcs + manifest.items` (the `LOCATED_IN` reads, engine→KG resolved inside the projection).

- [ ] **Step 1: Write the failing route test** — mirror `gateway/tests/test_opening_routes.py:97-123` (`httpx.ASGITransport(app)` + the autouse `_patch_opening_hooks` monkeypatching `build_projection` → `KgProjectionFake`, and `_clear_registry`; also clear `opening_repos`). Drive `POST /api/opening/start`, capture `player_id` + `location_id`, then `GET /api/opening/room/{location_id}/contents?player_id={player_id}` → assert 200 and that the seeded opening entities appear in `resp["things"]` names; unknown `player_id` → 404. (Confirm the exact seeded names + the `npcs`/`items` dict keys by reading `KgProjectionFake` + `entities_at_location`; use `uuid`/`name` with a fallback.)
- [ ] **Step 2: Run → fail** — `python -m pytest gateway/tests/test_opening_contents_route.py -v` → FAIL (route missing).
- [ ] **Step 3: Implement** in `opening.py`: add `opening_repos: dict[str, object] = {}`; in `start_opening` after the repo is built, `opening_repos[player_uuid] = repo`; in `act_opening`'s win-cleanup, also `opening_repos.pop(req.player_id, None)`; add:
```python
@router.get("/opening/room/{room_uuid}/contents")
async def room_contents(room_uuid: str, player_id: str) -> dict:
    repo = opening_repos.get(player_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Opening session not found.")
    manifest = await repo.room_manifest(room_uuid)
    things = [
        {"uuid": e.get("uuid") or e.get("id"), "name": e.get("name", "")}
        for e in (manifest.npcs + manifest.items)
    ]
    return {"things": things}
```
- [ ] **Step 4: Run → pass.** Also run `gateway/tests/test_opening_routes.py -v` → still green (the win-cleanup edit must not break it).
- [ ] **Step 5: Commit** — stage `opening.py` + the new test; commit `feat(gateway): player-scoped GET /opening/room/{uuid}/contents (LOCATED_IN)` + trailer.

---

## Task 8: Opening layout regions + injectable regions on UnifiedCanvas

**Files:** Modify `client/src/canvas/region-manager.ts`, `client/src/canvas/unified-canvas.ts`; Test `client/src/canvas/region-manager.test.ts`.

**Interfaces — Produces:**
- `computeOpeningRegions(totalCols: number, totalRows: number): Map<string, Region>` — minimal layout: outer frame; `prose` (left, ~60% cols) │ `_vDivOpening` │ `kgmap` (right, remainder) filling the body; `input` (1 row near bottom); `status` (last row). All `type:"grid"`.
- `UnifiedCanvas` constructor gains optional `computeRegionsFn: (cols, rows) => Map<string, Region> = computeRegions` (default preserves `app.ts` + every caller), stored + used in `_resize`.
Consumes: `Region` (`canvas/types.ts:4`); `computeRegions` (`region-manager.ts:42`) as the rect-math template.

- [ ] **Step 1: Failing test:**
```ts
import { test, expect } from "bun:test";
import { computeOpeningRegions } from "./region-manager";
test("opening layout has prose, kgmap, input, status with sane bounds", () => {
  const r = computeOpeningRegions(80, 24);
  for (const name of ["prose", "kgmap", "input", "status"]) expect(r.has(name)).toBe(true);
  const prose = r.get("prose")!, map = r.get("kgmap")!;
  expect(prose.col).toBeLessThan(map.col);
  expect(prose.cols).toBeGreaterThan(map.cols * 0.8);
  expect(prose.row).toBeGreaterThanOrEqual(1);
});
```
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** `computeOpeningRegions` (mirror `computeRegions`); thread the injectable fn through `UnifiedCanvas` (`constructor(container, computeRegionsFn = computeRegions)`; store + call in `_resize`).
- [ ] **Step 4: Run → pass** (`bun test src/canvas/region-manager.test.ts`); back-compat check: `cd client && bun build src/app.ts --outfile /tmp/app-check.js` → no errors.
- [ ] **Step 5: Commit** — stage the 3 files; commit `feat(client): opening layout regions + injectable regions on UnifiedCanvas` + trailer.

---

## Task 9: The new baseline boot (`opening-shell`) + build wiring + live smoke

**Files:** Create `client/src/boot/opening-shell.ts`; Modify `client/package.json` (build entry). (Manual live smoke — logic is covered by T2–T8; no new automated test.)

**Interfaces — Consumes:** every prior client unit + Task 7's route.

- [ ] **Step 1: Implement `boot/opening-shell.ts`** — on `DOMContentLoaded`: `#tui-main`; `const uc = new UnifiedCanvas(tuiMain, computeOpeningRegions)`; `ProseLayer` + `MapLayer`; a `redraw()` reading `uc.getRegion('prose'|'kgmap')` and `uc.setRegionContent(... render(region.cols, region.rows))` + `markDirty`; `const loop = new OpeningLoop(prose, map, httpGateway, httpKgReadPort, renderChips, redraw)`; wire `initInput(document.getElementById('action-input') as HTMLInputElement, t => loop.submit(t))`; a `document` keydown listener `→ prose.skip(); redraw()` (respect the INPUT-focus guard from `hotkeys.ts:15`); a typewriter tick `setInterval(() => { if (prose.tick()) redraw(); }, 25)`; render chips into the prose region (or status line) as selectable text; then `void loop.start()`.
- [ ] **Step 2: Repoint the build** in `client/package.json`: `"build": "bun build src/boot/opening-shell.ts --outfile app.js"` and add `"build:full": "bun build src/app.ts --outfile app.js"`. Run `cd client && bun run build` → emits `client/app.js`, no errors.
- [ ] **Step 3: Live smoke (manual).** With graph-memory on :8003 + the gateway wired to it (the 2026-06-23 `.git/sdd` env recipe), serve `client/index.html` against the gateway and confirm: epigraph → "the deep roads" → description **type out** (left); the **deep-roads box with its `LOCATED_IN` things** (right, from the KG); a `clarify` shows **chips**. Record the result (skip-note if the stack isn't up).
- [ ] **Step 4: Full client suite** — `cd client && bun test` → all green (T1–T8); `bun run build` clean.
- [ ] **Step 5: Commit** — stage `client/src/boot/opening-shell.ts` + `client/package.json`; commit `feat(client): opening-shell layered baseline boot + build entry` + trailer.

---

## Verification

1. **Client units:** `cd client && bun test` → green across `api`, `prose-layer`, `map-layer`, `kg-read-port`, `opening-loop`, `region-manager`.
2. **Client build:** `cd client && bun run build` → emits `client/app.js` from `opening-shell.ts`, no errors; `bun run build:full` still builds `app.ts`.
3. **Gateway route:** `python -m pytest gateway/tests/test_opening_contents_route.py gateway/tests/test_opening_routes.py -v` → green (new route returns seeded `LOCATED_IN` things; existing opening tests unbroken).
4. **End-to-end live (manual):** with graph-memory :8003 + gateway wired to it, the page boots into the split typewriter│map baseline; `/start` types the deep-roads prose while the map shows the room + its KG things; `clarify` yields chips.
5. **Whole-branch opus review:** layers are pure/testable (render is a function of state); the route is genuinely player-scoped (wrong/absent `player_id` → 404, no global leak); `app.ts` still builds (UnifiedCanvas regions-arg back-compat); `clarify`/KG-read-failure degrade without throwing.

## Out of Scope (later phases)

- Adapting `ui/codex-renderer.ts` / `ui/inventory-renderer.ts` / `ui/dialog-renderer.ts` to the `Layer` contract as z1+ overlay layers (the first "add a capability = add a layer" proof).
- Swapping the opening HTTP loop for the WS game loop; inventory/quests/combat/NPC dialogue as layers; deleting the old `app.ts` panel boot.
- Promoting room adjacency to KG edges; multi-player fog-of-war known-subgraph query.
- Fixing kernel `/comprehend` (working FCG + indexed world) — the UI degrades gracefully until it lands.

## On approval

Authored in plan mode. On approval: save this plan to `memento-mori/docs/superpowers/plans/2026-06-23-typewriter-kg-map-ui-plan.md` + commit (doc only), then execute via superpowers:subagent-driven-development on branch `ui/typewriter-kg-map` (T1→T9, T7 parallelizable).
