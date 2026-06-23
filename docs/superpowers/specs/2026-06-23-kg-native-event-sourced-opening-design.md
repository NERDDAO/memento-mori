# KG-Native, Event-Sourced Immersive Opening — Design (Sub-Project 1)

**Date:** 2026-06-23
**Status:** Design — awaiting review
**Branch:** `opening/engine-core`

## Goal

Make the deterministic immersive-opening engine (already built: `engine/src/memento/opening/*` + the cxn `TurnRouter`) reachable and **persistent**, so a player can drive the opening arc ("look around" → witnessed death, "take the iron blade" → materialize + carry, "go on" → cross the exit → win) over real endpoints, with all state changes flowing through an **event-sourced** store whose authoritative record is an append-only **Tx Log** of cxn-stamped deltas. On win, the player is already a fully-persisted session and continues in the live world — the opening *becomes* the game.

This is **sub-project 1** of two. Sub-project 2 (the client immersive-opening rendering) consumes the endpoints defined here and is specified separately.

## Background — two systems and the gap

The repo has two parallel systems that are not wired together:

- **(A) The deterministic opening engine** — `engine/src/memento/opening/*` (`SceneDirector`, seed loader, deep-roads seed, describe) + `engine/src/memento/cxn/*` (`TurnRouter`, `EntityResolver`, `EffectExecutor`, construction defs). Authored, in-memory, no LLM/RNG. The full arc is exercised end-to-end only in `engine/tests/integration/test_opening_arc.py`, wired by hand.
- **(B) The live gateway session flow** — `gateway/src/gateway/routes/{session,action,state}.py` + `memento/session.py` (`SessionManager`, KG-backed) + the WS hub + Matrix round-manager. This is what a deployed client talks to today; its only "opening" is a single LLM-generated `opening_narrative` string.

**The wiring gap:** `gateway/src/gateway/cxn_tools.py` `register_mm_act` builds the `TurnRouter` **without** `director`/`describe_client`/`repo`, so through the live MCP surface, LOOK's narration, MOVE exit-resolution, the win predicate, and lazy materialization are all inert — they only activate when a `SceneDirector` and `repo` are injected (today, only in the test). There is also no "start opening" entry point that instantiates a `SceneDirector`, and no persistence: the arc runs on `InMemoryStateRepository`.

## Design decisions (brainstorm outcomes)

| Decision | Choice |
|---|---|
| Integration target | Wire **and** render the deterministic arc (this spec = the wire half). |
| Player input | Free-text parser (utterances routed through the cxn `TurnRouter`); off-script input renders the engine's existing `clarify` outcome as an in-fiction nudge. |
| Persistence model | The opening **becomes the game** — its world persists; on win the player continues in the same persistent world, no migration. |
| State engine | **KG-native** — the deterministic engine runs against a persistent-backed `StateRepository`, not `InMemoryStateRepository`. |
| Source of truth | **Full event-sourcing** — the Tx Log (cxn-stamped deltas) is authoritative; current state is a rebuildable projection. |
| Tx Log entry granularity | One **tool-use transaction** = many component deltas, all sharing one `activation_id` (matches onchain tx semantics). |
| Onchain coverage | **Off-chain full Tx Log = truth**; the existing lazy write (`ChainMirror` → `chain.py`, MUD World on Redstone) keeps notarizing the **permadeath subset** (death, item ownership). MOVE/materialize are logged off-chain now, promotable onchain later. |
| Substrates | Off-chain Tx Log + activation log = **append-only Mongo collections**; KG projection = **Neo4j** via `bonfires_client.kg`; chain = unchanged `ChainMirror`. |
| Cxn-activation log | **Game-local** (`memento/cxn`), joined to the Tx Log by `activation_id`. Unifying with the memory kernel's perdurant cxn graph (FCG/entrenchment) is a later project. |

## Architecture

```
utterance ──comprehend──▶ Construction Activation ──┐
  (message log)            (memento/cxn TurnRouter)  │ activation_id = join key
                                                      ▼
                        EffectExecutor emits cxn-stamped deltas
                                  │
           ┌───────────────────────┼────────────────────────────┐
           ▼                       ▼                             ▼
   Off-chain Tx Log          KG projection               Chain (lazy write, BUILT)
   = FULL TRUTH (Mongo)      = fast reads (Neo4j)         = notarized subset
   {tx, activation_id,       engine reads here;           death + item ownership
    tool, deltas[]}          rebuildable from log         (ChainMirror, unchanged)
           │
           └── activation log (Mongo) {activation_id, message_id, cxn_id, roles, tool}
               join: Tx Log.activation_id ↔ activation log ↔ message  ⇒ provenance
```

The deterministic engine (`TurnRouter`/`SceneDirector`/`EntityResolver`/`EffectExecutor`) runs **unchanged in behavior**; only the `StateRepository` it is constructed with changes, plus an `activation_id` threaded through the executor.

## Components

### Component 1 — `EventSourcedStateRepository`

A new class satisfying the full `StateRepository` protocol (`engine/src/memento/state/repository.py:97` — 16 methods: `get_entity`, `get_labels`, `get_entities_at_location`, `get_items_at_location`, `get_exits`, `get_actor_snapshot`, `room_manifest`, `set_attr`, `move_entity`, `transfer_item`, `link`, `unlink`, `materialize`, `ensure_indexes`). `InMemoryStateRepository` (`engine/src/memento/state/in_memory.py`) is the behavioral reference.

It is a thin orchestrator composing three collaborators:

- **`TxLog`** (Mongo, append-only) — the authoritative event store. One document per tool-use transaction:
  ```json
  {"tx_id","activation_id","actor_id","tool","ts",
   "deltas":[{"op","target_uuid","field","before","after"}]}
  ```
  `deltas` reuse the shape `EffectExecutor` already emits (`engine/src/memento/cxn/executor.py:580`).
- **`KgProjection`** — the read model over Neo4j via `bonfires_client.kg` (`create_entity`/`get_entity`/`create_edge`/`get_edges`/`update_entity`). It maps the engine `EntityDoc`/`ItemDoc` model onto KG entities + edges, reusing the production edge vocabulary (`memento/session.py`):

  | Engine concept | KG representation |
  |---|---|
  | `entity.location_uuid` | `LOCATED_IN` edge (actor → room) |
  | `inventory` (UUIDs) | `CARRIES` edges (actor → items) |
  | `is_dead` | `HAS_STATUS "DEAD"` |
  | room `attrs.exits` `[{direction,target_uuid}]` | room entity attributes |
  | item `attrs` (e.g. `{damage:4}`) | item entity attributes |
- **`ChainMirror`** — the existing seam (`engine/src/memento/state/chain_mirror.py`), unchanged. Fired only for the permadeath subset: the death beat (`set_attr(is_dead=True)` + `DIED_IN` link, per `engine/src/memento/opening/director.py`) → `on_character_death`; an item ownership change (`transfer_item`, e.g. the blade pickup) → `on_item_transferred`. Fire-and-forget, never raises, never in rollback (existing contract).

**Write semantics** (`move_entity`, `materialize`, `set_attr`, `transfer_item`, `link`/`unlink`): compute the deltas, then in order — **(1)** append one tx `{activation_id, tool, deltas}` to `TxLog` (truth), **(2)** apply the deltas to `KgProjection` (reads), **(3)** fire `ChainMirror` if the effect is in the notarized subset. Reads come **only** from `KgProjection`.

**`rebuild_projection(actor_id)`** — folds the actor's `TxLog` stream from genesis to regenerate the `KgProjection` state. This proves the log is authoritative and is exercised in the test (Component 4).

The `activation_id` is supplied per write via a context set by the `TurnRouter` (Component 2), not passed through every protocol method signature — see Component 2 for the threading mechanism.

### Component 2 — Activation log + join key

- `TurnRouter.handle(utterance, actor)` mints one `activation_id` per call (one utterance = one comprehension = one activation).
- It writes an **activation record** to the `ActivationLog` (Mongo, append-only):
  ```json
  {"activation_id","message_id","actor_id","cxn_id","tool","roles","ts"}
  ```
  `cxn_id` is the matched construction (e.g. `MOVE_CXN`/`LOOK_CXN` from `engine/src/memento/cxn/definitions.py`); `tool` is its `mcp_tool_name`; `roles` is the resolved frame.
- The `activation_id` is threaded into the `EffectExecutor` (via an explicit parameter or a per-turn context object the executor reads) so every delta it emits — and thus every `TxLog` tx — carries it.
- **Join:** `TxLog.activation_id` → `ActivationLog.activation_id` → `message_id`. Every state change is explainable by the construction and utterance that caused it.

LOOK is `read_only` (`definitions.py` `LOOK_CXN`) and produces no deltas; its activation is still recorded (with an empty/`surface`-only effect) so the cxn graph captures the witnessed-death beat.

### Component 3 — Opening session lifecycle

Two **synchronous** gateway endpoints (the deterministic `TurnRouter` returns a `TurnOutcome` directly — no async round-manager). They live in a new `gateway/src/gateway/routes/opening.py`, mounted under `/api`.

- **`POST /api/opening/start`** — body `{player_name, wallet_address, archetype}`.
  1. Create the player entity in `KgProjection`.
  2. Seed the deep-roads world (`deep_roads_seed()`, `engine/src/memento/opening/deep_roads.py`) into `KgProjection`: the room + **canon** facts (the dying adventurer); latent facts (threat, iron blade) stay latent (loader behavior, `engine/src/memento/opening/loader.py:29`). Seed `NEXT_ROOM` so MOVE can land. These setup writes are recorded as **genesis txs** in the `TxLog` with a synthetic `activation_id="genesis"` (they are not player-caused, but must be in the log so `rebuild_projection` can reproduce the seeded world).
  3. Build a `SceneDirector` (`load_seed_room`) + a **director-backed `TurnRouter`** (`director=`, `describe_client=TemplateDescribeClient()`, `repo=EventSourcedStateRepository`) — exactly the wiring `test_opening_arc.py:106-115` does, now persistent. Register it in an in-memory `opening_registry` keyed by `player_id` (mirrors `gm_room_registry`).
  4. Return initial player state + the seeded room.
- **`POST /api/opening/act`** — body `{player_id, text}`.
  1. Look up the player's `TurnRouter` from `opening_registry` (404 if absent).
  2. `outcome = await router.handle(text, player_uuid)` — this mints the activation, writes the activation log + Tx Log + KG projection (+ ChainMirror for the subset).
  3. Return the `TurnOutcome` verbatim (`engine/src/memento/cxn/types.py:112`): `status` ∈ {`narrated` (LOOK prose), `executed` (+`StateUpdate`), `clarify` (off-script), `rejected`}, plus `won`/`narration` on a winning MOVE.

This **fixes the `cxn_tools.py` director gap** for the opening path specifically (its own director-backed router). The live `mm_act` path is left unchanged in this sub-project.

**Auth:** reuse the player JWT (`sub`=player_uuid), same as `session/create` (`gateway/src/gateway/engine_auth.py`).

**Win → handoff:** when `outcome["won"]` is true, drop the `opening_registry` entry. The player is already a persisted KG entity `LOCATED_IN NEXT_ROOM`; the client transitions to the live HUD via the existing `GET /api/state` + `POST /api/room-manifest`. No migration.

### Component 4 — Reconstruction proof

A KG-native parity proof mirroring the GM-rooms approach:

- **Integration test** (`engine/tests/integration/test_opening_arc_event_sourced.py`): runs `start → "look around" → "take the iron blade" → "go on"` against the `EventSourcedStateRepository` (real Mongo + a test KG, or a KG fake satisfying the projection contract). Asserts:
  - **Projection state:** the adventurer `HAS_STATUS DEAD`; the iron blade is materialized and `CARRIES`-linked to the player; player `LOCATED_IN NEXT_ROOM`; `won` is true.
  - **Tx Log:** contains the cxn-stamped txs (MOVE/TAKE) with non-empty `activation_id`s; deltas match the projection changes.
  - **Activation log:** each tx's `activation_id` joins to an activation record whose `message_id` is the originating utterance.
  - **Rebuild:** `rebuild_projection(player)` from the Tx Log reproduces the projection state byte-for-byte.
- **Live script** (`scripts/opening_smoke.py`): drives the real `/api/opening/{start,act}` endpoints against a running gateway, asserting the same outcomes; skips cleanly when the gateway is unreachable (mirrors `gm_room_smoke.py`).

This is the parity guarantee: the engine behaves identically event-sourced/KG-native as it does in the in-memory `test_opening_arc.py`.

## Error handling

- **Off-script input** → `TurnRouter` returns `{status:"clarify", message,...}` (existing behavior); the endpoint returns it as-is for the client to render as an in-fiction nudge. No 4xx.
- **`ChainMirror` faults** are swallowed and logged (existing contract `chain_mirror.py:15`) — gameplay continues; the off-chain Tx Log remains authoritative.
- **Write ordering:** Tx Log append is the commit point. If the projection update fails after a successful Tx Log append, the projection is stale-but-rebuildable (`rebuild_projection` repairs it); the system logs and surfaces a degraded read rather than losing truth.
- **Unknown `player_id`** on `/act` → 404 (`room.not_found`-style domain error).
- **Director/repo absent** would reproduce the old inert path; the opening router is always constructed director-backed, asserted at start.

## Scope boundaries

**In scope (sub-project 1):** the opening arc only, running event-sourced/KG-native + reachable via `/api/opening/*`; the off-chain Tx Log + activation log + KG projection + the join key; `rebuild_projection`; the parity proof.

**Out of scope:**
- The client immersive-opening rendering (sub-project 2).
- Making post-win / general gameplay event-sourced — after the opening, the live Matrix-agent path drives play; the `EventSourcedStateRepository` is available to it but not retrofitted here.
- Full-onchain coverage (adding a MUD MOVE System) — MOVE stays off-chain-logged.
- Unifying the game-local activation log with the memory kernel's perdurant cxn graph (FCG/entrenchment).
- Snapshotting / replay-cost bounds for the Tx Log — fine at opening scale; revisit for long-lived worlds.

## File plan (informs the implementation plan)

- Create: `engine/src/memento/state/event_sourced.py` (`EventSourcedStateRepository`, `TxLog`, `KgProjection`, `ActivationLog`).
- Modify: `engine/src/memento/cxn/turn_router.py` (mint `activation_id`, write activation record, thread into executor), `engine/src/memento/cxn/executor.py` (accept + stamp `activation_id` onto deltas).
- Create: `gateway/src/gateway/routes/opening.py` (`/api/opening/{start,act}`) + `opening_registry`; modify `gateway/src/gateway/app.py` (mount).
- Create: `engine/tests/integration/test_opening_arc_event_sourced.py`, `scripts/opening_smoke.py`.

## Open questions for review

1. **KG projection in tests** — use a real ephemeral Neo4j, or a `KgProjection` fake satisfying the read/write contract? (Recommend a fake for the unit/integration layer + the live script for the real KG, mirroring how the GM-rooms loop split deterministic-proof vs live-smoke.)
2. **Player identity at `/opening/start`** — mint a fresh player, or accept an existing character? (Recommend fresh player for the opening; returning characters skip the opening.)
