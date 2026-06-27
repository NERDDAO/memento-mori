# Agent-Driven Opening — "Catch the Construction" (Slice 1) — Design Spec

**Date:** 2026-06-26
**Status:** Approved (brainstorming) — ready for implementation plan
**Lineage:** branch `opening/cxn-catch` off `opening/engine-core` (@ `0b83829`, carries persona P1/P2/P3 + the persona-in-typewriter integration).
**Repos:** spans **memento-mori** (gateway + engine + client) *and* **bonfires-ai-core** (agent-runtime manifest/tools + graph-memory kernel grammar).

## North star (the larger vision this is slice 1 of)

The game is **"catch the constructions" — Pokémon for grammar.** The core loop: a player statement is comprehended by FCG into a *construction*; when that construction fires you **see it happen** and you've "caught" it; caught constructions accrete into a personal constructicon (the Pokédex); you bind statements to keys and **edit those statements as your grammar grows** to invoke richer constructions; a construction's effect is an operation over an **expressive ECS**, so "knowing more grammar" literally means "more expressive moves over entities/components." Most of this substrate already exists in the repo (the effectful constructicon + `EffectExecutor`, FCG comprehension, the self-spine, the "constructions all the way down" ECS vision). What's new is the **game layer**: visible cxn-firing, the constructicon-as-Pokédex, and key↔statement binding.

**This spec is slice 1: the opening *is* catch #1.** The player is created as a self-agent, is auto-issued the statement "look around", the LOOK construction fires *visibly*, the world is drawn, and the LLM narrates it. No Pokédex persistence and no keybinding UI yet (slice 2+). The one game-layer mechanic that ships here is **seeing the construction fire**.

## Decisions locked in brainstorming

1. **The player IS the persona** (self-agent), not a separate NPC. The named character reasons and calls tools.
2. **Pre-authored Deep Roads room** — reuse `deep_roads_seed`; no procedural lazy-canon generation yet.
3. **"look around" via FCG comprehension** ("as a statement") — the cxn genuinely fires from comprehension, not a scripted dispatch.
4. **Comprehend + fire inside the agent-runtime persona's own ReAct turn** — one unified agent loop (comprehend → tool-use → narrate), the truest "player IS the agent".
5. **Wire the kernel, drop the in-memory NPC seed** — the player-persona is created from the player entity; the `PERSONA_OPENING_SEED` in-memory `opening-wanderer` is not used on this path.
6. **Catch depth: see-it-fire** — log + a UI "◇ caught: LOOK" beat. No constructicon persistence.
7. **Narrator auto-issues "look around"** — no key↔statement binding UI in slice 1.

## Verified ground truth (from exploration)

- **`LOOK_CXN` exists** — `engine/src/memento/cxn/definitions.py`: `name="LOOK"`, `predicate="look"`, `mcp_tool_name="mm_look"`, `read_only=True`, `effect_template=[]`. In `CONSTRUCTION_REGISTRY` (always available). `TurnRouter.handle` already has a comprehend→predicate-match→LOOK branch (`turn_router.py` step 2, ~line 154), and stamps an `ActivationRecord(cxn_id="LOOK", tool="mm_look")` there.
- **Scene/persona creation** — gateway → `POST /v1/scenes/{location_uuid}/open` with `{bonfire_id, scene_actor_id, gm_self: SelfDto, roster: [SelfDto]}`. `SelfDto = {id, embodiment_agent_id, names, seat ("LLM"|"human"), capabilities: [tool names]}` (`scenes_dto.py`). A scene is keyed by `location_uuid`; personas are roster members; `add_persona` is server-side. **No code creates a self for the *player* today** — `RoomDriver.open_room` explicitly filters players out (`room_driver.py:206`). `DirectorSeat.HUMAN` exists as a schema enum but is never sent.
- **Tool kits** — `engine/src/memento/tools/tool_labels.py`: `get_allowed_tools(labels) -> set` unions `INNATE_TOOLS` + `KITS[label]` + `LABEL_TOOLS[label]`. `RoomDriver._npc_self_spec` puts `sorted(get_allowed_tools(entity.labels))` into `SelfDto.capabilities`. **`mm_look` is absent** from the agent-runtime `MEMENTO_MANIFEST` (`bonfires-ai-core/.../manifests/memento.py`), from all `KITS`/`INNATE_TOOLS`, and has no registered gateway MCP handler (`cxn_tools.py` registers only MOVE/ATTACK/TAKE).
- **Turn shape** — `POST /v1/scenes/{id}/turn {self_id, message, correlation_id?}` → `{response_text, should_respond}`. Internally a DSPy ReAct pipeline (comprehend → tool use → respond); `ActModule` already feeds `tool_observations` from the trajectory into the respond step, so **a tool the agent calls during the turn can be narrated by the same turn**. There is no "pre-injected tool result" param — the agent must call the tool itself.
- **Live comprehension** — `HttpComprehensionClient` → `POST /v1/bonfires/{bonfire_id}/kernel/comprehend {actor_id, utterance, entity_hints, allowed_construct_ids}` → `{frame: {predicate, roles, applied_cxn_ids, matched} | null}`. Graph-memory returns `frame=None` (`diagnostics.status="no_grammar"`) unless a grammar is authored via `POST /v1/bonfires/{bonfire_id}/kernel/author-grammar` with a `ConstructionSpecDTO` (`{construct_id, name, lemmas:["look"], predicate:"look", roles:[], lexicon, form}`). **LOOK has no roles/connective**, so it dodges the FCG closure-balloon that bites MOVE's bare-space connective (`test_persona_grammar_gating.py`).
- **`NullComprehensionClient`** (no `KERNEL_BASE_URL`/`GM_INTERNAL_TOKEN`) returns `matched=False` for everything → every statement clarifies. This is why the live demo's free text fell back to "I didn't understand that."
- **Observability gap** — there is *zero* logging or WS event when a construction matches/fires today; only the in-process `ActivationLog` records it. WS event types today: `player_joined/left`, `presence`, `death_feed`, `episode_feed`, `tool_event` (`{type, tool, npc, summary, data, location, channel}`), `npc_joined`. No `cxn_fired`/`construction_matched` type.
- **Known bug to avoid** — `cxn_tools.py` `mm_act` does not handle the `"narrated"` TurnOutcome (LOOK) and would `AssertionError` on `update is None`. The agent-runtime ReAct path for `mm_look` must not route through that `mm_act` branch.
- **Player today** — `/opening/start` seeds the player as `{kind:"character", labels:["Character"], location_uuid:LOC_DEEP_ROADS}` into a *per-player* `EventSourcedStateRepository` (`opening_repos[player_uuid]`), disjoint from `app.state.cxn_repo`. Only `["Character"]` → `get_allowed_tools` grants only `INNATE_TOOLS`.

## Architecture

The unified agent-ReAct loop. The player is a self-agent at the agent-runtime; its turn comprehends "look around" → LOOK fires (visible) → it ReAct-calls `mm_look` → the tool (executed gateway-side) draws the room and returns a summary → the same turn's LLM narrates it.

```
[client] title card: "Memento Mori" + epigraph fade in/out → name box "What's your name?"
   │
   ├─1─▶ POST /api/opening/start {player_name}
   │        → player entity {kind:character, labels:[Character, Player, Self]} (+ persona-capable labels)
   │        → register player as a self-persona at the agent-runtime:
   │             gateway → POST /v1/scenes/{LOC_DEEP_ROADS}/open
   │                roster=[ SelfDto(player_uuid, seat=LLM, capabilities=get_allowed_tools(labels) ∋ mm_look) ]
   │
   └─2─▶ narrator auto-issues "look around"
          gateway → POST /v1/scenes/{LOC_DEEP_ROADS}/turn {self_id=player_uuid, message:"look around"}
             │   ── inside the agent-runtime ReAct turn ──
             ├─ comprehend "look around" → kernel FCG → applied_cxn_ids ∋ "LOOK"
             │     └─▶ ✦ CXN FIRED → emit cxn_fired (server log + WS event) → client "◇ caught: LOOK" beat
             ├─ ReAct calls mm_look (gateway-hosted MCP tool, read-only)
             │     ├─▶ reads Deep Roads room + entities (deep_roads_seed)
             │     ├─▶ WS draw event → client RoomViewportAdapter draws room + places entities
             │     └─▶ returns a room+entity text summary into the ReAct trajectory
             └─ LLM narrates the look outcome → response_text
                   └─▶ WS (mm_npc_response-style, attributed to the player-self) → typewriter prose pane
```

### Component A — Cinematic intro (client)

Replace the legacy `#char-create-overlay` flow with: (1) a centered black title card — "Memento Mori" + the epigraph *"The old world is dying, yet the new world struggles to be born: this is the time of monsters"* — fading in then out; (2) a single name box "What's your name?". On submit, the name drives `/opening/start`. The epigraph is **not** in the typewriter stream (it's a title card); the typewriter prose pane is reserved for the look narration. The legacy overlay is hidden/removed (closes the standing Phase-1 gap).

### Component B — Player-as-persona (gateway)

`/opening/start` (or a new step right after) creates the player as a self-persona:
- Seed the player entity with labels that grant `mm_look` via `get_allowed_tools` (e.g. add a `Self`/`Player`-style label whose kit includes `mm_look`; see Component D for where `mm_look` is granted).
- Build a `SelfDto` for the player (`seat="LLM"` — the agent voices/narrates on the player's behalf; the human "drives" only by the narrator auto-issuing statements in slice 1) and POST `/v1/scenes/{LOC_DEEP_ROADS}/open` with the player in the `roster`. This is the new "create a self for the player" path that does not exist today.
- The opening's per-player `EventSourcedStateRepository` and the scene path must agree on the player + room identity at `LOC_DEEP_ROADS` (the two-disjoint-stores pattern from the persona-in-typewriter slice still applies; the room contents `mm_look` reads come from the authoritative opening room — see Component D).

### Component C — `mm_look` tool (gateway-hosted MCP, read-only)

A new `mm_look` MCP tool registered gateway-side (alongside the MOVE/ATTACK/TAKE registration in `cxn_tools.py`), so the agent-runtime persona's ReAct loop can call it and it executes where the room data + WS hub live:
- **Reads** the pre-authored Deep Roads room + entities (the opening room manifest).
- **Broadcasts** a draw WS event (room + entities) → the client `RoomViewportAdapter.setContents` draws the room and places entities. (Reuses the existing room-contents → viewport render path; the new part is that `mm_look` *triggers* it server-side rather than the client polling `/room/{uuid}/contents`.)
- **Returns** a concise text summary (room name, description, salient entities) into the ReAct trajectory so the *same turn's* LLM narrates it.
- Read-only (no `EffectExecutor` state effects); must NOT route through the `mm_act` `"narrated"`-unhandled branch.

### Component D — `mm_look` in the agent-runtime manifest + a kit

So the player-persona is *allowed* to call `mm_look`:
- Add an `mm_look` `CxnToolSpec` to `MEMENTO_MANIFEST` (`bonfires-ai-core/.../manifests/memento.py`) — a free spec (no `unlock_cxn_ids`; read-only) so it's always in the manifest.
- Grant it via a kit/label in `engine/src/memento/tools/tool_labels.py` (e.g. a `Perception`/`Self` label, or `INNATE_TOOLS`) so `get_allowed_tools(player.labels)` includes `mm_look` and it reaches `SelfDto.capabilities` → `CapabilitySet.from_tool_names`.

### Component E — Kernel LOOK grammar (graph-memory)

Author a LOOK construction for the opening bonfire so the kernel comprehends "look around":
- At boot (or first opening), call `POST /v1/bonfires/{bonfire_id}/kernel/author-grammar` (header `X-Internal-Token` + `X-Permission: write`) with a `ConstructionSpecDTO` for LOOK. Idempotent / gated.
- **PROVEN grammar (Phase 0, 2026-06-26):** the minimal verb-only spec comprehends "look around" at confidence 1.0:
  ```json
  {"construct_id": "mm.look.v1", "name": "LOOK", "predicate": "look",
   "lemmas": ["look"], "roles": [], "lexicon": [], "form": [{"role": "verb"}]}
  ```
  Authored against bonfire `6a3e8c71f3326302eee047e4`, `comprehend("look around")` → `{matched: true, applied_cxn_ids: ["mm.look.v1"], confidence: 1.0}`. Verb-only (no connective) → dodges the FCG closure-balloon. "look", "look around", "look about", "i look around", "look around the room" all match. **Spike script:** `scratchpad/spike_look_comprehend.py`.

### Component E note — comprehension result keying (Phase-0 finding)

The kernel returns `predicate: ""` (empty) for the minimal LOOK construction — it does not surface a verb predicate. Therefore **`cxn_fired` keys on `applied_cxn_ids` containing the construct id** (`"mm.look.v1"`), NOT on `predicate == "look"`. The construct id → display name ("LOOK") mapping for the catch beat is owned by the gateway/agent-runtime (a small static map), since the kernel returns only the construct id. (If a real `predicate` is later wanted, the authored construction would need a `v` role; not required for slice 1.)

### Component F — cxn-fired observability (the game mechanic)

When comprehension yields `applied_cxn_ids ∋ "LOOK"` (the agent-runtime turn's comprehend step), emit a **visible** signal. Comprehension runs *inside* the agent-runtime, but the **player's WebSocket lives on the gateway** — and today the `/turn` response (`{response_text, should_respond}`) does **not** surface what fired. So the signal must be plumbed back:
- **Agent-runtime (bonfires-ai-core):** extend `SceneTurnResponse` to carry the fired construct ids — `fired_cxns: list[str]` (the comprehend step's `applied_cxn_ids`, e.g. `["mm.look.v1"]`). (Also: a structured agent-runtime log line at the comprehend point — `cxn fired: mm.look.v1 (actor=<player>)`.) Note the kernel returns `predicate=""` for the minimal LOOK (Phase-0 finding), so the construct **id** is the carried key, not a predicate.
- **Gateway:** when `RoomDriver.drive_turn` receives a turn response with `fired_cxns`, map each construct id → a display name via a small static map (`"mm.look.v1" → "LOOK"`), emit the **server log line**, and broadcast a new WS event `{type:"cxn_fired", cxn:"LOOK", construct_id:"mm.look.v1", actor_id, location}` to the player (the gateway owns the WS hub).
- **Client:** on `cxn_fired`, render a "◇ caught: LOOK" beat — a distinct prose/sigil line (its own accent, e.g. the NPC gold or a dedicated catch color) announcing the catch, ahead of the narration line.

This keeps the *origin* of the signal at the agent-runtime comprehend step (Decision 4) while the *emission* (log + WS) happens gateway-side where the socket is. The engine `turn_router.py` step 2 is the equivalent firing point on the engine path and already stamps `ActivationRecord(cxn_id="LOOK")` — that remains the canonical in-process record; the live slice-1 signal flows agent-runtime → turn response → gateway → WS.

### Component G — Narration render (client)

The look narration (`response_text` from the player-self's turn) renders in the typewriter prose pane — reuse the persona-in-typewriter WS adapter (`opening-ws.ts` / `routeOpeningMessage`), attributing the line to the player-self (not an NPC). Optionally a distinct style from NPC dialogue.

## Data flow (one opening)

1. Title card (epigraph fade) → name box → submit `{player_name}`.
2. `/opening/start` → player entity + register player-self at `/v1/scenes/{deep_roads}/open`.
3. Narrator → `/v1/scenes/{deep_roads}/turn {self_id=player, message:"look around"}`.
4. Agent-runtime comprehends → `applied_cxn_ids ∋ LOOK`; the turn response carries `fired_cxns:["LOOK"]` back to the gateway → gateway logs + broadcasts **cxn_fired** WS event → client "◇ caught: LOOK".
5. ReAct calls `mm_look` (gateway) → draw WS event → client draws room + entities; tool returns summary.
6. LLM narrates → `response_text` → WS → typewriter prose.

## Error handling

- **No comprehension match** (kernel down / grammar missing / closure-balloon): the turn degrades — no `cxn_fired`, no catch beat. The opening must still render the room (the draw can be triggered directly as a fallback) and a neutral narration; never a 500. Phase 0 de-risks this; the fallback keeps the opening playable if the kernel hiccups.
- **`mm_look` failure** (room read / draw): best-effort; the turn still returns a narration; logged.
- **Persona/agent-runtime failure**: the opening start still returns; the look sequence degrades to the existing client-side room render. (Same failure-isolation contract as the persona-in-typewriter slice.)
- **Kernel grammar author failure at boot**: non-fatal; logged; comprehension simply won't match until authored.

## Testing

- **Phase 0 (spike):** an integration check that `author-grammar(LOOK)` then `comprehend("look around")` returns `applied_cxn_ids ∋ "LOOK"` against the live kernel. Go/no-go.
- **Component F:** unit — given a comprehend result with `applied_cxn_ids=["LOOK"]`, the firing point emits the `cxn_fired` log + WS event exactly once; none when no match. Client — `cxn_fired` → the "◇ caught" beat renders.
- **Component C/D:** the player-persona's turn with "look around" calls `mm_look`; `mm_look` broadcasts the draw event with the Deep Roads entities and returns a non-empty summary; read-only (no state mutation). A persona turn with `mm_look` does not hit the `mm_act` `"narrated"` AssertionError.
- **Component B:** `/opening/start` registers a player `SelfDto` (seat=LLM, capabilities ∋ mm_look) at `/v1/scenes/{deep_roads}/open`.
- **Component A/G:** client — title-card fade sequence; name submit drives start; look narration renders in the prose pane attributed to the player-self.
- **Live browser demo (the goal):** title card → name → "look around" auto-issued → "◇ caught: LOOK" beat + room drawn + LLM flavor narration in prose; the cxn firing visible in the gateway log.

## Phasing (build order — each independently testable)

- **Phase 0 — comprehension spike (go/no-go): ✅ DONE 2026-06-26 — GO.** Authored the verb-only `mm.look.v1` against bonfire `6a3e8c71f3326302eee047e4`; `comprehend("look around")` → `matched=true, applied_cxn_ids=["mm.look.v1"], confidence=1.0` (and 4 other variants). Verb-only dodges the closure-balloon. Finding folded into Component E. (`scratchpad/spike_look_comprehend.py`.)
- **Phase 1 — cxn-fired observability:** the log + WS `cxn_fired` event + the "◇ caught: LOOK" client beat. (Testable against a stubbed comprehend result; the game mechanic lands first.)
- **Phase 2 — player-as-persona + `mm_look`:** player `SelfDto` creation; `mm_look` in the manifest + a kit; the gateway-hosted `mm_look` (draw + summary); narration over the persona turn.
- **Phase 3 — cinematic intro:** epigraph fade + name box; wire it to start the sequence; retire the legacy overlay.

## Out of scope (slice 2+ / future)

- **Constructicon-as-Pokédex** — persisting caught constructions per player, the "gotta catch 'em all" counter/collection UI.
- **Key↔statement binding** — editable statement slots bound to keys; editing the bound statement as the grammar grows.
- **More constructions** — MOVE/ATTACK/TAKE and beyond as catchable cxns (and the closure-balloon work they require).
- **Expressive-ECS effects** — constructions whose effects are richer ECS component/system operations.
- **Lazy-canon / look-to-build** — procedurally generating the room+entities on first look (slice uses the pre-authored Deep Roads).
- **Multi-room / opening→main-loop handoff.**
