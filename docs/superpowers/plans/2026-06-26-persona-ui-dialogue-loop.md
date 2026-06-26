# Persona UI Integration — P1: Dialogue Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Fresh implementer per task, per-task review, whole-branch opus review at the end. Steps use `- [ ]` checkboxes. Spec: `bonfires-ai-core/docs/superpowers/specs/2026-06-26-persona-ui-integration-design.md` (this plan is **P1** of three phases; P2 reachability + P3 provisioning get their own plans later).

## Context

The persona/scene NPC system (gateway `RoomDriver` → agent-runtime `/v1/scenes`) is fully parallel to what the UI uses, with no path to the client. The live player loop is `POST /api/action {player_id, action, location}` (fire-and-forget, returns `{status:"queued"}`); **all rendering is async over WebSocket**. NPC dialogue already renders from a WS `tool_event` with `tool:"mm_npc_response"` (NPC name + dialogue block) — but the persona path's `drive_turn` returns its reply to the *caller* and never broadcasts. **P1 wires the dialogue loop:** when a player's `/api/action` message hits a location with an **already-active** persona scene, route it to that scene's `RoomDriver.drive_turn` and broadcast the NPC reply over the existing `tool_event/mm_npc_response` WS path so the current client renders it — no client change. (Auto-activation + NPC seeding are **P2**; provisioning is **P3** — P1 assumes a scene is already registered, e.g. via the existing `/api/scenes/{loc}/activate`.)

**Goal:** A player `/api/action` message at a location with an active persona scene drives `RoomDriver.drive_turn` and broadcasts the NPC reply (`tool_event/mm_npc_response`) to that location; when no scene is active, the existing `RoundManager`/Matrix path runs unchanged.

**Architecture:** A new `SceneCoordinator` (gateway) owns the persona-routing decision (resolve player→`location_uuid`, look up the registered `RoomDriver`, `drive_turn`, broadcast), keeping `submit_action` thin. `drive_turn` is extended to return the acting NPC's `self_id` so the broadcast can label the speaker. Rendering reuses the existing WS `tool_event` shape.

**Tech Stack:** Python 3.12 (memento-mori gateway + engine), FastAPI/Starlette, httpx. Tests: `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest <path> -q`.

## Branch & base

- **mmori branch:** `persona/ui-dialogue-loop`, off `opening/engine-core` (HEAD `8a0f8b4`, which carries the scene-activation slice).
- Use an **isolated worktree**: `git worktree add -b persona/ui-dialogue-loop <scratchpad>/mmori-uidlg-wt opening/engine-core`. Work from the worktree; read files from it (the main checkout is on a different branch — wrong-tree trap).

## Global Constraints

- Commit trailer (exact): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Never `git add -A`** — stage only the files each task touches. PR targets this lineage's base, never main.
- No cross-service Python imports (plain dicts on the wire). No `Any` in new service signatures **except** the `repo`/`state` params (Protocol/app-state namespaces, matching the existing `RoomDriver(repo: Any)` and `SceneActivationService.from_app_state(state: Any)` conventions).
- Services raise **domain exceptions, not `HTTPException`** — and **a persona failure must never break the action path** (the branch degrades to the existing path / a logged no-op, never 500s `/api/action`).
- UUIDs for entity/scene identity; the location **name** string is used only for `ws_hub` broadcast targeting (`broadcast_to_location` is keyed on the name).
- Ruff-format only the files each task touches (not the whole tree — the base isn't ruff-clean).

## Key existing symbols (reuse, don't reinvent) — verbatim anchors on `opening/engine-core`

- **`submit_action`** — `gateway/src/gateway/routes/action.py` (`POST /api/action`, model `ActionRequest{player_id, action, location:""}`, returns `ActionResponse(status="queued")`). Handler has **no `request: Request` param** (must be added to reach `request.app.state`). It imports module globals `from gateway.app import round_manager, ws_hub`; calls `await ws_hub.set_location(req.player_id, req.location)` then `await round_manager.submit_action(req.player_id, req.player_id, req.location, req.action)` + a solo fast-path `await round_manager.close_round(req.location)`.
- **`RoomDriver.drive_turn(location_uuid, player_message, *, addressed_name=None) -> dict`** — `gateway/src/gateway/room_driver.py`. Resolves `actor_uuid = self._resolve_actor_uuid(...)` (addressed-name via `npc_registry`, else single-NPC fallback from `self._last_roster_uuids[location_uuid]`); raises `ValueError` if none; POSTs `/v1/scenes/{loc}/turn` body `{self_id, message}`; returns `resp.json()` verbatim = `{"response_text": str, "should_respond": bool}` (default `True`) — **does NOT include the actor id** (`actor_uuid` is in scope at the return, only logged).
- **`app.state.scene_registry`** — `dict[str, RoomDriver]` (location_uuid → live `RoomDriver`), set in `app.py` lifespan; populated by `SceneActivationService.activate`. `app.state.cxn_repo` (the world `StateRepository`) and `app.state.ws_hub` are also set in lifespan.
- **`_get_location_uuid(player_id) -> str | None`** — `gateway/src/gateway/routes/codex.py` (module-level async; resolves `ws_hub.player_locations[player_id]` name → KG search → `Location`-labelled uuid, with a `world.json` threshold fallback). Reused by `routes/action.py:sync_position` via lazy import. Monkeypatchable in tests.
- **`WebSocketHub.broadcast_to_location(location, message)`** — `gateway/src/gateway/ws.py`; sends `message` to every player whose `player_locations[pid] == location` (keyed on the location **name** string). `set_location(player_id, location)` populates `player_locations`.
- **Client render contract** (no change needed) — the client renders a WS message `{type:"tool_event", tool:"mm_npc_response", npc:<name>, summary:<dialogue>, location:<name>}` as an NPC-name + dialogue block (`client/src/message-handler.ts`). `engine_events.broadcast_tool_event` builds this shape but derives location from the npc registry (unreliable here) — **P1 broadcasts the same shape directly to the player's location name** instead.
- **Repo entity read** — `await app.state.cxn_repo.get_entity(uuid) -> dict | None` (async; the dict has `"name"`). Used to resolve the acting NPC's display name.
- **Test patterns** — `gateway/tests/test_scene_activation_route.py` + `test_gm_room_loop_e2e.py`: import the real `from gateway.app import app`, inject `app.state.*`, drive via `httpx.ASGITransport(app=app)`; agent-runtime stub = a Starlette app recording `/v1/scenes/{id}/turn` returning `{"response_text":..., "should_respond":...}`. `ws_hub`/`round_manager` are **module globals** — tests must `monkeypatch.setattr("gateway.app.ws_hub", fake)` / `"gateway.app.round_manager", fake`.

---

# Movement 1 — engine/gateway: name the speaker

## Task 1 — `RoomDriver.drive_turn` returns the acting `self_id`

**Files:**
- Modify: `gateway/src/gateway/room_driver.py`
- Test: `gateway/tests/test_room_driver.py`

**Interfaces:**
- Produces: `drive_turn` returns `{**agent_runtime_json, "self_id": <acting actor_uuid>}` — additive (`response_text`/`should_respond` unchanged). Task 2 consumes `turn["self_id"]`.

- [ ] **Step 1 — failing test** (add to `gateway/tests/test_room_driver.py`; reuse its `_Recorder` + Starlette stub pattern — the stub's `/v1/scenes/{room_id}/turn` returns `{"response_text":"ok","should_respond":true}`). Build a `RoomDriver` over the stub client, seed its roster so the single-NPC fallback resolves, and assert the returned dict carries `self_id`:
```python
@pytest.mark.asyncio
async def test_drive_turn_returns_acting_self_id(<client fixture>):
    driver = RoomDriver(repo=InMemoryStateRepository(), agent_runtime_client=<stub client>, bonfire_id="b1")
    driver._last_roster_uuids["loc-1"] = {"npc-1"}          # single-NPC fallback target
    turn = await driver.drive_turn("loc-1", "hello")
    assert turn["response_text"] == "ok"
    assert turn["self_id"] == "npc-1"                        # NEW: speaker named
```

- [ ] **Step 2 — run, verify fail:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_room_driver.py -q -k drive_turn_returns_acting_self_id` → FAIL (`KeyError: 'self_id'`).

- [ ] **Step 3 — implement** — in `drive_turn`, change the success return so the resolved actor id is included (additive). Replace `return data` with:
```python
            return {**data, "self_id": actor_uuid}
```
(`actor_uuid` is already resolved at the top of the method and in scope at the return.)

- [ ] **Step 4 — run, verify pass:** same `-k` command → PASS; then the whole file `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_room_driver.py -q` → green (the additive key does not break existing `drive_turn` assertions, which read `response_text`).
- [ ] **Step 5 — commit** (stage room_driver.py + test) — `feat(gateway): drive_turn returns the acting self_id`.

---

# Movement 2 — gateway: the scene coordinator

## Task 2 — `SceneCoordinator.handle_player_message`

**Files:**
- Create: `gateway/src/gateway/scene_coordinator.py`
- Test: `gateway/tests/test_scene_coordinator.py` (new)

**Interfaces:**
- Consumes: `app.state.scene_registry` (location_uuid → `RoomDriver`), `app.state.cxn_repo`, `app.state.ws_hub`; `_get_location_uuid(player_id)`; `drive_turn` (Task 1, returns `self_id`).
- Produces: `SceneCoordinator.from_app_state(state) -> SceneCoordinator`; `async handle_player_message(player_id, location_name, message) -> bool` (True = the persona path handled it; False = caller falls through to the existing path).

- [ ] **Step 1 — write the coordinator** (`gateway/src/gateway/scene_coordinator.py`):
```python
"""Routes a player message to an active persona scene's RoomDriver and broadcasts
the NPC reply over the existing WS tool_event path. Keeps submit_action thin.

P1 scope: assumes a scene is ALREADY registered for the location (auto-activation
is P2). handle_player_message returns False (no-op) whenever a persona scene is
not available, so the caller falls through to the existing RoundManager path.
"""

from __future__ import annotations

from typing import Any

from gateway.log import get_logger

logger = get_logger(__name__)


class SceneCoordinator:
    def __init__(self, *, scene_registry: Any, cxn_repo: Any, ws_hub: Any) -> None:
        self._registry = scene_registry
        self._repo = cxn_repo
        self._ws_hub = ws_hub

    @classmethod
    def from_app_state(cls, state: Any) -> "SceneCoordinator":
        # Tolerant: scene infra may be absent (e.g. lifespan not run) -> no-op path.
        return cls(
            scene_registry=getattr(state, "scene_registry", None),
            cxn_repo=getattr(state, "cxn_repo", None),
            ws_hub=getattr(state, "ws_hub", None),
        )

    async def handle_player_message(
        self, player_id: str, location_name: str, message: str
    ) -> bool:
        if self._registry is None or self._ws_hub is None:
            return False
        from gateway.routes.codex import _get_location_uuid

        location_uuid = await _get_location_uuid(player_id)
        if not location_uuid:
            return False
        driver = self._registry.get(location_uuid)
        if driver is None:
            return False

        try:
            turn = await driver.drive_turn(location_uuid, message)
        except Exception as exc:  # persona failure must NOT break the action path
            logger.warning("scene_coordinator.drive_turn_failed: %s", exc)
            return True  # claimed by the persona path; degrade to silence, not 500

        if turn.get("should_respond", True):
            npc_name = await self._npc_name(turn.get("self_id"))
            msg = {
                "type": "tool_event",
                "tool": "mm_npc_response",
                "npc": npc_name,
                "summary": turn.get("response_text", ""),
                "data": {},
                "location": location_name,
                "channel": "narrative",
            }
            await self._ws_hub.broadcast_to_location(location_name, msg)
        return True

    async def _npc_name(self, self_id: str | None) -> str:
        if not self_id or self._repo is None:
            return ""
        try:
            entity = await self._repo.get_entity(self_id)
        except Exception:
            return ""
        return entity.get("name", "") if entity else ""
```
  *(`get_logger` is the gateway's existing logger factory — confirm the import path against another gateway module, e.g. `room_driver.py`'s `logger = get_logger(__name__)`; match it.)*

- [ ] **Step 2 — failing tests** (`gateway/tests/test_scene_coordinator.py`) — fakes for registry/driver/repo/ws_hub; monkeypatch `_get_location_uuid`:
```python
import pytest

from gateway.scene_coordinator import SceneCoordinator


class _FakeDriver:
    def __init__(self): self.calls = []
    async def drive_turn(self, loc, msg, *, addressed_name=None):
        self.calls.append((loc, msg))
        return {"response_text": "Halt!", "should_respond": True, "self_id": "npc-1"}


class _FakeRepo:
    async def get_entity(self, uuid):
        return {"uuid": uuid, "name": "Gareth"} if uuid == "npc-1" else None


class _FakeHub:
    def __init__(self): self.broadcasts = []
    async def broadcast_to_location(self, location, message):
        self.broadcasts.append((location, message))


def _patch_loc(monkeypatch, value):
    async def _fake(_pid): return value
    monkeypatch.setattr("gateway.routes.codex._get_location_uuid", _fake)


@pytest.mark.asyncio
async def test_handles_message_when_scene_active_and_broadcasts(monkeypatch):
    driver, hub = _FakeDriver(), _FakeHub()
    coord = SceneCoordinator(scene_registry={"loc-1": driver}, cxn_repo=_FakeRepo(), ws_hub=hub)
    _patch_loc(monkeypatch, "loc-1")
    handled = await coord.handle_player_message("p1", "North Gate", "Gareth, may I pass?")
    assert handled is True
    assert driver.calls == [("loc-1", "Gareth, may I pass?")]
    assert len(hub.broadcasts) == 1
    loc, msg = hub.broadcasts[0]
    assert loc == "North Gate"
    assert msg["type"] == "tool_event" and msg["tool"] == "mm_npc_response"
    assert msg["npc"] == "Gareth" and msg["summary"] == "Halt!"
    assert msg["location"] == "North Gate"


@pytest.mark.asyncio
async def test_no_scene_registered_returns_false(monkeypatch):
    hub = _FakeHub()
    coord = SceneCoordinator(scene_registry={}, cxn_repo=_FakeRepo(), ws_hub=hub)
    _patch_loc(monkeypatch, "loc-1")
    handled = await coord.handle_player_message("p1", "North Gate", "hi")
    assert handled is False
    assert hub.broadcasts == []


@pytest.mark.asyncio
async def test_unresolved_location_returns_false(monkeypatch):
    coord = SceneCoordinator(scene_registry={"loc-1": _FakeDriver()}, cxn_repo=_FakeRepo(), ws_hub=_FakeHub())
    _patch_loc(monkeypatch, None)
    assert await coord.handle_player_message("p1", "Nowhere", "hi") is False


@pytest.mark.asyncio
async def test_should_respond_false_suppresses_broadcast(monkeypatch):
    class _Quiet(_FakeDriver):
        async def drive_turn(self, loc, msg, *, addressed_name=None):
            return {"response_text": "", "should_respond": False, "self_id": "npc-1"}
    hub = _FakeHub()
    coord = SceneCoordinator(scene_registry={"loc-1": _Quiet()}, cxn_repo=_FakeRepo(), ws_hub=hub)
    _patch_loc(monkeypatch, "loc-1")
    assert await coord.handle_player_message("p1", "North Gate", "hi") is True
    assert hub.broadcasts == []


@pytest.mark.asyncio
async def test_drive_turn_failure_degrades_without_raising(monkeypatch):
    class _Boom(_FakeDriver):
        async def drive_turn(self, loc, msg, *, addressed_name=None):
            raise RuntimeError("agent-runtime down")
    hub = _FakeHub()
    coord = SceneCoordinator(scene_registry={"loc-1": _Boom()}, cxn_repo=_FakeRepo(), ws_hub=hub)
    _patch_loc(monkeypatch, "loc-1")
    # claimed by the persona path (True) but no broadcast and no exception
    assert await coord.handle_player_message("p1", "North Gate", "hi") is True
    assert hub.broadcasts == []
```

- [ ] **Step 3 — run, verify pass:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_scene_coordinator.py -q` → 5 passed. (If `gateway.log.get_logger` isn't the right import, fix the coordinator's logger import to match the gateway convention and re-run.)
- [ ] **Step 4 — commit** (stage scene_coordinator.py + test) — `feat(gateway): SceneCoordinator routes player messages to active persona scenes`.

---

# Movement 3 — gateway: the action-path branch

## Task 3 — Branch `submit_action` into the persona path

**Files:**
- Modify: `gateway/src/gateway/routes/action.py`
- Test: `gateway/tests/test_action_persona_branch.py` (new)

**Interfaces:**
- Consumes: `SceneCoordinator.from_app_state` + `handle_player_message` (Task 2).
- Produces: `submit_action` gains `request: Request`; after `set_location`, calls the coordinator; if handled, returns `{status:"queued"}` without invoking `round_manager`; else the existing round path runs unchanged.

- [ ] **Step 1 — implement the branch** in `gateway/src/gateway/routes/action.py`:
  - Add `Request` to the FastAPI import: `from fastapi import APIRouter, Request`.
  - Change the handler signature to `async def submit_action(req: ActionRequest, request: Request):`.
  - Insert the persona branch immediately AFTER the `set_location` block and BEFORE the `if round_manager:` block:
```python
    # Persona branch: if a persona scene is active at the player's location, the
    # persona NPC handles the message and we skip the round path. Otherwise fall
    # through. A persona failure never breaks the action (coordinator degrades).
    from gateway.scene_coordinator import SceneCoordinator

    coordinator = SceneCoordinator.from_app_state(request.app.state)
    if await coordinator.handle_player_message(req.player_id, req.location, req.action):
        return ActionResponse(status="queued")
```

- [ ] **Step 2 — integration test** (`gateway/tests/test_action_persona_branch.py`) — real app, injected `app.state`, monkeypatched module globals + `_get_location_uuid`, a stub agent-runtime, asserting BOTH branches:
```python
import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from memento.state.in_memory import InMemoryStateRepository
from gateway.room_driver import RoomDriver


class _Hub:
    def __init__(self): self.broadcasts = []; self.locs = {}
    async def set_location(self, pid, loc): self.locs[pid] = loc
    async def broadcast_to_location(self, loc, msg): self.broadcasts.append((loc, msg))
    def players_at_location(self, loc): return 1


class _RM:
    def __init__(self): self.submitted = []
    async def submit_action(self, *a): self.submitted.append(a)
    async def close_round(self, loc): ...


def _turn_stub(recorder):
    async def _turn(request: Request):
        recorder.append(await request.json())
        return JSONResponse({"response_text": "Halt, traveler.", "should_respond": True})
    return Starlette(routes=[Route("/v1/scenes/{rid}/turn", _turn, methods=["POST"])])


async def _wire(monkeypatch, loc_uuid):
    from gateway.app import app
    repo = InMemoryStateRepository()
    repo.seed_entity({"uuid": "npc-1", "kind": "character", "name": "Gareth",
                      "labels": ["Character", "NPC"], "location_uuid": loc_uuid,
                      "attrs": {"hp": 10, "max_hp": 10, "inventory": []}, "is_dead": False})
    recorder = []
    ar_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=_turn_stub(recorder)),
                                  base_url="http://ar-stub")
    driver = RoomDriver(repo=repo, agent_runtime_client=ar_client, bonfire_id="b1")
    driver._last_roster_uuids[loc_uuid] = {"npc-1"}
    hub, rm = _Hub(), _RM()
    app.state.cxn_repo = repo
    app.state.ws_hub = hub
    app.state.scene_registry = {loc_uuid: driver}
    monkeypatch.setattr("gateway.app.ws_hub", hub)
    monkeypatch.setattr("gateway.app.round_manager", rm)

    async def _loc(_pid): return loc_uuid
    monkeypatch.setattr("gateway.routes.codex._get_location_uuid", _loc)
    return app, repo, hub, rm, recorder, ar_client


@pytest.mark.asyncio
async def test_action_in_scene_drives_persona_and_broadcasts(monkeypatch):
    app, repo, hub, rm, recorder, ar_client = await _wire(monkeypatch, "loc-1")
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://testserver") as gw:
            resp = await gw.post("/api/action",
                                 json={"player_id": "p1", "action": "Gareth, may I pass?",
                                       "location": "North Gate"})
            assert resp.status_code == 200
        assert len(recorder) == 1 and recorder[0]["self_id"] == "npc-1"   # agent-runtime got the turn
        assert rm.submitted == []                                          # round path skipped
        assert len(hub.broadcasts) == 1
        loc, msg = hub.broadcasts[0]
        assert loc == "North Gate" and msg["tool"] == "mm_npc_response"
        assert msg["npc"] == "Gareth" and msg["summary"] == "Halt, traveler."
    finally:
        await ar_client.aclose()


@pytest.mark.asyncio
async def test_action_without_scene_falls_through_to_round_path(monkeypatch):
    # location_uuid resolves but NO scene registered for it -> existing path runs
    app, repo, hub, rm, recorder, ar_client = await _wire(monkeypatch, "loc-1")
    app.state.scene_registry = {}                                          # no active scene
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://testserver") as gw:
            resp = await gw.post("/api/action",
                                 json={"player_id": "p1", "action": "look around",
                                       "location": "North Gate"})
            assert resp.status_code == 200
        assert recorder == []                                              # agent-runtime NOT called
        assert len(rm.submitted) == 1                                      # round path ran
        assert hub.broadcasts == []                                        # no persona broadcast
    finally:
        await ar_client.aclose()
```

- [ ] **Step 3 — run, verify pass:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_action_persona_branch.py -q` → 2 passed. Run twice (the tests mutate the module-level `app`/`gateway.app` globals) to confirm determinism.
- [ ] **Step 4 — regression smoke:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests -q` → green except the pre-existing unrelated `test_round_callback.py::test_send_batch_to_matrix` (confirm it's the only failure and unchanged).
- [ ] **Step 5 — commit** (stage action.py + the test) — `feat(gateway): /api/action branches to the persona scene when one is active`.

---

## Verification (end-to-end)

1. **Speaker named (Task 1):** `drive_turn` returns `self_id` additively; `test_room_driver.py` green (existing `response_text` assertions unaffected).
2. **Coordinator (Task 2):** `test_scene_coordinator.py` — handles a message when a scene is active (drives `drive_turn` + broadcasts a `tool_event/mm_npc_response` to the player's location name with the resolved NPC name); returns `False` when no scene / no location; suppresses the broadcast on `should_respond=False`; degrades (no raise, no broadcast) on a `drive_turn` failure.
3. **Action branch (Task 3):** `test_action_persona_branch.py` (twice) — `/api/action` at a scene-active location drives the persona turn (agent-runtime stub receives `/turn` with the resolved `self_id`), the round path is skipped, and a `tool_event/mm_npc_response` is broadcast to the player's location; `/api/action` with no active scene falls through to `round_manager.submit_action` with no persona call and no broadcast.
4. **No regression:** full gateway suite green except the pre-existing unrelated `test_round_callback.py::test_send_batch_to_matrix`.
5. **Whole-branch opus review:** the branch is additive and non-intrusive (existing path is the default/fallback); a persona failure never 500s `/api/action`; the broadcast reuses the exact client-rendered `tool_event/mm_npc_response` shape keyed on the player's location name; `drive_turn`'s return change is additive; no `Any` beyond the repo/state conventions; no whole-tree ruff churn.
6. **Live demo (manual, optional):** against the bring-up stack, activate a scene (`/api/scenes/{loc}/activate`) with a seeded NPC, then `POST /api/action` at that location and observe the NPC reply rendered in the connected client — the P1 capstone.

## Out of scope (P2 / P3)

- **Auto-activation + NPC seeding + location name↔uuid `LocationResolver`** (P2) — P1 assumes a scene is already registered (e.g. via `/api/scenes/{loc}/activate`) and uses `_get_location_uuid` directly.
- **Provisioning** (P3): gateway bonfire-id resolution (graph-memory ObjectId), KG-backed `cxn_repo` wiring, multi-NPC who-acts beyond the existing addressed-name + single-NPC fallback.
- **Matrix cutover**, persona narration/gossip/combat dialogue, client UX for targeting NPCs — later.

## On approval

Execute via superpowers:subagent-driven-development on a worktree branch `persona/ui-dialogue-loop` off `opening/engine-core` (8a0f8b4), T1→T3. Copy this plan to `memento-mori/docs/superpowers/plans/2026-06-26-persona-ui-dialogue-loop.md` and commit (in the worktree) before dispatching Task 1.
