# cxn_fired Observability — "Catch the Construction" Signal (Slice 1, Plan 3 of N)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax. Spec: `docs/superpowers/specs/2026-06-26-agent-driven-opening-cxn-catch-design.md` (**Component F**, spec "Phase 1"). This is the headline game mechanic — *seeing a construction fire* — and it is a **cross-repo vertical slice**: the signal is produced in **bonfires-ai-core** (agent-runtime), emitted as a WS event by the **memento-mori gateway**, and rendered as a "◇ caught: LOOK" beat by the **memento-mori client**. It is independently testable against a *stubbed* comprehend result — it needs neither a live kernel nor the player-persona (those are Plans 4–5).

**Goal:** When a scene turn's comprehension fires a construction, surface it end-to-end: the agent-runtime carries the fired construct ids on the turn response, the gateway logs + broadcasts a `cxn_fired` WS event (construct id → display name), and the client renders a distinct catch beat in the typewriter prose pane ahead of the narration.

**Architecture:** Three tasks, one per layer of the data flow. (1) agent-runtime: thread `applied_cxn_ids` (currently read-and-dropped in `_comprehend_and_activate`) up through `PipelineOutput` to a new `SceneTurnResponse.fired_cxns: list[str]`. (2) gateway: in `SceneCoordinator.handle_player_message`, after the turn returns, map each fired construct id → a display name via a small static map, log it, and broadcast a `cxn_fired` WS event — before the narration broadcast, independent of `should_respond`. (3) client: a `cxn_fired` case in `routeOpeningMessage` enqueues a `"catch"`-kind prose segment ("◇ caught: LOOK").

**Tech Stack:** bonfires-ai-core agent-runtime = Python 3.12 / FastAPI / pytest (`asyncio_mode="auto"`, **no decorator**), `uv`. memento-mori gateway = Python / pytest (`@pytest.mark.asyncio`). memento-mori client = TypeScript / `bun test` + `bun run build`.

## Branches & bases (TWO repos)

- **bonfires-ai-core (Task 1):** branch `cxn-catch/cxn-fired` off `persona/service-revision` (HEAD `bab1a4d`). Use an **isolated worktree** so the repo's unrelated dirty `.claude/skills/*` files are not involved: `git -C /home/at0x/Vaults/Bonfires/bonfires-ai-core worktree add -b cxn-catch/cxn-fired <scratchpad>/core-cxn-fired persona/service-revision`. Work from that worktree. PRs in this repo target `staging` — but this plan only commits to the feature branch; opening a PR is out of scope.
- **memento-mori (Tasks 2 + 3):** branch `opening/cxn-catch` (HEAD `8fbed24` after Plan 2), existing worktree `<scratchpad>/mmori-cxn-catch`.
- The two repos are independent git roots; each task commits in its own repo.

## Global Constraints

- Commit trailer (exact, every commit, both repos): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Never `git add -A`** — stage only the files each task touches. (Critical in bonfires-ai-core: the repo has unrelated dirty `.claude/skills/*` files; the worktree avoids them, but still stage explicitly.)
- **bonfires-ai-core rules (binding, from its CLAUDE.md):** No `Any` in service signatures. No `# type: ignore` without a code+justification. Services raise domain exceptions, never `HTTPException`. **No `os.getenv`** outside `app/config.py`. Feature-branch only (never commit to `main`/`staging`). `ruff format` before commit. The existing best-effort `except Exception: logger.warning(...)` in `_comprehend_and_activate` is the established pattern there (it logs, it does not silently pass) — preserve it.
- **The fired-cxn signal must be best-effort end-to-end:** a comprehension miss / empty `applied_cxn_ids` yields `fired_cxns=[]` and simply no `cxn_fired` event — never an error. The gateway emission and client render are additive and must not disturb the existing `mm_npc_response` narration path.
- **`fired_cxns` is keyed on the construct id** (e.g. `"mm.look.v1"`), NOT a predicate (the kernel returns `predicate=""` for the minimal LOOK — Phase-0 finding). The construct-id → display-name map (`{"mm.look.v1": "LOOK"}`) is owned by the gateway.
- Ruff-format / prettier only the files each task touches. Client: after editing TS source, regenerate the committed `client/app.js` via `bun run build` (it is a checked-in build artifact served at runtime) and stage it.

## Key existing symbols (verbatim anchors)

### bonfires-ai-core (agent-runtime) — paths under `services/agent-runtime/`
- **`SceneTurnResponse`** — `src/app/modules/scenes/scenes_dto.py:61-65`: `class SceneTurnResponse(BaseModel): response_text: str; should_respond: bool = True`. (`Field` may need importing.)
- **`PipelineOutput`** — `src/app/modules/pipeline/pipeline_dto.py:254-262`: `response_text, image_prompt, image_caption, labels, retrieval_used, sources, tools_used, should_respond` — no cxn field.
- **`_comprehend_and_activate`** — `src/app/modules/pipeline/backend.py:120-163`, returns `frozenset[str] | None` (the `tools_for_turn` allowed-tools set when `_in_loop_activation and _cxn_manifest is not None`, else `None`). Reads `frame.applied_cxn_ids` at lines 143 & 155 but **drops it**. Early return `ComprehendOutcome()` at line 132-133 (`if self._cxn_gateway is None or not self._jwt_secret`). Best-effort `except Exception: logger.warning(...)` at 158-162.
- **Caller** — `backend.py:332`: `allowed_tools = await self._comprehend_and_activate(msg)`; `allowed_tools` is passed to `_run_pipeline_in_thread(..., allowed_tools=allowed_tools)` at line 344; `PipelineOutput(...)` is built at lines 365-372 (no `fired_cxns`). `PipelineResult.from_prediction` does NOT carry cxn ids (not in the DSPy prediction) — thread `fired_cxns` separately.
- **`SemanticFrame`** — `src/app/adapters/graph_memory/types.py:153-162`: `{predicate: str|None, applied_cxn_ids: list[str], matched: bool}`.
- **Route** — `src/app/modules/scenes/scenes_routes.py:166-200`, `turn(...)`: builds `SceneTurnResponse(response_text=output.response_text, should_respond=output.should_respond)` at line 197 from `output = await runtime.voice_turn(...)` (line 189). `voice_turn` (`src/app/runtime/scene/scene_runtime.py:363-393`) passes `PipelineOutput` through unchanged.
- **Tests** — `tests/test_scenes_routes.py`: `_RecordingBackend(response_text="npc voice response")` at `:78-94` returns `PipelineOutput(response_text=..., retrieval_used=RetrievalPath.NONE, should_respond=True)`; the turn-route test `test_turn_routes_utterance_under_self_id` at `:302-330` asserts `body["response_text"]`. `asyncio_mode="auto"`.
- **Test runner:** from `services/agent-runtime/`, `uv run pytest <files> -q`. If imports fail, run `uv sync --all-packages` from the repo root first.
- **CHANGELOG (rule 14):** `docs/migration/CHANGELOG.md` — every code-changing change gets an entry.

### memento-mori gateway — paths under `gateway/src/gateway/`
- **`SceneCoordinator.handle_player_message`** — `scene_coordinator.py:140-173`. `turn = await driver.drive_turn(location_uuid, message)` at 156 (try/except at 157-159 returns True on failure). The `mm_npc_response` broadcast is inside `if turn.get("should_respond", True):` at 161-172. `self._ws_hub`, `self._npc_name(turn.get("self_id"))`, `location_name` in scope. `logger` is module-level (used at 158). `fired_cxns` already rides through `RoomDriver.drive_turn` for free (`room_driver.py:281` returns `{**data, "self_id": actor_uuid}`) — no client/driver change.
- **WS** — `WebSocketHub.broadcast_to_location(location: str, message: dict)` (`ws.py:88`). Flat-dict + top-level `type` convention.
- **Tests** — `gateway/tests/test_scene_coordinator.py`: a fake driver returns `{"response_text": "Halt!", "should_respond": True, "self_id": "npc-1"}`; `_FakeHub` records `(location, message)` in `self.broadcasts`; assertions check `msg["type"]`/`msg["tool"]`. (No construct-id→name map exists anywhere — this plan defines one.)

### memento-mori client — paths under `client/`
- **`routeOpeningMessage`** — `src/state/opening-ws.ts:18-47` (the live opening dispatch; `client/app.js` is its **generated** build output — edit the TS source, never app.js). Cases: `tool_event`(→`s.prose.enqueue({kind:"npc-dialogue",...}); s.redrawProse()`), `npc_joined`, `npc_left`. `OpeningSurfaces.prose.enqueue` kind union typed at `opening-ws.ts:8-10`.
- **`Segment`** — `src/layers/prose-layer.ts:6-10`: `kind: "epigraph"|"location"|"description"|"narration"|"prompt"|"npc-name"|"npc-dialogue"`. Color mapping in `ProseLayer.render` at `prose-layer.ts:85-88` (`npc-name`/`npc-dialogue` → `theme.colors.npc`, else `primary`). Theme tokens `src/renderer/theme.ts:6-14` (`npc:'#d4a574'`, `accent:'#8b5cf6'`, `primary:'#c8c8d0'`).
- **WS types** — `src/types/ws-messages.ts`: `ToolEventMessage`(121-128), `NpcJoinedMessage`(98-102); union `WsMessage`(130-148). (The opening router reads `Record<string, unknown>`, so the typed union is for completeness/the in-game path.)
- **Tests/build** — `bun test` (`src/state/opening-ws.test.ts:30-35` drives a message through `routeOpeningMessage` and asserts `s.enqueued`/`s.redraws` via `makeSurfaces()` at :10-28). Build: `bun run build` regenerates `app.js`.

## File Structure

- bonfires-ai-core: `pipeline_dto.py` (+field), `scenes_dto.py` (+field), `backend.py` (`_ComprehendOutcome` + thread), `scenes_routes.py` (+serialize), `tests/test_scenes_routes.py` (+assert), `docs/migration/CHANGELOG.md` (+entry).
- gateway: `scene_coordinator.py` (display map + `_broadcast_cxn_fired` + call), `tests/test_scene_coordinator.py` (+test).
- client: `opening-ws.ts` (+case), `prose-layer.ts` (+kind+color), `types/ws-messages.ts` (+type), `state/opening-ws.test.ts` (+test), `app.js` (regenerated).

---

# Task 1 — agent-runtime: carry `fired_cxns` on the turn response (bonfires-ai-core)

**Files:**
- Modify: `services/agent-runtime/src/app/modules/pipeline/pipeline_dto.py`, `.../pipeline/backend.py`, `.../scenes/scenes_dto.py`, `.../scenes/scenes_routes.py`
- Modify: `services/agent-runtime/tests/test_scenes_routes.py`
- Modify: `docs/migration/CHANGELOG.md`

**Interfaces:**
- Produces: `SceneTurnResponse.fired_cxns: list[str]` (default `[]`) on `POST /v1/scenes/{id}/turn`. Consumed by Task 2 (the gateway reads `turn["fired_cxns"]`).

- [ ] **Step 0 — confirm the runner:** from `services/agent-runtime/`, `uv run pytest tests/test_scenes_routes.py -q` passes on the untouched branch. If imports fail, `uv sync --all-packages` from the repo root, then retry. Also run `gitnexus_impact({target: "_comprehend_and_activate", direction: "upstream"})` (repo rule) and confirm the only caller is `backend.py:332`; if there are others, update them too.

- [ ] **Step 1 — add `fired_cxns` to `PipelineOutput`** (`pipeline_dto.py`, in the class at 254-262, after `should_respond`):
```python
    fired_cxns: list[str] = Field(default_factory=list)
```
  *(`Field` is already imported in this module — it's used by the surrounding DTOs.)*

- [ ] **Step 2 — add `fired_cxns` to `SceneTurnResponse`** (`scenes_dto.py`, in the class at 61-65, after `should_respond`):
```python
    fired_cxns: list[str] = Field(default_factory=list)
```
  Ensure `from pydantic import BaseModel, Field` at the top (add `Field` if the import is `from pydantic import BaseModel` only).

- [ ] **Step 3 — surface the fired ids from `_comprehend_and_activate`** (`backend.py`). Add a small internal result type near the top of the module (after the imports, before `class DSPyAgentBackend`), and import `dataclass`:
```python
from dataclasses import dataclass


@dataclass(frozen=True)
class _ComprehendOutcome:
    """What one comprehend step produced: the in-loop allowed-tools set (or
    None when not gating in-loop) AND the fired construct ids (for cxn_fired)."""

    allowed_tools: frozenset[str] | None = None
    fired_cxns: tuple[str, ...] = ()
```
  Then rewrite `_comprehend_and_activate` (120-163) to return `_ComprehendOutcome`, capturing `frame.applied_cxn_ids` on every non-early path and defaulting to `()`:
```python
    async def _comprehend_and_activate(self, msg: ProcessableMessage) -> _ComprehendOutcome:
        """Best-effort: comprehend the utterance, gate tools in-loop or push fired
        cxn ids, AND surface the fired construct ids (for the cxn_fired signal).

        Entirely best-effort — any failure (graph-memory down, gateway
        unreachable, malformed frame) is logged and swallowed: a comprehension
        miss must never fail the turn, and yields no fired cxns.
        """
        if self._cxn_gateway is None or not self._jwt_secret:
            return _ComprehendOutcome()
        fired: tuple[str, ...] = ()
        try:
            frame = await self.graph_memory.comprehend(
                bonfire_id=msg.bonfire_id,
                utterance=msg.message.text,
                profile=msg.agent_id,
                actor_id=msg.actor_id,
            )
            fired = tuple(frame.applied_cxn_ids)
            if self._in_loop_activation and self._cxn_manifest is not None:
                return _ComprehendOutcome(
                    allowed_tools=tools_for_turn(
                        fired_cxn_ids=frame.applied_cxn_ids,
                        manifest=self._cxn_manifest,
                        lease_warm=True,
                    ),
                    fired_cxns=fired,
                )
            bearer = sign_npc_jwt(
                msg.agent_id,
                secret=self._jwt_secret,
                ttl_seconds=3600,
                now=int(time.time()),
            )
            await self._cxn_gateway.push_activation(
                agent_id=msg.agent_id,
                cxn_ids=frame.applied_cxn_ids,
                bearer=bearer,
            )
        except Exception as exc:
            logger.warning(
                "cxn_gateway.comprehend_activate.degraded",
                extra={"agent_id": msg.agent_id, "bonfire_id": msg.bonfire_id, "error": str(exc)},
            )
        return _ComprehendOutcome(fired_cxns=fired)
```

- [ ] **Step 4 — unpack at the caller + thread into `PipelineOutput`** (`backend.py`, around 332-372). Replace line 332 and the `PipelineOutput(...)` build:
```python
        outcome = await self._comprehend_and_activate(msg)
        allowed_tools = outcome.allowed_tools
```
  (keep `allowed_tools=allowed_tools` at the `_run_pipeline_in_thread(...)` call, line 344, unchanged) and add `fired_cxns` to the returned `PipelineOutput`:
```python
        return PipelineOutput(
            response_text=result.response,
            image_prompt=result.image_prompt,
            retrieval_used=result.retrieval_path,
            sources=result.sources,
            tools_used=result.tools_used,
            should_respond=result.should_respond,
            fired_cxns=list(outcome.fired_cxns),
        )
```

- [ ] **Step 5 — serialize in the route** (`scenes_routes.py:197`):
```python
        return SceneTurnResponse(
            response_text=output.response_text,
            should_respond=output.should_respond,
            fired_cxns=output.fired_cxns,
        )
```
  *(`voice_turn`/`scene_runtime.py` passes `PipelineOutput` through unchanged — no edit there.)*

- [ ] **Step 6 — tests** (`tests/test_scenes_routes.py`). Extend `_RecordingBackend` to carry fired ids (default empty, so existing tests are unaffected):
```python
    def __init__(self, response_text: str = "npc voice response", fired_cxns: list[str] | None = None) -> None:
        self.calls: list[PipelineInput] = []
        self._response_text = response_text
        self._fired_cxns = fired_cxns or []

    async def process(self, pipeline_input: PipelineInput) -> PipelineOutput:
        self.calls.append(pipeline_input)
        return PipelineOutput(
            response_text=self._response_text,
            retrieval_used=RetrievalPath.NONE,
            should_respond=True,
            fired_cxns=self._fired_cxns,
        )
```
  Then add one focused test that builds the app with a fired-cxns backend and asserts the route surfaces it. **Mirror the existing app-construction fixture used by `test_turn_routes_utterance_under_self_id` (`:302-330`)** — build it with `_RecordingBackend(fired_cxns=["mm.look.v1"])` instead of the default — and assert:
```python
    body = resp.json()
    assert body["fired_cxns"] == ["mm.look.v1"]
```
  Also confirm the default path: an existing turn test (default backend) now returns `body["fired_cxns"] == []` (backward-compatible). *(Read `:290-330` for the exact app/client construction and copy it, swapping the backend.)*

- [ ] **Step 7 — run, verify pass** (from `services/agent-runtime/`):
```bash
uv run pytest tests/test_scenes_routes.py -q
```
Expected: green (the existing turn tests + the new `fired_cxns` assertion).

- [ ] **Step 8 — CHANGELOG entry** (`docs/migration/CHANGELOG.md`, under the current phase): one line — `agent-runtime: SceneTurnResponse now carries fired_cxns (the comprehend step's applied_cxn_ids) for the cxn_fired observability signal; additive, defaults to []`.

- [ ] **Step 9 — ruff-format + commit** (only the touched files):
```bash
cd services/agent-runtime && uv run ruff format src/app/modules/pipeline/pipeline_dto.py src/app/modules/pipeline/backend.py src/app/modules/scenes/scenes_dto.py src/app/modules/scenes/scenes_routes.py tests/test_scenes_routes.py
cd <repo-root> && git add services/agent-runtime/src/app/modules/pipeline/pipeline_dto.py services/agent-runtime/src/app/modules/pipeline/backend.py services/agent-runtime/src/app/modules/scenes/scenes_dto.py services/agent-runtime/src/app/modules/scenes/scenes_routes.py services/agent-runtime/tests/test_scenes_routes.py docs/migration/CHANGELOG.md
git commit -m "feat(agent-runtime): carry fired_cxns on the scene turn response

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Task 2 — gateway: emit a `cxn_fired` WS event (memento-mori)

**Files:**
- Modify: `gateway/src/gateway/scene_coordinator.py`
- Test: `gateway/tests/test_scene_coordinator.py`

**Interfaces:**
- Consumes: `turn.get("fired_cxns")` (Task 1's new field, already threaded through `drive_turn`).
- Produces: a `cxn_fired` WS event `{type:"cxn_fired", cxn, construct_id, actor_id, location}` per fired construct id, emitted before the narration broadcast, independent of `should_respond`.

- [ ] **Step 1 — add the display map + emitter** to `gateway/src/gateway/scene_coordinator.py`. Add a module-level map (near the top, after imports):
```python
# Construct id -> player-facing display name for the cxn_fired catch beat.
# The kernel returns predicate="" for the minimal LOOK, so we key on the id.
CXN_DISPLAY_NAMES: dict[str, str] = {"mm.look.v1": "LOOK"}
```
  And a private method (place beside `_npc_name`):
```python
    async def _broadcast_cxn_fired(self, turn: dict[str, Any], location_name: str) -> None:
        """Emit one cxn_fired WS event per fired construction (the catch beat).
        Best-effort: never breaks the turn; no-op when nothing fired."""
        if self._ws_hub is None:
            return
        fired = turn.get("fired_cxns") or []
        actor_id = turn.get("self_id")
        for construct_id in fired:
            display = CXN_DISPLAY_NAMES.get(construct_id, construct_id)
            logger.info(
                "cxn_fired: %s (%s) actor=%s loc=%s",
                display, construct_id, actor_id, location_name,
            )
            await self._ws_hub.broadcast_to_location(
                location_name,
                {
                    "type": "cxn_fired",
                    "cxn": display,
                    "construct_id": construct_id,
                    "actor_id": actor_id,
                    "location": location_name,
                },
            )
```
  *(`Any` is already imported in this module; `logger` is module-level.)*

- [ ] **Step 2 — call it** in `handle_player_message`, right after the `drive_turn` try/except (after line 159, before the `if turn.get("should_respond", True):` block at 161):
```python
        await self._broadcast_cxn_fired(turn, location_name)
```
  *(Before the narration, independent of `should_respond` — a cxn fired even if the agent chose silence.)*

- [ ] **Step 3 — failing test** (`gateway/tests/test_scene_coordinator.py`). Add a test that drives a turn whose response carries `fired_cxns` and asserts a `cxn_fired` broadcast precedes the `mm_npc_response` one. **Mirror the file's existing coordinator-construction helper and `_FakeHub`** (the fake driver returns the turn dict; the hub records `(location, message)` tuples). Add a fired-cxns driver + test:
```python
class _FiredDriver:
    async def drive_turn(self, loc, msg, *, addressed_name=None):
        return {
            "response_text": "You see a dim shape.",
            "should_respond": True,
            "self_id": "npc-1",
            "fired_cxns": ["mm.look.v1"],
        }


@pytest.mark.asyncio
async def test_cxn_fired_broadcast_precedes_narration():
    # build the coordinator with the file's existing helper/fakes, using _FiredDriver
    # (mirror how the other tests in this file construct SceneCoordinator + _FakeHub)
    ...  # registry/repo/hub/activation/resolver per the existing helper, driver=_FiredDriver()
    await coord.handle_player_message("p1", "Gate", "look around")
    kinds = [m["type"] for _, m in hub.broadcasts]
    assert "cxn_fired" in kinds
    fired = next(m for _, m in hub.broadcasts if m["type"] == "cxn_fired")
    assert fired["cxn"] == "LOOK" and fired["construct_id"] == "mm.look.v1"
    assert fired["actor_id"] == "npc-1" and fired["location"] == "Gate"
    # cxn_fired comes before the mm_npc_response narration
    assert kinds.index("cxn_fired") < kinds.index("tool_event")
```
  *(Read the existing tests in this file for the exact `SceneCoordinator(...)` construction + `_FakeHub`/`_FakeRepo`/`_FakeActivation`/`LocationResolver` wiring and the location-name→uuid cache, and fill the `...`. Use `_FiredDriver` as the activated driver.)*

- [ ] **Step 4 — run, verify pass:**
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_scene_coordinator.py -q
```
Expected: green (existing tests unaffected — `cxn_fired` is additive; the existing tests use drivers with no `fired_cxns`, so `_broadcast_cxn_fired` is a no-op for them).

- [ ] **Step 5 — ruff-format + commit:**
```bash
python3.12 -m ruff format gateway/src/gateway/scene_coordinator.py gateway/tests/test_scene_coordinator.py
git add gateway/src/gateway/scene_coordinator.py gateway/tests/test_scene_coordinator.py
git commit -m "feat(gateway): broadcast cxn_fired when a scene turn reports fired constructions

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Task 3 — client: render the "◇ caught: LOOK" catch beat (memento-mori)

**Files:**
- Modify: `client/src/state/opening-ws.ts`, `client/src/layers/prose-layer.ts`, `client/src/types/ws-messages.ts`
- Test: `client/src/state/opening-ws.test.ts`
- Regenerate: `client/app.js` (`bun run build`)

**Interfaces:**
- Consumes: the `cxn_fired` WS event (Task 2).
- Produces: a `"catch"`-kind prose segment rendered with a distinct accent.

- [ ] **Step 1 — add the `"catch"` segment kind** in `client/src/layers/prose-layer.ts:6-10` (extend the `Segment.kind` union):
```ts
  kind: "epigraph" | "location" | "description" | "narration" | "prompt" | "npc-name" | "npc-dialogue" | "catch";
```
  and give it an accent in `ProseLayer.render` (the color ternary at `:85-88`):
```ts
    const color =
      seg.kind === "catch"
        ? theme.colors.accent
        : seg.kind === "npc-name" || seg.kind === "npc-dialogue"
          ? theme.colors.npc
          : theme.colors.primary;
```
  *(`theme.colors.accent` = `#8b5cf6`, a distinct purple — the catch color.)*

- [ ] **Step 2 — widen the `OpeningSurfaces` enqueue kind** in `client/src/state/opening-ws.ts:8-10` so `"catch"` is accepted (match the union edit from Step 1 in the `prose.enqueue` parameter type).

- [ ] **Step 3 — add the `cxn_fired` case** in `routeOpeningMessage` (`opening-ws.ts`, in the `switch`):
```ts
    case "cxn_fired":
      s.prose.enqueue({ kind: "catch", text: `◇ caught: ${(msg.cxn as string) ?? ""}` });
      s.redrawProse();
      break;
```

- [ ] **Step 4 — add the typed message** in `client/src/types/ws-messages.ts` (a new interface + add to the `WsMessage` union at `:130-148`):
```ts
export interface CxnFiredMessage {
  type: 'cxn_fired';
  cxn: string;
  construct_id?: string;
  actor_id?: string;
  location?: string;
}
```

- [ ] **Step 5 — failing test** (`client/src/state/opening-ws.test.ts`, in the style of the `mm_npc_response` test at `:30-35`):
```ts
test("cxn_fired becomes a catch prose segment", () => {
  const s = makeSurfaces();
  routeOpeningMessage({ type: "cxn_fired", cxn: "LOOK", construct_id: "mm.look.v1" }, s.surfaces);
  expect(s.enqueued).toEqual([{ kind: "catch", text: "◇ caught: LOOK" }]);
  expect(s.redraws).toBe(1);
});
```

- [ ] **Step 6 — run tests, then rebuild:**
```bash
cd client && bun test src/state/opening-ws.test.ts
```
Expected: the new test + the existing opening-ws tests pass. Then regenerate the served bundle:
```bash
cd client && bun run build
```
Expected: `app.js` rewritten with the `cxn_fired` case compiled in.

- [ ] **Step 7 — prettier + commit** (include the regenerated `app.js`):
```bash
cd client && bunx prettier --write src/state/opening-ws.ts src/layers/prose-layer.ts src/types/ws-messages.ts src/state/opening-ws.test.ts
git add client/src/state/opening-ws.ts client/src/layers/prose-layer.ts client/src/types/ws-messages.ts client/src/state/opening-ws.test.ts client/app.js
git commit -m "feat(client): render the cxn_fired catch beat in the opening prose pane

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
  *(If the repo doesn't use prettier via bunx, match whatever `client/package.json` provides for formatting; if none, skip formatting and commit as-is.)*

---

## Verification (end-to-end)

1. **agent-runtime (Task 1):** `SceneTurnResponse.fired_cxns` carries the comprehend step's `applied_cxn_ids`; `_comprehend_and_activate` surfaces them via `_ComprehendOutcome` on every non-early path (empty on miss/early/exception); the route serializes them; backward-compatible (default `[]`). Route tests + CHANGELOG.
2. **gateway (Task 2):** `SceneCoordinator` emits one `cxn_fired` WS event per fired construct id (id→display via `CXN_DISPLAY_NAMES`), logged, before the narration and independent of `should_respond`; no-op when `fired_cxns` is empty/absent (existing tests unaffected). 1 test.
3. **client (Task 3):** a `cxn_fired` event renders a `"catch"`-kind segment ("◇ caught: LOOK") in the prose pane with a distinct accent; typed `CxnFiredMessage` added; `app.js` regenerated. 1 test.
4. **The slice's headline mechanic now lands** against a *stubbed* comprehend result — no live kernel, no player-persona required (those are Plans 4–5). End to end: a turn that fires `mm.look.v1` → `fired_cxns:["mm.look.v1"]` → gateway `cxn_fired` WS → client "◇ caught: LOOK".

## What this plan deliberately does NOT do (later plans)

- **Plan 4:** player-as-persona `SelfDto` creation at `/v1/scenes/{deep_roads}/open`; `mm_look` in the agent-runtime `MEMENTO_MANIFEST` + a `get_allowed_tools` kit/label (so `mm_look` becomes *callable* — until then the capability gate denies it, by design); authoring the kernel LOOK grammar at bring-up. This is what makes a *real* (non-stubbed) comprehend actually fire LOOK on the player's turn.
- **Plan 5:** the client `room_draw` handler that adds the new glyph to the map viewport; the cinematic intro (epigraph fade + name box); retiring the legacy overlay; look narration attributed to the player-self.
- **api-contracts / OpenAPI regen:** if the repo's `docs-check.yml` CI requires regenerating `packages/api-contracts` for the `SceneTurnResponse` field, that is a PR-time step (this plan commits to the feature branch only; the CHANGELOG entry satisfies rule 14).
