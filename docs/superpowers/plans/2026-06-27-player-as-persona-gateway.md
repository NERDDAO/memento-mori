# Player-as-Persona Opening (gateway) — Implementation Plan (Slice 1, Plan 5 of N)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax. Spec: `docs/superpowers/specs/2026-06-27-player-as-persona-opening-design.md` (Component B). This plan delivers the **gateway** pieces B1–B4 that make the player a self-agent who can take its own "look around" turn (→ LOOK fires → `mm_look` runs → room drawn + narrated). **Gateway-only** — the agent-runtime already accepts a `seat="LLM"` human-less self (verified). The client one-shot look trigger (B-client) is deferred to Plan 6 (which owns the client opening flow + cinematic intro).

**Goal:** A player can be made a self-agent in the Deep Roads scene and driven through a "look around" turn that fires LOOK and calls `mm_look` — all over the gateway, demonstrable via `POST /api/opening/start` then `POST /api/opening/look`.

**Architecture:** Three additive gateway tasks. (1) Two new `RoomDriver` methods: `open_player_scene` (open a scene with the player as `gm_self`, empty roster) and `drive_self_turn` (POST `/turn` with a forced `self_id`, bypassing the NPC who-acts resolver). (2) `/opening/start` also seeds the player into `app.state.cxn_repo` (so `mm_look` resolves its location) and opens the player scene — both best-effort/non-fatal. (3) A new `/opening/look` route that drives the player's "look around" turn and broadcasts `cxn_fired` + a player-attributed narration over WS (`room_draw` rides along from the `mm_look` tool).

**Tech Stack:** Python 3.12, FastAPI/Starlette gateway, httpx. Tests: `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest <path> -q` (gateway tests use `@pytest.mark.asyncio`).

## Branch & base

- **Branch:** `opening/cxn-catch` (HEAD `d7b1feb` after the Plan 5 spec). Worktree `<scratchpad>/mmori-cxn-catch`. Single repo (memento-mori), gateway-only.

## Global Constraints

- Commit trailer — **BOTH lines, exact, every commit:**
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01TmmDb5v2f2mae5pmRWtqBZ
  ```
- **Never `git add -A`** — stage only the files each task touches.
- Every new gateway path is **best-effort / non-fatal**: B1 player-seed, B2 scene-open, B3/B4 turn — a failure must NEVER break `/opening/start` or 500 `/opening/look`; degrade to a logged no-op (mirrors the existing `/opening/act` persona-hook `try/except … logger.warning(..., exc_info=True)`).
- `drive_self_turn` POSTs with a **caller-supplied `self_id`** (no `_resolve_actor_uuid`); the existing `drive_turn` NPC path is UNCHANGED.
- The player is seeded into `app.state.cxn_repo` with labels `["Character"]` — `mm_look` is innate (Plan 4), so no extra label is needed; the player carries no `reveal_level` (it is not a reveal candidate).
- `os.environ`/`os.getenv` reads stay in the gateway (existing pattern). No agent-runtime/bonfires-ai-core change.
- Ruff-format only the files each task touches.

## Key existing symbols (verbatim anchors on `opening/cxn-catch`)

- **`RoomDriver`** — `gateway/src/gateway/room_driver.py`. `__init__(*, repo, agent_runtime_client, bonfire_id, internal_token="", player_labels=None, projection=None)` (`:88`). Helpers: `_embodiment_id(engine_uuid)` (`:120`), `_request_headers()` (`:149-151` → `{"X-Internal-Token": self._internal_token}`), `get_allowed_tools` imported at module top. `open_room` POSTs `/v1/scenes/{loc}/open` with body `{bonfire_id, scene_actor_id, gm_self, roster}` (`:216-236`); `drive_turn` POSTs `/v1/scenes/{loc}/turn` body `{self_id, message}` and returns `{**data, "self_id": actor_uuid}` (`:263-281`). `build_agent_runtime_client()` (`:45-58`) → httpx.AsyncClient (base_url `AGENT_RUNTIME_BASE_URL`, header `X-Internal-Token`).
- **`/opening/start`** — `gateway/src/gateway/routes/opening.py:158-265`. `async def start_opening(req: StartOpeningRequest) -> StartOpeningResponse` (NO `request: Request` today — must add it). Seeds the player into the per-player `repo` (`:196-206`, labels `["Character"]`, at `LOC_DEEP_ROADS`); `player_uuid = _uuid_mod.uuid4().hex` (`:178`); `LOC_DEEP_ROADS` imported `:194`; registers `opening_registry`/`opening_repos` (`:249-250`); returns `StartOpeningResponse` (`:256`). `logger` (`:55`), `BONFIRE_ID = resolve_bonfire_id()` (`:70`). `from fastapi import APIRouter, HTTPException, Request` already imports `Request` (`:49`).
- **`/opening/act`** — `opening.py:268-310` — the best-effort persona-hook pattern to mirror: `from gateway.app import ws_hub`; `if ws_hub is not None: await ws_hub.set_location(player_id, "the deep roads")`; `SceneCoordinator.from_app_state(request.app.state)`; wrapped `try/except … logger.warning(..., exc_info=True)`.
- **`CXN_DISPLAY_NAMES`** — `gateway/src/gateway/scene_coordinator.py` (Plan 3 Task 2): module-level `{"mm.look.v1": "LOOK"}`. Importable.
- **`WebSocketHub`** — `gateway/src/gateway/ws.py`: `set_location(player_id, name)`, `broadcast_to_location(location, msg)`. The narration shape that renders in the opening client is the `tool_event`/`mm_npc_response` dict (`scene_coordinator.py:163-171`): `{type:"tool_event", tool:"mm_npc_response", npc:<name>, summary:<text>, data:{}, location, channel:"narrative"}`. The client opening adapter (`opening-ws.ts`) only renders `mm_npc_response` when `msg.npc` is truthy — so the narration MUST carry a non-empty `npc` (the player's name).
- **`app.state`** — `gateway/src/gateway/app.py`: `app.state.cxn_repo` (`:65`), `app.state.agent_runtime_client` (`:67`), `app.state.bonfire_id` (`:72`). Module-global `ws_hub`.
- **Repos** — `InMemoryStateRepository` (`memento.state.in_memory`): `seed_entity` SYNC, `get_entity` ASYNC. `EventSourcedStateRepository`: `seed_entity` ASYNC. (Handle both with `inspect.isawaitable`.)
- **Tests** — `gateway/tests/test_room_driver.py` (stubs `/open` + `/turn` via a Starlette ASGITransport app returning JSON; capabilities assertion at `:544`). `gateway/tests/test_opening_routes.py` (autouse `_patch_opening_hooks` monkeypatches `build_comprehension/build_memory/build_mirror/build_projection` to fakes; `app_transport = httpx.ASGITransport(app=app)`; `make_client`; T1 at `:124-152` asserts `data["player_id"]` + `player_id in opening_mod.opening_registry`).

## File Structure

- `gateway/src/gateway/room_driver.py` — `open_player_scene` + `drive_self_turn` (Task 1).
- `gateway/src/gateway/routes/opening.py` — `request: Request` on `start_opening`; B1 player-seed + B2 open-player-scene; new `/opening/look` route + `LookRequest` (Tasks 2 + 3).
- `gateway/tests/test_room_driver.py` (Task 1), `gateway/tests/test_opening_player_scene.py` (new, Tasks 2+3).

---

# Task 1 — `RoomDriver.open_player_scene` + `drive_self_turn`

**Files:**
- Modify: `gateway/src/gateway/room_driver.py`
- Test: `gateway/tests/test_room_driver.py`

**Interfaces:**
- Produces: `async open_player_scene(location_uuid, player_uuid, player_name, player_labels) -> dict` (POSTs `/open` with the player as `gm_self`, empty roster). `async drive_self_turn(location_uuid, self_id, message) -> dict` (POSTs `/turn` with a forced `self_id`; returns `{**data, "self_id": self_id}`). Consumed by Tasks 2 + 3.

- [ ] **Step 1 — add the two methods** to `RoomDriver` (after `drive_turn`, before `close_room`):
```python
    async def open_player_scene(
        self,
        location_uuid: str,
        player_uuid: str,
        player_name: str,
        player_labels: list[str],
    ) -> dict[str, Any]:
        """Open a scene with the PLAYER as gm_self (single-self, empty roster).

        Unlike ``open_room`` (synthetic GM + NPC roster), this makes the player
        the scene's director so it can take its own turns and call its innate
        tools (e.g. ``mm_look``). The scene manifest is built from gm_self's
        capabilities; ``mm_look`` is a free spec, so it is retained regardless.
        """
        gm_self = {
            "id": player_uuid,
            "embodiment_agent_id": self._embodiment_id(player_uuid),
            "names": [player_name],
            "seat": "LLM",
            "capabilities": sorted(get_allowed_tools(player_labels)),
        }
        body: dict[str, Any] = {
            "bonfire_id": self._bonfire_id,
            "scene_actor_id": player_uuid,
            "gm_self": gm_self,
            "roster": [],
        }
        url = f"/v1/scenes/{location_uuid}/open"
        resp = await self._client.post(url, json=body, headers=self._request_headers())
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        logger.info("open_player_scene %s player=%s", location_uuid, player_uuid)
        return data

    async def drive_self_turn(
        self, location_uuid: str, self_id: str, message: str
    ) -> dict[str, Any]:
        """POST /turn with a caller-supplied ``self_id`` (the acting self),
        bypassing the NPC who-acts resolver. Used to make the PLAYER act on its
        own turn. The NPC ``drive_turn`` path is unchanged."""
        body: dict[str, Any] = {"self_id": self_id, "message": message}
        url = f"/v1/scenes/{location_uuid}/turn"
        resp = await self._client.post(url, json=body, headers=self._request_headers())
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        logger.info(
            "drive_self_turn %s self_id=%s → %.60s",
            location_uuid, self_id, data.get("response_text", ""),
        )
        return {**data, "self_id": self_id}
```

- [ ] **Step 2 — write the failing tests** (`gateway/tests/test_room_driver.py`, append; mirror the file's existing `/open` + `/turn` ASGITransport stub style):
```python
@pytest.mark.asyncio
async def test_open_player_scene_makes_player_the_gm_self():
    captured = {}

    async def _open(request):
        captured["body"] = await request.json()
        return JSONResponse({"source_episode_id": "ep-1"})

    stub = Starlette(routes=[Route("/v1/scenes/{loc}/open", _open, methods=["POST"])])
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=stub), base_url="http://ar")
    driver = RoomDriver(repo=object(), agent_runtime_client=client, bonfire_id="bf-1")

    data = await driver.open_player_scene("loc-1", "player-1", "Tester", ["Character"])
    assert data["source_episode_id"] == "ep-1"
    body = captured["body"]
    assert body["gm_self"]["id"] == "player-1"
    assert body["gm_self"]["seat"] == "LLM"
    assert body["gm_self"]["names"] == ["Tester"]
    assert "mm_look" in body["gm_self"]["capabilities"]  # innate → granted
    assert body["roster"] == [] and body["scene_actor_id"] == "player-1"


@pytest.mark.asyncio
async def test_drive_self_turn_uses_forced_self_id():
    captured = {}

    async def _turn(request):
        captured["body"] = await request.json()
        return JSONResponse({"response_text": "You see a dim shape.", "should_respond": True, "fired_cxns": ["mm.look.v1"]})

    stub = Starlette(routes=[Route("/v1/scenes/{loc}/turn", _turn, methods=["POST"])])
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=stub), base_url="http://ar")
    driver = RoomDriver(repo=object(), agent_runtime_client=client, bonfire_id="bf-1")

    turn = await driver.drive_self_turn("loc-1", "player-1", "look around")
    assert captured["body"] == {"self_id": "player-1", "message": "look around"}  # forced, not NPC-resolved
    assert turn["self_id"] == "player-1"
    assert turn["fired_cxns"] == ["mm.look.v1"]
    assert turn["response_text"] == "You see a dim shape."
```
  *(If `Starlette`/`Route`/`JSONResponse`/`httpx` aren't already imported at the top of `test_room_driver.py`, add them — match how the file's existing `/turn` stub imports them.)*

- [ ] **Step 3 — run, verify pass:**
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_room_driver.py -q
```
Expected: green (existing + 2 new). The existing `drive_turn`/`open_room` tests are unaffected (the new methods are additive).

- [ ] **Step 4 — ruff-format + commit:**
```bash
python3.12 -m ruff format gateway/src/gateway/room_driver.py gateway/tests/test_room_driver.py
git add gateway/src/gateway/room_driver.py gateway/tests/test_room_driver.py
git commit -m "feat(gateway): RoomDriver.open_player_scene + drive_self_turn (player-as-self)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TmmDb5v2f2mae5pmRWtqBZ"
```

---

# Task 2 — `/opening/start`: seed the player into `app.state.cxn_repo` + open the player scene

**Files:**
- Modify: `gateway/src/gateway/routes/opening.py`
- Test: `gateway/tests/test_opening_player_scene.py` (new)

**Interfaces:**
- Consumes: `RoomDriver.open_player_scene` (Task 1). Produces: after `/opening/start`, the player exists in `app.state.cxn_repo` at `LOC_DEEP_ROADS` and a player-`gm_self` scene is opened (both best-effort).

- [ ] **Step 1a — add `import inspect`** to the module imports (top of `opening.py`, near `import asyncio`).

- [ ] **Step 1b — add `request: Request` to the signature** (`Request` is already imported at `:49`):
```python
async def start_opening(req: StartOpeningRequest, request: Request) -> StartOpeningResponse:
```

- [ ] **Step 1c — add the two module-level helpers** (place them above `start_opening`):
```python
async def _seed_player_into_cxn_repo(cxn_repo, player_uuid: str, player_name: str) -> None:
    """B1: seed the player into app.state.cxn_repo at the Deep Roads so the
    gateway mm_look can resolve the player's location. seed_entity may be sync
    (in-memory) or async (EventSourced) — handle both."""
    from memento.opening.deep_roads import LOC_DEEP_ROADS

    res = cxn_repo.seed_entity(
        {
            "uuid": player_uuid,
            "name": player_name,
            "kind": "character",
            "labels": ["Character"],
            "location_uuid": LOC_DEEP_ROADS,
            "attrs": {},
            "is_dead": False,
        }
    )
    if inspect.isawaitable(res):
        await res


async def _open_player_scene(state, player_uuid: str, player_name: str) -> None:
    """B2: open a scene with the player as gm_self so it can take its own turns."""
    from memento.opening.deep_roads import LOC_DEEP_ROADS

    from gateway.room_driver import RoomDriver, build_agent_runtime_client

    ar_client = getattr(state, "agent_runtime_client", None) or build_agent_runtime_client()
    driver = RoomDriver(
        repo=state.cxn_repo,
        agent_runtime_client=ar_client,
        bonfire_id=getattr(state, "bonfire_id", BONFIRE_ID),
    )
    await driver.open_player_scene(LOC_DEEP_ROADS, player_uuid, player_name, ["Character"])
```

- [ ] **Step 1d — insert the best-effort B1+B2 block** in `start_opening`, immediately AFTER the `opening_registry[player_uuid] = turn_router` / `opening_repos[player_uuid] = repo` block (`:249-250`) and BEFORE the `# -- 8. Return room manifest` step:
```python
    # -- 7b. Player-as-persona (Component B): make the player a self-agent so it
    # can take its own "look around" turn. Best-effort — never break /opening/start.
    state = request.app.state
    cxn_repo = getattr(state, "cxn_repo", None)
    if cxn_repo is not None:
        try:
            await _seed_player_into_cxn_repo(cxn_repo, player_uuid, req.player_name)  # B1
            await _open_player_scene(state, player_uuid, req.player_name)             # B2
        except Exception:
            logger.warning("opening player-as-persona setup failed (non-fatal)", exc_info=True)
```

- [ ] **Step 2 — failing tests** (`gateway/tests/test_opening_player_scene.py`, new). Set `app.state.cxn_repo` + a stub agent-runtime client, drive `/opening/start`, assert the player landed in the repo + `/open` was called with the player as `gm_self`:
```python
import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from memento.opening.deep_roads import LOC_DEEP_ROADS
from memento.state.in_memory import InMemoryStateRepository


def _ar_stub(captured):
    async def _open(request):
        captured["open_body"] = await request.json()
        return JSONResponse({"source_episode_id": "ep-1"})

    app = Starlette(routes=[Route("/v1/scenes/{loc}/open", _open, methods=["POST"])])
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://ar")


@pytest.fixture()
def _patch_opening_hooks(monkeypatch):
    # reuse the same fakes test_opening_routes.py uses (KgProjectionFake, NoopChainMirror,
    # NullMemoryClient, FakeComprehensionClient with a 'look around' frame). Import or
    # replicate that autouse fixture's monkeypatches here.
    ...


@pytest.mark.asyncio
async def test_start_seeds_player_into_cxn_repo_and_opens_player_scene(_patch_opening_hooks):
    from gateway.app import app

    captured = {}
    cxn_repo = InMemoryStateRepository()
    app.state.cxn_repo = cxn_repo
    app.state.agent_runtime_client = _ar_stub(captured)
    app.state.bonfire_id = "bf-1"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/opening/start", json={
            "player_name": "Tester",
            "wallet_address": "0x" + "a" * 40,
            "archetype": "",
        })
    assert resp.status_code == 200, resp.text
    player_id = resp.json()["player_id"]

    # B1: player is in app.state.cxn_repo at the Deep Roads
    ent = await cxn_repo.get_entity(player_id)
    assert ent is not None and ent["location_uuid"] == LOC_DEEP_ROADS
    assert ent["kind"] == "character" and "Character" in ent["labels"]

    # B2: a player-gm_self scene was opened
    body = captured["open_body"]
    assert body["gm_self"]["id"] == player_id and body["gm_self"]["seat"] == "LLM"
    assert "mm_look" in body["gm_self"]["capabilities"] and body["roster"] == []


@pytest.mark.asyncio
async def test_start_still_succeeds_without_cxn_repo(_patch_opening_hooks):
    from gateway.app import app

    if hasattr(app.state, "cxn_repo"):
        delattr(app.state, "cxn_repo")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/opening/start", json={
            "player_name": "Tester", "wallet_address": "0x" + "b" * 40, "archetype": "",
        })
    assert resp.status_code == 200  # B1/B2 no-op gracefully when cxn_repo absent
```
  *(The `_patch_opening_hooks` fixture must apply the SAME monkeypatches as `test_opening_routes.py`'s autouse hook — read that file and copy its body (it patches `gateway.routes.opening.build_comprehension/build_memory/build_mirror/build_projection`). Without it, `/opening/start` hits the real KG SDK. The cleanest path is to import and reuse that fixture if it's importable, else replicate it.)*

- [ ] **Step 3 — run, verify pass:**
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_opening_player_scene.py gateway/tests/test_opening_routes.py -q
```
Expected: green (the new tests + the existing `/opening/start` tests, which still pass because B1/B2 no-op when `app.state.cxn_repo` is absent in those fixtures).

- [ ] **Step 4 — ruff-format + commit:**
```bash
python3.12 -m ruff format gateway/src/gateway/routes/opening.py gateway/tests/test_opening_player_scene.py
git add gateway/src/gateway/routes/opening.py gateway/tests/test_opening_player_scene.py
git commit -m "feat(gateway): /opening/start seeds the player into cxn_repo + opens a player-self scene

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TmmDb5v2f2mae5pmRWtqBZ"
```

---

# Task 3 — `/opening/look`: drive the player's "look around" turn

**Files:**
- Modify: `gateway/src/gateway/routes/opening.py`
- Test: `gateway/tests/test_opening_player_scene.py` (append)

**Interfaces:**
- Consumes: `RoomDriver.drive_self_turn` (Task 1); `CXN_DISPLAY_NAMES` (Plan 3). Produces: `POST /api/opening/look {player_id}` → drives the player turn, broadcasts `cxn_fired` + player-attributed narration, returns `{ok, fired_cxns, response_text}`.

- [ ] **Step 1 — add `LookRequest` + the route** to `opening.py` (after `ActRequest` and the `/opening/act` route respectively):
```python
class LookRequest(BaseModel):
    player_id: str = Field(..., min_length=1, max_length=64)
```
```python
@router.post("/opening/look")
async def look_opening(req: LookRequest, request: Request) -> dict:
    """Drive the player-self's auto-issued "look around" turn (post-WS-connect).

    The player (a self-agent registered at /opening/start) comprehends
    "look around" → LOOK fires → it calls mm_look (drawing the room) → narrates.
    Broadcasts the cxn_fired catch beat + the narration over WS. Best-effort:
    never 500s; a turn failure returns {ok: false}.
    """
    from memento.opening.deep_roads import LOC_DEEP_ROADS

    from gateway.room_driver import RoomDriver, build_agent_runtime_client
    from gateway.scene_coordinator import CXN_DISPLAY_NAMES

    state = request.app.state
    location_name = "the deep roads"
    ar_client = getattr(state, "agent_runtime_client", None) or build_agent_runtime_client()
    driver = RoomDriver(
        repo=getattr(state, "cxn_repo", None),
        agent_runtime_client=ar_client,
        bonfire_id=getattr(state, "bonfire_id", BONFIRE_ID),
    )
    try:
        turn = await driver.drive_self_turn(LOC_DEEP_ROADS, req.player_id, "look around")
    except Exception:
        logger.warning("opening look turn failed (non-fatal)", exc_info=True)
        return {"ok": False, "fired_cxns": [], "response_text": ""}

    fired = turn.get("fired_cxns") or []
    try:
        from gateway.app import ws_hub

        if ws_hub is not None:
            await ws_hub.set_location(req.player_id, location_name)
            for construct_id in fired:
                display = CXN_DISPLAY_NAMES.get(construct_id, construct_id)
                await ws_hub.broadcast_to_location(
                    location_name,
                    {
                        "type": "cxn_fired",
                        "cxn": display,
                        "construct_id": construct_id,
                        "actor_id": req.player_id,
                        "location": location_name,
                    },
                )
            response_text = turn.get("response_text", "")
            if turn.get("should_respond", True) and response_text:
                player_name = await _player_name(state, req.player_id)
                await ws_hub.broadcast_to_location(
                    location_name,
                    {
                        "type": "tool_event",
                        "tool": "mm_npc_response",
                        "npc": player_name,  # non-empty → renders; attributed to the player
                        "summary": response_text,
                        "data": {},
                        "location": location_name,
                        "channel": "narrative",
                    },
                )
    except Exception:
        logger.warning("opening look broadcast failed (non-fatal)", exc_info=True)

    return {"ok": True, "fired_cxns": fired, "response_text": turn.get("response_text", "")}


async def _player_name(state, player_id: str) -> str:
    cxn_repo = getattr(state, "cxn_repo", None)
    if cxn_repo is None:
        return ""
    try:
        ent = await cxn_repo.get_entity(player_id)
        return ent.get("name", "") if ent else ""
    except Exception:
        return ""
```
  *(The narration reuses the `mm_npc_response` shape so the existing opening client adapter renders it; `npc` is the player's name (non-empty so it renders) — proper player-narration styling is a Plan-6 client refinement.)*

- [ ] **Step 2 — failing tests** (append to `gateway/tests/test_opening_player_scene.py`). Stub the agent-runtime `/turn`, set a fake `ws_hub`, assert `cxn_fired` + narration broadcasts:
```python
@pytest.mark.asyncio
async def test_look_drives_player_turn_and_broadcasts(monkeypatch):
    from gateway.app import app
    import gateway.app as gw_app

    # stub agent-runtime /turn
    async def _turn(request):
        return JSONResponse({"response_text": "A dim shape stirs.", "should_respond": True, "fired_cxns": ["mm.look.v1"]})

    ar = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=Starlette(routes=[Route("/v1/scenes/{loc}/turn", _turn, methods=["POST"])])),
        base_url="http://ar",
    )
    repo = InMemoryStateRepository()
    repo.seed_entity({"uuid": "p1", "name": "Tester", "kind": "character", "labels": ["Character"], "location_uuid": LOC_DEEP_ROADS, "attrs": {}, "is_dead": False})
    app.state.cxn_repo = repo
    app.state.agent_runtime_client = ar
    app.state.bonfire_id = "bf-1"

    class _Hub:
        def __init__(self): self.b = []
        async def set_location(self, pid, name): pass
        async def broadcast_to_location(self, loc, msg): self.b.append((loc, msg))
    hub = _Hub()
    monkeypatch.setattr(gw_app, "ws_hub", hub)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/opening/look", json={"player_id": "p1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True and data["fired_cxns"] == ["mm.look.v1"]

    kinds = [m.get("type") for _, m in hub.b]
    cxn = next(m for _, m in hub.b if m["type"] == "cxn_fired")
    assert cxn["cxn"] == "LOOK" and cxn["construct_id"] == "mm.look.v1" and cxn["actor_id"] == "p1"
    narr = next(m for _, m in hub.b if m.get("tool") == "mm_npc_response")
    assert narr["npc"] == "Tester" and narr["summary"] == "A dim shape stirs."
    assert kinds.index("cxn_fired") < kinds.index("tool_event")  # catch beat before narration


@pytest.mark.asyncio
async def test_look_turn_failure_returns_benign(monkeypatch):
    from gateway.app import app
    import gateway.app as gw_app

    async def _boom(request):
        return JSONResponse({"error": "down"}, status_code=503)
    ar = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=Starlette(routes=[Route("/v1/scenes/{loc}/turn", _boom, methods=["POST"])])),
        base_url="http://ar",
    )
    app.state.cxn_repo = InMemoryStateRepository()
    app.state.agent_runtime_client = ar
    app.state.bonfire_id = "bf-1"
    monkeypatch.setattr(gw_app, "ws_hub", None)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/opening/look", json={"player_id": "p1"})
    assert resp.status_code == 200  # never 500
    assert resp.json() == {"ok": False, "fired_cxns": [], "response_text": ""}
```

- [ ] **Step 3 — run, verify pass:**
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_opening_player_scene.py -q
```
Expected: green (Task 2 + Task 3 tests).

- [ ] **Step 4 — regression smoke:**
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_opening_routes.py gateway/tests/test_room_driver.py gateway/tests/test_scene_coordinator.py -q
```
Expected: green (the new routes/methods are additive).

- [ ] **Step 5 — ruff-format + commit:**
```bash
python3.12 -m ruff format gateway/src/gateway/routes/opening.py gateway/tests/test_opening_player_scene.py
git add gateway/src/gateway/routes/opening.py gateway/tests/test_opening_player_scene.py
git commit -m "feat(gateway): /opening/look drives the player-self look turn + broadcasts the catch beat

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TmmDb5v2f2mae5pmRWtqBZ"
```

---

## Verification (end-to-end)

1. **RoomDriver (Task 1):** `open_player_scene` POSTs `/open` with the player as `gm_self` (seat=LLM, capabilities ∋ `mm_look`, empty roster); `drive_self_turn` POSTs `/turn` with a forced `self_id`. The NPC `drive_turn` path is unchanged. 2 tests.
2. **`/opening/start` (Task 2):** seeds the player into `app.state.cxn_repo` at the Deep Roads (so `mm_look` resolves it) and opens the player scene — both best-effort, and `/opening/start` still succeeds when `cxn_repo` is absent. 2 tests + existing-start regression.
3. **`/opening/look` (Task 3):** drives the player's "look around" turn and broadcasts `cxn_fired` (catch beat) + a player-attributed narration, before/independent of failures; never 500s. 2 tests + regression.
4. **End-to-end (manual, bring-up):** with the KG stack + `OPENING_AUTHOR_LOOK_GRAMMAR` (Plan 4) + agent-runtime up: `POST /api/opening/start` → connect WS → `POST /api/opening/look` → "◇ caught: LOOK" + `room_draw` + narration; re-`look` accretes (reveal → deepen).

## What this plan deliberately does NOT do (Plan 6 / later)

- **The client one-shot look trigger** (B-client) — POSTing `/opening/look` after the opening WS connects — folds into **Plan 6** with the cinematic intro (epigraph fade + name box) and the client `room_draw` glyph rendering + proper player-narration styling.
- The deterministic-draw fallback (if the ReAct agent doesn't reliably call `mm_look`) — deferred per the spec's open question (wait-and-see in the live demo).
- Reconciling the legacy `/opening/act` TurnRouter path with the player-self path (they coexist additively); multi-room; cross-session reveal-state persistence.
