# Memento-Mori NPC ↔ bonfires-core Agent-Runtime Integration (Design)

> **Status:** design / spec. Lifts memento-mori's NPC agents off the legacy NERDDAO
> bonfires-ai (TS/NestJS LangGraph) runtime onto the new **bonfires-core agent-runtime**
> (Python/FastAPI, DSPy-ReAct, on `origin/agent-service`). This is the **crew/agent
> layer** of the lean-core, and the migration's first real game consumer.

---

## 1. Goal & premise

Drive a memento-mori **NPC** as an agent on the new agent-runtime: the engine posts a
turn, the NPC's `dspy.ReAct` loop calls memento tools to **assess → act → speak**, the
world state mutates and the NPC's speech broadcasts to players — **end to end, on the new
runtime, against the existing mmori gateway, with zero gateway changes.**

This works because **memento-mori has no agent loop of its own.** Its NPC surface is
entirely transport-agnostic: the `mm_*` MCP tools (gateway), crews-as-tools (generation),
label-gating (`engine_auth` + `tool_labels`), and personas-as-prompts. The only
runtime-coupled pieces lived in bonfires-ai; the new runtime already supplies them
(ReAct loop, 4-stage pipeline, per-agent manager, LLM/memory adapters, the BridgeContext
identity seam, a `/v1/chat` turn API). So the lift is a **tool bridge + a JWT wire + a
turn trigger**.

### 1.1 Locked decisions (from the strategy discussion)

1. **Baseline = lean-core extracted from mmori.** This spec is the **crew/agent layer**
   on that base. It plugs into the *existing* gateway `mm_*` surface, so it does **not
   block** on the extraction — it composes with it.
2. **Runtime = the new bonfires-core agent-runtime** (`services/agent-runtime/` on
   `origin/agent-service`), not the legacy TS runtime and not a from-scratch loop.
3. **The lift is a bridge, not a rewrite.** Preserve the construction spine, `mm_*`
   tools, crews, gating, personas; add only the runtime-side glue.
4. **The kernel lands here, and each agent has its own grammar.** This integration also
   stands up the kernel (graph-memory + FCG comprehend + the `author_grammar` seam) as the
   agents' **understanding substrate**: comprehension is **per-agent** — each NPC has its
   own FCG grammar (kernel `profile = agent_id`), seeded via `author_grammar` and used by the
   pipeline's `understand` stage. This is **distinct from** the world's authoritative
   construction control (the gateway `mm_*` effect constructions). The NPC **comprehends via
   its own grammar, acts via the world's tools** (§4.7).

### 1.2 Cut line

**In:** a `memento_tools` builtin bridge in the agent-runtime; a `MementoGatewayClient`
adapter; the per-NPC JWT wire on `BridgeContext`; a lightweight **Matrix client adapter**
(`adapters/matrix/`, mirror of the Telegram adapter via `matrix-nio` — see §4.6); **a
per-agent grammar seeded on spawn (`author_grammar`, profile=agent_id) and comprehended in
the `understand` stage (§4.7)**; a minimal NPC persona/skill payload. **Trigger:** a
player/narrator message in the NPC's Matrix room drives the turn through that adapter (HTTP
`POST /v1/chat` remains an alternative entrypoint for engine-initiated cues). **Proof:** one
NPC, with its own grammar, takes one turn — comprehends the message through its grammar,
mutates world state via tools, and posts its reply to the Matrix room.

**Out (deferred):** porting *every* mmori agent type (master narrator, engine referee,
room narrator) — start with **one NPC**; AgentConfig persistence / spawner rewrite (use
the stateless `/chat` path first); replacing Matrix transport wholesale; the lean-core
extraction itself (separate spec); maturing the runtime's stubbed internals beyond what
this slice needs.

---

## 2. Background: the two runtimes (verified)

| | **NERDDAO bonfires-ai** (migrate FROM) | **bonfires-core agent-runtime** (migrate TO) |
|---|---|---|
| Stack | TS / NestJS, LangGraph | Python ≥3.14 / FastAPI, **DSPy-ReAct** |
| Location | NERDDAO/bonfires-ai (running) | `services/agent-runtime/` on `origin/agent-service` (58 ahead of staging, **not merged**) |
| Loop | `think→decide→search_stack→choose_tools⇄mcp_tools→respond→send→add_to_stack` | `understand→retrieve→act→respond` pipeline over `dspy.ReAct` |
| Tools | `MultiServerMCPClient` (MCP) | **Python callables** in `ToolRegistry`, skill-filtered, `get_dspy_tools()` |
| Identity into tools | per-agent `Bearer <JWT>` via env-var templating | `BridgeContext` ContextVar (`agent_id`, `bonfire_id`, clients) set before each `to_thread` |
| Turn API | Matrix message wake | `POST /v1/chat {agent_id, bonfire_id, actor_id, text, agent_persona, agent_skills}` |

**Maturity caveat:** the new runtime is pyright-clean and bootable, but on a branch, py314,
with some early logic (a "stub keyword matcher" commit). Adopting it = mmori is its first
game consumer, a forcing function that matures it.

### 2.1 The canonical tool pattern (clone target)

`builtin/graph_memory_tools.py` is the exact template a memento tool follows:

```python
def search_knowledge_graph(query: str, limit: int = 10) -> str:
    ctx = _get_bridge_context()                       # BridgeContext from ContextVar
    if ctx is None: return "Error: bridge context not available."
    try:
        results = _run_async(                          # schedule async on ctx.loop, block w/ timeout
            ctx.graph_memory.kg_search(bonfire_id=ctx.bonfire_id, query=query, ...),
            ctx.loop)
        return _format_kg_results(results)
    except Exception as exc:                            # tools NEVER raise — return strings
        return f"Unexpected error: {type(exc).__name__}"
```

Registered in `bootstrap.build_tool_registry()` as
`ToolDefinition(name=..., description=..., handler=...)`; the per-agent runtime applies
`registry.filter_by_skills(agent_skills)`.

### 2.2 mmori seams (reused unchanged)

- **JWT minter:** `gateway/engine_auth.sign_jwt(sub, *, type, ttl_seconds, extra_claims=None)`
  → HS256 over `JWT_SECRET`; `sub` = entity KG UUID, `type="npc"`. Accepted as Bearer on
  the gateway `/mcp` mount; `_BearerAuthMiddleware` + `_check_tool_access` enforce
  label-gating.
- **NPC tool kit** (`tools/tool_labels.py`): `INNATE_TOOLS` (`mm_get_state`,
  `mm_search_world`, `mm_get_entity`, `mm_npc_response`, `mm_npc_memory`, …) + the `"NPC"`
  kit (`mm_move`, `mm_attack`, `mm_take`, `mm_move_to`/`mm_move_within`). The gateway gates
  by the JWT `sub`'s KG labels regardless of what the runtime exposes — **double safety**.

---

## 3. Architecture & data flow

```
player / narrator posts in the NPC's Matrix room
  └─ runtime Matrix adapter (logged in as @bonfires-<npc>) receives the event, builds:
        PipelineInput { agent_id = NPC KG-UUID, bonfire_id = "mm-world-v1", actor_id,
                        text = <message>, persona = <NPC prompt>, skills = ["memento"] }
        (engine-initiated cues may instead POST /v1/chat → the same backend)
        │
        ▼  agent-runtime: backend → pipeline (understand→retrieve→act→respond)
   understand: comprehend_utterance(bonfire_id, text, profile=agent_id) → meaning via THIS agent's grammar (§4.7)
   backend sets BridgeContext { loop, bonfire_id, agent_id, correlation_id, memento: MementoToolCtx }
        │
        ▼  dspy.ReAct loop over the `memento` tool set:
   mm_get_state ──┐
   mm_search_world┤  each memento_tool callable:
   mm_move/attack/├──  reads BridgeContext → MementoGatewayClient.call(tool, args, jwt) → gateway /mcp
   mm_take/mm_act │     reads BridgeContext → MementoGatewayClient → POST gateway /v1/tools/{tool}
                  │     (gateway REST facade validates Bearer JWT, label-gates by sub, runs the construction)
   mm_npc_response┘     mm_* mutate world state (EXISTING handlers, now also reachable over HTTP)
        │
        ▼  pipeline returns response_text → Matrix adapter posts it to the room as @bonfires-<npc>
```

**Speech via the adapter; actions via the tools.** The NPC's *spoken reply* is posted to the
Matrix room by the runtime's Matrix adapter (as `@bonfires-<npc>`); the NPC's *game actions*
go through `memento_tools` (`mm_move/attack/take` mutate world state, gateway-gated by the NPC
JWT). `mm_npc_response` narrows to non-Matrix surfaces (WS/webapp broadcast). So delivery =
the adapter, actions = the tools — cleanly separated.

**Memory is tool-driven.** NPC memory = the authoritative world state via tools
(`mm_get_state`, `mm_npc_memory`), not the runtime's conversational stack. The `retrieve`
stage is configured **light/off** for memento agents (no graph-memory pre-retrieval
required for the slice).

---

## 4. Components

### 4.1 `MementoGatewayClient` (new adapter — agent-runtime) — HTTP, not MCP
`src/app/adapters/memento/client.py`. Async **HTTP** client to the mmori gateway, mirroring
`GraphMemoryClient` (the runtime is HTTP everywhere — `/v1/chat`, graph-memory, the kernel
comprehend route — so the gateway call is HTTP too, for consistency). One method:
`async def call_tool(self, *, tool: str, args: dict, bearer: str, bonfire_id: str) -> str` —
POSTs to a gateway REST endpoint with `Authorization: Bearer <bearer>` and returns the
result rendered for the LLM.

**Decision: HTTP REST facade on the gateway.** Add a thin JWT-gated REST surface to the
mmori gateway that wraps the **existing** construction handlers (`mm_get_state`, `mm_attack`,
`mm_take`, `mm_act`, …) — e.g. `POST /v1/tools/{tool_name}` reusing the same
`_BearerAuthMiddleware` + `_check_tool_access` gating as `/mcp`. The handler logic is shared
with the MCP registration (one implementation, two transports); no construction logic is
duplicated. This is the only mmori gateway addition — small, additive, and the handlers/spine
are untouched.

### 4.2 The JWT wire (the one genuinely new piece)
`BridgeContext` carries `agent_id`/`bonfire_id` but no gateway token today. Add a
`MementoToolCtx` to the bridge (or extend `BridgeContext`): `{ gateway_url, bearer }`,
where `bearer = sign_jwt(sub=agent_id, type="npc", ttl_seconds=...)` minted by the runtime
using a **shared `JWT_SECRET`** (config). The backend sets it per turn (or caches per-agent)
alongside the existing context vars. memento tools read `ctx.memento.bearer`.

**Decision:** the runtime mints per-NPC JWTs from the shared `JWT_SECRET` (same trust model
as the legacy `ENGINE_API_TOKEN` env var). The `sign_jwt` logic is small and HS256 —
re-implement or share it via `bonfires-shared`. Flagged: secret distribution to the runtime
service.

### 4.3 `memento_tools` builtins (the bridge)
`src/app/modules/tools/builtin/memento_tools.py`. One sync callable per NPC tool —
`mm_get_state`, `mm_search_world`, `mm_move`, `mm_attack`, `mm_take` (or `mm_act` free-text),
`mm_npc_response`, `mm_npc_memory` — each a clone of the `graph_memory_tools.py` shape:
read `BridgeContext`, `_run_async(MementoGatewayClient.call_tool(..., bearer=ctx.memento.bearer), ctx.loop)`,
never raise. Registered in `build_tool_registry()` as `ToolDefinition`s under a
**`"memento"` skill tag** so `filter_by_skills(["memento"])` selects exactly this set.

### 4.4 Turn trigger
**Primary:** the runtime's Matrix adapter (§4.6) receives a message in the NPC's room
(a player line, or a narrator `@mention` cue as today's `mm_trigger_npc` posts) and runs the
pipeline — `text` = the message, `agent_id` = the NPC KG UUID, persona = the existing
`NPC_SYSTEM_PROMPT_TEMPLATE` output, skills = `["memento"]`. **Alternative:** the engine can
`POST {AGENT_RUNTIME_URL}/v1/chat` with the same payload for engine-initiated cues (both hit
the same `AgentBackend.process`). **Lean path:** persona+skills travel inline (no AgentConfig
CRUD). **Scale path (deferred):** per-NPC `AgentConfig` docs so the manager holds persistent
per-agent runtimes.

### 4.5 Reused unchanged
The construction spine (state/constructicon/executor), the construction **handlers** + crews,
`engine_auth`/`tool_labels` gating, and the NPC persona templates. The only mmori gateway
*addition* is the thin REST facade of §4.1 (a second transport over the same handlers); the
handlers, executor, and spine are unchanged.

### 4.6 Player transport — where Matrix lives (the runtime has none)
**Verified:** the new agent-runtime has **no Matrix adapter** (`adapters/` = telegram, llm,
graph_memory, fireworks, web_search). The old bonfires-ai had a full Matrix appservice
provider (`src/messaging/providers/matrix.provider.ts`). **But mmori already owns its Matrix
presence** in the gateway — `matrix_bridge.py` (MatrixBridge), the appservice + per-NPC
`@bonfires-*` user registration (`agent_controller` matrix_as/hs tokens), and
`matrix_listener.py`. So the integration keeps the **runtime transport-agnostic** and lets
mmori own Matrix:
- **Trigger-in:** `matrix_listener` (existing) turns a player's room message into
  `POST /v1/chat` to the runtime — replacing the per-agent Matrix-bot wake.
- **Deliver-out:** `mm_npc_response` (gateway tool the NPC calls) posts to the location's
  Matrix room via the existing MatrixBridge appservice, puppeting the NPC's `@bonfires-*`
  identity — and/or broadcasts to the WS hub for the webapp.

**Decision: a lightweight Matrix CLIENT adapter in the runtime — not an appservice
provider.** Distinguish two things the old infra conflated:
- **Appservice *provider*** (the heavy bit — namespace registration, puppeting many
  `@bonfires-*` users, the bridge): old bonfires-ai had this (`matrix.provider.ts` +
  `matrix-appservice`). **We do NOT rebuild it.**
- **Client *adapter*** (the light bit — log in as a bot over the Matrix client-server API,
  receive room events, post replies): this is what the runtime's `adapters/telegram/`
  already is, for Telegram. **We add the Matrix equivalent.**

So the runtime gets a small `src/app/adapters/matrix/` that **mirrors `adapters/telegram/`**
(bot/handler/intent/policy/history/formatting) using a Matrix client lib (e.g. `matrix-nio`):
each NPC logs in as its **own Matrix user via an access token**, listens to its location
room(s), runs the pipeline on incoming messages, and posts the reply as that NPC. It swaps in
for Telegram per-agent (add `"matrix"` to `DeploymentConfiguration.platform`, today
`Literal["telegram","discord"]`).

**Reality check on effort:** the runtime currently has **only the Telegram adapter** — no
Discord or Slack are built yet (those existed in old bonfires-ai and are planned ports;
`platform` *anticipates* Discord but no code exists). There is **no `MessagingProvider`
abstraction yet** — `shared/protocols.py` defines only `AgentBackend.process(...)`. So Matrix
is the **second** transport: clone the Telegram adapter's ~7-file shape against `matrix-nio`,
and (optionally, since it's the 2nd) extract a thin `MessagingProvider` protocol so Matrix /
Telegram / future Discord all slot in uniformly. Bounded, pattern-following work — the same
cost as adding Discord or Slack — not novel infra.

**Identity provisioning stays in mmori (reused, not rebuilt):** the per-NPC `@bonfires-*`
Matrix accounts + tokens are already registered by `agent_controller` via the existing
appservice — the runtime adapter simply *consumes* those credentials to log in as a client.
No new provider/bridge; mmori provisions identities, the runtime adapter uses them.

**This replaces the pure-gateway trigger/delivery:** the Matrix adapter is both transport-in
(room message / narrator `@mention` cue → pipeline — same trigger model as today's
`mm_trigger_npc`) and transport-out (the NPC's spoken reply posts to the room). Game *actions*
still go through `memento_tools` (the construction tools); the adapter carries *speech*. So
`mm_npc_response`'s delivery role narrows to non-Matrix surfaces (WS/webapp); the adapter
owns the NPC's Matrix voice.

*Alternatives not chosen:* **WS/webapp only** (drop Matrix) — leanest, revisit if players
move to the webapp. **Full appservice provider in the runtime** — unnecessary; mmori already
provisions the identities.

### 4.7 Per-agent grammar — the kernel as each agent's understanding substrate
This integration also **lands the kernel** (graph-memory + the FCG comprehend route from
Track C + the `author_grammar` seam from M2) as the agents' understanding substrate, and
**each agent gets its own grammar.** Two grammar layers, cleanly separated:

| Layer | Where | Key | Role |
|---|---|---|---|
| **Agent grammar** (new here) | kernel | `bonfire_id` + **`profile = agent_id`** | how *this* NPC comprehends input + its construction repertoire |
| **World construction control** | gateway / executor | world `bonfire_id` | authoritative effects (`ATTACK` mutates hp) behind `mm_*` |

- **Seeded per agent on spawn:** when an NPC is created, seed its grammar with
  `author_grammar(bonfire_id, constructions, profile=agent_id)` — a base construction set
  (the move/attack/take action constructions + dialogue constructions). The grammar entrenches
  / grows per agent over time (§9).
- **Comprehension is per-agent:** the pipeline's **`understand`** stage comprehends the
  incoming message through *this agent's* grammar — `comprehend_utterance(bonfire_id,
  utterance, profile=agent_id)` via graph-memory's comprehend route — yielding the meaning /
  activated constructions that drive `act`. Two NPCs reading the same line can understand it
  differently because they hold different grammars. (This is where the kernel's per-agent
  comprehension replaces a generic intent classifier.)
- **Comprehend (agent) → act (world):** the NPC understands via its grammar, then the `act`
  stage's `memento_tools` enact through the world's `mm_*` effect constructions. The agent's
  grammar governs *understanding*; the world's constructicon governs *consequences*.
- **Seeding seam (decided):** expose `author_grammar` as a **graph-memory route** the
  runtime/spawner calls on NPC creation — keeps the per-agent grammar lifecycle alongside
  comprehend in the kernel HTTP surface. M2 chose `author_grammar` as a kernel *seam*, not yet
  an HTTP route, so exposing it is the new kernel-side work this requires.
- **Shared cxns = agreements (forward).** Agent grammars are **not strictly isolated** —
  agents can **share constructions to form agreements / collectives**, e.g. a `the-guild` cxn
  shared across guild members. Model: a shared grammar layer keyed by the collective
  (`profile = <guild/faction-id>`) that member agents' comprehension *also* consults, so an
  agent's **effective grammar = its own (`profile=agent_id`) + the shared grammars it belongs
  to**. Comprehend activates constructions across the agent's grammar **and** its shared
  layers; agreeing to / enacting a guild interaction entrenches `the-guild` cxn for all
  members — a construction *is* the agreement. Out of the one-NPC slice, but the per-agent
  profile keying + composable grammars make it the natural next layer (§9). It also reframes
  social mechanics (factions, contracts, reputation) as **shared constructions** rather than
  bespoke systems.
- **Hashing (carry the M2 fix):** the per-agent grammar must be **hashed-lemma-native** (lemma
  buckets), not `:all-cxns`, to avoid per-agent bloat — fold in the M2 hashing fix (verb-anchored
  lexical cxns + categorial-network co-activation; drop the `authored:true` `:all-cxns` bypass).
- **For the slice:** seed **one** NPC's grammar (`profile=that NPC`) with the base action +
  dialogue constructions and comprehend its input through it. The per-agent model generalizes
  to every agent; one agent's grammar is the proof.

---

## 5. Testing

**Principle: no live LLM in unit tests.** DSPy supports a dummy/configured LM; mock the
gateway transport.

- **agent-runtime unit:** `memento_tools` callables against a fake `MementoGatewayClient`
  (mirrors the `graph_memory_tools` test pattern) — bridge-context read, arg pass-through,
  error-string-not-raise; JWT-wire mints a valid `type:"npc"` token for `agent_id`; the
  Matrix adapter handler against a fake Matrix client (room event → `AgentBackend.process` →
  reply posted), mirroring the Telegram adapter tests.
- **mmori unit:** per-NPC Matrix credential provisioning hands the runtime a usable
  `@bonfires-*` access token (reusing the existing appservice registration).
- **Integration (gated):** a real NPC turn — a message in the NPC's Matrix room against a
  booted agent-runtime + mmori gateway (testcontainers/compose), DSPy with a scripted/dummy
  LM that calls `mm_get_state` then `mm_attack`; assert world state mutated, gateway gating
  honored the NPC JWT, and the NPC's reply posted to the room as `@bonfires-<npc>`. The
  end-to-end proof.

---

## 6. Repo & PR plan

| Repo | Change |
|---|---|
| **bonfires-ai-core** (`agent-service`) | `adapters/memento/client.py`, `builtin/memento_tools.py`, the `MementoToolCtx` JWT wire on `BridgeContext` + backend set, register the `"memento"` skill tools; **`adapters/matrix/`** (client adapter, mirror of `adapters/telegram/` via `matrix-nio`), add `"matrix"` to the `platform` literal, optionally extract a `MessagingProvider` protocol |
| **memento-mori** | add a thin JWT-gated REST facade (`POST /v1/tools/{tool}`) over the existing construction handlers (§4.1); provision each NPC's Matrix credentials (reuse the existing appservice-registered `@bonfires-*` users/tokens from `agent_controller`) to the runtime; narrator cues an NPC by posting to its room (existing `mm_trigger_npc` model) or via `/v1/chat`; `AGENT_RUNTIME_URL` config. **Construction handlers/executor/spine unchanged.** |
| shared | `JWT_SECRET` available to the runtime; optionally share `sign_jwt` via `bonfires-shared` |
| **graph-memory** (kernel) | expose an **`author_grammar` route** (per-agent grammar seeding, `profile=agent_id`) — M2 left it a kernel seam, not a route; the comprehend route (Track C, PR #121) already exists. The runtime's kernel client calls comprehend with `profile=agent_id` in `understand`, and `author_grammar` on NPC spawn. Carry the M2 **hashing fix** so per-agent grammars are hashed-lemma-native (no `:all-cxns` bloat). |

Branch off `agent-service` for the runtime side; off the lean-core branch for the mmori
side. The runtime work lands on `agent-service` (its home), advancing that branch.

---

## 7. Risks / caveats

- **Runtime maturity:** `agent-service` is branch-only, py314, partially stubbed. We inherit
  its gaps; the slice should only depend on the ReAct loop + tool registry + BridgeContext +
  `/chat`, which exist.
- **MCP-client dependency** in the runtime (recommended path) — if heavy, fall back to a
  gateway REST facade (§4.1b).
- **Secret distribution:** the runtime needs `JWT_SECRET` to mint NPC tokens.
- **DSPy ReAct tool-calling reliability** for game actions (does the NPC reliably call
  `mm_attack` with a valid target UUID?) — the gated integration test is the proof; the
  persona/tool descriptions are the lever.
- **Per-agent grammar (§4.7):** lands the kernel + adds two new dependencies — an
  `author_grammar` graph-memory route (M2 left it a seam) and per-agent comprehend in the
  `understand` stage. Risks: per-agent grammar **bloat** if not hashed-lemma-native (carry the
  M2 hashing fix); seeding/store cost at NPC-spawn scale; comprehend latency on the turn hot
  path. The slice proves it with **one** agent's grammar; scale + entrenchment are forward work.
- **Matrix transport (§4.6):** the runtime has no Matrix adapter. The slice assumes Matrix
  stays gateway-side (fork B) or is dropped for WS (fork A) — **no runtime adapter is
  built**. If fork (C) is chosen, building a native Matrix provider in `agent-service` is a
  separate, larger effort. For (B), confirm the gateway MatrixBridge can puppet-post as the
  NPC's `@bonfires-*` identity via the appservice (`agent_controller` already registers
  these users + tokens).

---

## 8. Definition of done (the slice)

- `memento_tools` + `MementoGatewayClient` + the JWT wire + the `adapters/matrix/` client
  adapter land on `agent-service` with unit tests (fake transport / fake Matrix client, no
  live LLM).
- An NPC runs as a Matrix bot (logged in via its provisioned `@bonfires-*` credentials),
  persona + `["memento"]` skill supplied per turn.
- The NPC's **own grammar is seeded** via `author_grammar(bonfire_id, …, profile=agent_id)`
  (hashed-lemma-native, no `:all-cxns`) and used by the `understand` stage.
- **One NPC, one turn, end to end:** a player/narrator message in the NPC's Matrix room →
  the NPC **comprehends it through its own grammar** (`comprehend_utterance(profile=agent_id)`)
  → calls `mm_get_state → mm_attack (or mm_act)` (world state mutates, gateway gates the NPC
  JWT) → posts its spoken reply to the room as `@bonfires-<npc>` — proven by the gated
  integration test.
- The mmori gateway gains only a thin REST facade over the existing construction handlers
  (§4.1); the handlers, executor, construction spine, and crews are unchanged.

---

## 9. Forward map

- **The activation→unlock loop (the core mechanic).** The kernel exposes the *activated
  construction ids* per turn (already in `comprehend`'s `applied_cxn_ids`); mmori treats those
  cxn ids as **capability keys that unlock which `mm_*` functions the agent may call** — a
  deterministic loop: `player input → agent comprehends via its grammar → activated cxn ids →
  those ids unlock tools → action`. Construction activation *is* the capability gate; this
  lives in the **gateway plan** (extend `_check_tool_access` to gate on activated cxn ids, not
  only KG labels), and depends only on the kernel emitting stable construct ids (the
  kernel-prereqs plan provides them).
- **Agent-created cxns.** Agents author new constructions at runtime (an incremental
  `author_grammar` that *adds* a cxn to an existing grammar) — e.g. an agent coins
  `the-new-guild` mid-conversation; its activation pattern (form pole) emerges from the
  conversation vernacular. Foundation for emergent social structure.
- **State-linked cxns.** Constructions tie to game state: `the-guild` linked to a `guild-bank`
  cxn that *holds assets*. The cxn id is the **join key** between the kernel's grammar layer and
  mmori's construction-control/state layer — a construction can carry/gate state, not just
  meaning.
- Port the other agent types (room narrator, engine referee, master narrator) onto the same
  bridge — each with its own per-agent grammar.
- **Per-agent grammar growth/entrenchment:** agents start from a seeded base grammar and
  entrench/extend their own constructions over time (the generative-composition + entrenchment
  spec; entrenchment-as-propagation-weight from the kernel-native HyperMem design). Distinct
  NPC "voices"/behaviours emerge as their grammars diverge.
- **Shared cxns / agreements (§4.7):** a shared grammar layer per collective (guild, faction,
  contract) that members' comprehension composes with — `the-guild` cxn and friends. Social
  mechanics become shared constructions, not bespoke systems; agreeing = sharing/entrenching a
  cxn. Needs kernel support for **composable/multi-profile comprehension** (an agent activates
  its own grammar + the shared layers it belongs to).
- Persistent `AgentConfig` registration + a mmori spawner that targets the runtime's agents
  API instead of the Bonfires SDK.
- Retire the Matrix wake / bonfires-ai dependency for mmori once coverage is complete.
- Fold in the lean-core extraction (this layer already sits on the gateway surface it produces).
