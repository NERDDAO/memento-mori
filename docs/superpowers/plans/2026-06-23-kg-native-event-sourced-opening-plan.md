# KG-Native, Event-Sourced Immersive Opening — Implementation Plan (Sub-Project 1)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) tracking. Fresh implementer per task + per-task review + final whole-branch review.

## Context

The deterministic opening engine (`engine/src/memento/opening/*` + cxn `TurnRouter`/`SceneDirector`) is built and tested only in-memory (`engine/tests/integration/test_opening_arc.py`), and is **not reachable from a client**: `gateway/.../cxn_tools.py register_mm_act` constructs the `TurnRouter` with `director=None, describe_client=None, repo=None`, so LOOK narration, MOVE exit-resolution, win, and lazy materialization are inert; and there is no "start opening" entry point. This sub-project makes the arc reachable **and** persistent via an **event-sourced** store: an append-only **Tx Log** of cxn-stamped deltas is the truth, the **graphiti KG** is the rebuildable read-projection, a game-local **activation log** joins state changes to the constructions that caused them (`activation_id`), and the existing `ChainMirror` lazy-write keeps notarizing the permadeath subset onchain. On win, the player is already a persisted KG session in `NEXT_ROOM` and the live HUD takes over.

Full design: `memento-mori/docs/superpowers/specs/2026-06-23-kg-native-event-sourced-opening-design.md` (committed 99e5e5d).

## Architecture (one paragraph)

The deterministic engine runs **unchanged in behavior** against a new `EventSourcedStateRepository` (instead of `InMemoryStateRepository`). Each write emits cxn-stamped deltas → appends one tool-use tx `{tx_id, activation_id, actor_id, tool, deltas[]}` to the **Tx Log** (Mongo, truth) → updates the **KG projection** (graphiti via `bonfires_client.kg`, reads) → fires `ChainMirror` for the permadeath subset. Reads hit the KG projection. `TurnRouter.handle` mints one `activation_id` per utterance, writes an activation record to the **activation log** (Mongo), and sets it as per-turn context on the repo so every write that turn (executor deltas **and** `SceneDirector` surface-beat writes) is stamped. `rebuild_projection(actor)` folds the Tx Log to regenerate the projection — the parity proof. New sync endpoints `POST /api/opening/{start,act}` build a director-backed router per player (in `opening_registry`) and return `TurnOutcome` directly.

## Tech Stack

Python 3.x (memento-mori engine + gateway, FastAPI, Beanie/Mongo, httpx); pytest (`engine/tests`, `gateway/tests`); the deterministic cxn engine + opening modules; graphiti KG via the `bonfires` SDK (`get_client().kg`).

## Global Constraints

- **Branch:** work on `opening/engine-core` (current). NEVER `git add -A` — stage only touched files.
- **Commit trailer (every commit):** `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **UUIDs, never names** (project CLAUDE.md). In the real flow ALL uuids are KG-assigned (player from `create_player`; rooms/facts/items from `kg.create_entity`); the `SceneDirector` key→uuid registry + `materialize`'s return value thread them. The fixed deep-roads UUIDs (`deep_roads.py`) are **test fixtures only** — do not assume them as literal KG ids in the live path.
- **KG SDK is SYNC + UUID-server-assigned + no hard delete.** Every `bonfires_client.kg.*` call is wrapped in `asyncio.to_thread(...)` (precedent: `routes/session.py:44`). Use `kg.get_entity_or_none(uuid)` for `EntityDoc | None` semantics (`kg.get_entity` raises on miss). `update_entity` requires `name,labels,summary` resent. Deletions/unlinks use `update_edge(expired_at=...)` (no hard delete).
- **Behavioral parity:** the `EventSourcedStateRepository` must match `InMemoryStateRepository` semantics exactly (reads return deepcopies; writes return post-write snapshot; `set_attr` writes `is_dead` top-level and all else into `attrs`; `move_entity` maintains the location's `attrs["item_ids"]`; `get_actor_snapshot` keys: `location`=`location_uuid`, `health`=`attrs["hp"]`, `max_health`=`attrs["max_hp"]`, `inventory`=`attrs["inventory"]`, etc.). Reference: `engine/src/memento/state/in_memory.py`.
- **ChainMirror unchanged**, fire-and-forget, never raises, never in rollback (`engine/src/memento/state/chain_mirror.py`).
- **Two spec open-questions resolved:** integration/unit tests use a **KG fake** (in-memory object honoring the `KgProjection` read/write contract) + the **live script** hits the real KG (mirrors GM-rooms deterministic-proof vs live-smoke split). `/opening/start` mints a **fresh player** (returning characters skip the opening).

## File Structure

- Create `engine/src/memento/state/tx_log.py` — `TxLog`, `ActivationLog` (Mongo append-only) + a Mongo-less in-memory variant for tests.
- Create `engine/src/memento/state/kg_projection.py` — `KgProjection` (EntityDoc↔KG adapter over `get_client().kg`, sync→`to_thread`) + `KgProjectionFake` (test double).
- Create `engine/src/memento/state/event_sourced.py` — `EventSourcedStateRepository` (composes TxLog+KgProjection+ChainMirror; 14 Protocol methods + `seed_entity`/`seed_item` + `set_activation`/`rebuild_projection`).
- Modify `engine/src/memento/cxn/turn_router.py` — mint `activation_id`, write activation record, `repo.set_activation(id)` per turn.
- Modify `engine/src/memento/cxn/executor.py` — stamp `activation_id` onto emitted deltas (read from repo context; minimal — the repo already holds the activation).
- Modify `engine/src/memento/opening/loader.py` — generalize `load_seed_room`'s repo type (accept anything with `seed_entity`/`seed_item`).
- Create `gateway/src/gateway/routes/opening.py` — `/api/opening/{start,act}` + module-level `opening_registry`; modify `gateway/src/gateway/app.py` (mount before the StaticFiles catch-all).
- Create `engine/tests/integration/test_opening_arc_event_sourced.py`, `scripts/opening_smoke.py`.

---

## Task 1 — Tx Log + Activation Log stores

**Files:** create `engine/src/memento/state/tx_log.py`; test `engine/tests/state/test_tx_log.py`.

- `TxEntry` dataclass/TypedDict `{tx_id, activation_id, actor_id, tool, deltas: list[dict], ts}`; `ActivationRecord` `{activation_id, message_id, actor_id, cxn_id, tool, roles, ts}`.
- `TxLog` + `ActivationLog`: `append(entry)`, `for_actor(actor_id) -> list` (ordered), `join(activation_id)`. Provide an **in-memory** implementation now (a list-backed class) behind a small Protocol so the repo and tests don't depend on Mongo; a Beanie/Mongo-backed impl can swap in later (note in file, do not build Mongo yet unless trivial).
- TDD: append two txs for an actor → `for_actor` returns them in order; `ActivationLog.join(id)` returns the matching record; deltas survive round-trip.

## Task 2 — KgProjection adapter (+ fake)

**Files:** create `engine/src/memento/state/kg_projection.py`; test `engine/tests/state/test_kg_projection.py`.

- `KgProjection` wraps `get_client().kg`, every call via `asyncio.to_thread`. Implements the read/write surface the repo needs, mapping `EntityDoc`/`ItemDoc` ↔ KG entity + edges using the production vocabulary (`memento/session.py`): `location_uuid`↔`LOCATED_IN`, `inventory`↔`CARRIES`, `is_dead`↔`HAS_STATUS "DEAD"`, exits/attrs on the entity. Use `get_entity_or_none`; `update_entity` resends name+labels+summary; unlink via `update_edge(expired_at)`.
- `KgProjectionFake` — in-memory dict honoring the same contract (the test/integration double), so tests don't need a live KG.
- TDD (against the fake AND, where cheap, contract-shape assertions): write an entity then `get_entity` returns the same `EntityDoc`; `move_entity` re-points `LOCATED_IN`; `materialize` returns the (assigned) uuid and the item is `CARRIES`/located correctly; `is_dead` set ↔ `HAS_STATUS`.

## Task 3 — EventSourcedStateRepository

**Files:** create `engine/src/memento/state/event_sourced.py`; test `engine/tests/state/test_event_sourced_repository.py`.

- Compose `TxLog`, `ActivationLog` (Task 1), `KgProjection` (Task 2), `ChainMirror`. Implement all **14** Protocol methods + sync `seed_entity`/`seed_item` (genesis txs, `activation_id="genesis"`).
- `set_activation(activation_id)` sets per-turn context (cleared per turn by the router). Each write: compute deltas → `TxLog.append({activation_id=current, tool, deltas})` → apply to `KgProjection` → fire `ChainMirror` for the subset (death `set_attr(is_dead)`→`on_character_death`; ownership `transfer_item`→`on_item_transferred`). Reads from `KgProjection` only.
- `rebuild_projection(actor_id)`: fresh projection ← fold `TxLog.for_actor`.
- TDD: **behavioral parity vs `InMemoryStateRepository`** on `move_entity`/`materialize`/`set_attr`/`get_actor_snapshot`/`transfer_item`/`link`/`unlink` (same returns, using the fake projection); each write appends a tx carrying the current `activation_id`; `rebuild_projection` reproduces the projection state after a sequence of writes.

## Task 4 — activation_id threading in TurnRouter + executor

**Files:** modify `engine/src/memento/cxn/turn_router.py`, `engine/src/memento/cxn/executor.py`; test `engine/tests/cxn/test_activation_stamping.py`.

- `TurnRouter.handle`: at top, mint `activation_id` (uuid hex); after comprehension, write `ActivationRecord{activation_id, message_id=<utterance id>, actor_id, cxn_id=matched cxn, tool=mcp_tool_name, roles}` to the `ActivationLog`; call `repo.set_activation(activation_id)` before executing so executor deltas AND the read-only/`director.apply_surface_beats` writes are stamped; clear after.
- `executor.py`: ensure emitted deltas carry the activation (simplest: the repo stamps from its current-activation context at `TxLog.append`, so the executor needs no signature change — verify `_apply_transactional` writes go through the repo so the repo-context stamping covers them; if any delta is built without a repo write, stamp it explicitly).
- TDD (with the EventSourced repo + fake projection + a fake comprehension like `test_opening_arc.py`'s): one `handle("go on", actor)` produces an `ActivationRecord` and a Tx Log tx sharing the `activation_id`; a `handle("look around", actor)` that triggers the "die" surface beat stamps that `is_dead` write with the same turn's `activation_id` (covers the director-beat path).

## Task 5 — load_seed_room generalization

**Files:** modify `engine/src/memento/opening/loader.py`; test `engine/tests/opening/test_loader_event_sourced.py`.

- Generalize the `repo` param type from `InMemoryStateRepository` to a structural type exposing `seed_entity`/`seed_item` (or a small Protocol), so `load_seed_room(seed, repo, actor_id)` works with the EventSourced repo. Keep behavior identical (seeds room + canon facts, leaves latent facts latent, populates the `SceneDirector` registry with the seeded uuids).
- TDD: seeding `deep_roads_seed()` into an `EventSourcedStateRepository` creates the room + dying adventurer (genesis txs present), the iron blade stays latent (not in projection), and the director registry maps the canon fact key → its uuid.

## Task 6 — Opening routes + registry + gateway wiring

**Files:** create `gateway/src/gateway/routes/opening.py`; modify `gateway/src/gateway/app.py`; test `gateway/tests/routes/test_opening_routes.py`.

- `router = APIRouter()`; `opening_registry: dict[str, TurnRouter]` (module-level, mirrors `gm_room_registry`).
- `POST /api/opening/start` `{player_name, wallet_address, archetype}`: create fresh player in KG; build `EventSourcedStateRepository`; `await load_seed_room(deep_roads_seed(), repo, player_uuid)` → director; build the **director-backed** `TurnRouter(comprehension, ConstructiconRegistry(), EntityResolver(repo, director), EffectExecutor(repo, memory, mirror), bonfire_id, director=director, describe_client=TemplateDescribeClient(), repo=repo)` (exactly the `test_opening_arc.py:106-115` wiring); register under `player_id`; return initial state.
- `POST /api/opening/act` `{player_id, text}`: lookup router (404 if absent); `outcome = await router.handle(text, player_uuid)`; on `outcome.get("won")` drop the registry entry; return the `TurnOutcome`.
- Reuse player JWT/auth as `session/create`. Mount `app.include_router(opening.router, prefix="/api")` before the StaticFiles catch-all (`app.py`).
- TDD (FastAPI `TestClient`/ASGITransport, with the KG fake + a fake comprehension injected via `app.state`/DI): `start` returns a player_id + seeded room; `act` with a comprehension that yields LOOK returns `{status:"narrated", narration:...}`; off-script text returns `{status:"clarify"}`; a winning MOVE returns `{won:true}` and clears the registry entry.

## Task 7 — Integration parity proof

**Files:** create `engine/tests/integration/test_opening_arc_event_sourced.py`.

- Mirror `test_opening_arc.py` but with `EventSourcedStateRepository` (+ `KgProjectionFake` + in-memory Tx/activation logs). Drive `start → "look around" → "take the iron blade" → "go on"`. Assert: projection state (adventurer `HAS_STATUS DEAD`; blade materialized + `CARRIES`-linked; player `LOCATED_IN NEXT_ROOM`; `won`); Tx Log holds cxn-stamped txs (non-empty `activation_id`); each tx joins to an `ActivationRecord` whose `message_id` is the originating utterance; **`rebuild_projection(player)` reproduces the projection byte-for-byte**.

## Task 8 — Live smoke script

**Files:** create `scripts/opening_smoke.py`.

- Drive the real `/api/opening/{start,act}` against a running gateway (env `GATEWAY_URL`), asserting the same arc outcomes; **skip cleanly** when the gateway is unreachable (mirror `scripts/gm_room_smoke.py`). All network I/O behind `if __name__ == "__main__":`.

---

## Verification

1. **Unit/integration (no live infra):** from `engine/` run `pytest tests/state tests/cxn tests/opening tests/integration/test_opening_arc_event_sourced.py -q` → green; the parity test's `rebuild_projection` assertion is the load-bearing event-sourcing proof. From `gateway/` run `pytest tests/routes/test_opening_routes.py -q`.
2. **Behavioral parity:** Task 3's parity test proves `EventSourcedStateRepository` matches `InMemoryStateRepository` on the core methods.
3. **Live end-to-end (manual):** boot the gateway (with a real KG/graph-memory reachable); `GATEWAY_URL=http://localhost:8090 python scripts/opening_smoke.py` → drives `start → look → take → go on`, asserts the persisted KG state (dead adventurer, carried blade, location `NEXT_ROOM`, won) and that the player continues as a normal session afterward.
4. **Regression:** the original `engine/tests/integration/test_opening_arc.py` (in-memory) stays green — the engine behavior is unchanged.

## Out of scope (this sub-project)

Client immersive-opening rendering (sub-project 2); making post-win/general gameplay event-sourced; full-onchain coverage (a MUD MOVE System); unifying the game-local activation log with the memory kernel's perdurant cxn graph; Tx Log snapshotting/replay-cost bounds.
