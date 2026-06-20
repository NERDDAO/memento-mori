# Memento-Mori Runtime Side — NPCs on the bonfires-core Agent-Runtime (Design)

> The runtime half of the agent-runtime integration: lift one mmori NPC onto the
> bonfires-core **agent-runtime** (`bonfires-ai-core/services/agent-runtime`, branch
> `origin/agent-service`) so it hears a player on **Matrix**, comprehends via its **own kernel
> grammar**, **activates** the matching cards on the mmori gateway, and **acts** through the
> gateway's **card-tool REST facade** — closing the loop the kernel-prereqs and construction-card
> work built. Sub-spec of `2026-06-20-mmori-agent-runtime-integration-design.md` (§4); targets the
> now-PR'd kernel `comprehend(profile)` route and the gateway unlock loop.

## 1. Goal & premise

mmori has **no agent loop** — it is all tool surface (gateway `mm_*` tools), crews-as-tools,
label-gating, and personas-as-prompts. The bonfires-core agent-runtime IS a real loop
(`dspy.ReAct` over an `understand → retrieve → act → respond` pipeline, per-agent runtime + tool
registry, `BridgeContext` identity seam, `POST /v1/chat`). So lifting an NPC onto it = give the
runtime a **general cxn-tool bridge** (mmori as the first consumer) + a **comprehend→activate step** + a **Matrix transport**, then
seed one NPC. The construction spine, crews, and gateway handlers stay unchanged; the gateway's
card-tool REST facade (`POST /v1/tools/{tool}`) and activation endpoint
(`POST /v1/agents/{id}/activation`) are the runtime's targets.

### 1.1 Locked decisions

1. **Matrix is the turn trigger** (in-slice) — the runtime gets a Matrix **client** adapter
   (matrix-nio), mirroring the existing telegram adapter; it logs in as `@bonfires-<npc>` and
   drives the pipeline. `POST /v1/chat` is the **inner contract** (same backend) and the primary
   test surface.
2. **One NPC, pre-seeded grammar** — a single `AgentConfig` + its grammar seeded by a **script**
   (reusing the M2 `author_grammar` route + `seed_game_grammar` pattern, `profile=NPC-UUID`). No
   spawn-time authoring pipeline this slice.
3. **The runtime mints the NPC JWT** from a shared `JWT_SECRET` (HS256, `sub=NPC-KG-UUID`,
   `type="npc"`) — same trust model as the gateway's `engine_auth`. Re-implemented as a tiny local
   signer (the gateway's `engine_auth` is not cross-service importable).
4. **Two services, two clients.** Kernel **comprehend** lives on graph-memory
   (`/v1/bonfires/{id}/kernel/comprehend`) → extend the runtime's existing `GraphMemoryClient`.
   Tool calls + activation push go to a service exposing the unlock-loop contract → a **general
   `CxnGatewayClient`** (the mmori gateway is the first *configured* instance, not hardcoded).
5. **cxn-tools are general, manifest-driven.** The unlock loop is a **protocol** (comprehend →
   activate → call activation-gated tools), not a memento feature. A `build_cxn_tools(manifest,
   gateway)` factory generates sync ReAct wrappers (clone of `graph_memory_tools.py`: read
   `BridgeContext`, `_run_async`, **never raise**) from a declared **`CxnToolManifest`** (tool names
   + arg signatures). The memento toolset is one **static manifest** in config. A second service
   plugs in by adding a `cxn_gateway` config + its manifest — no new runtime code. Dynamic
   manifest-endpoint discovery (`GET /v1/tools`) is a deferred fast-follow.

### 1.2 Cut line

**In:** the general `CxnGatewayClient` (`call_tool` + `push_activation`) + the `build_cxn_tools`
factory + the static memento `CxnToolManifest`; the JWT wire into `BridgeContext`; the
comprehend→activate step; `GraphMemoryClient.comprehend`; a config-driven `cxn_gateways` + skill
group; the Matrix client adapter (one NPC); one seeded NPC `AgentConfig` + a grammar-seed script;
`/v1/chat`-driven integration test.

**Out (follow-ups):** dynamic tool-manifest discovery (`GET /v1/tools`); multi-gateway per agent;
multi-NPC spawning service; `AgentConfig` CRUD/UI; spawn-time grammar authoring; the kernel
identity-DAG (traits stay seeded/test-injected); discord/slack; the room narrator / engine referee
/ master narrator agents (same bridge, later).

---

## 2. Background: verified seams (do not re-derive)

In `bonfires-ai-core/services/agent-runtime/src/app` on `origin/agent-service`:

- **`modules/tools/bridge_context.py`** — `@dataclass(frozen=True) BridgeContext{loop, bonfire_id,
  agent_id, correlation_id, graph_memory, fireworks, web_search, image_generation_model}` in
  `bridge_context_var: ContextVar`. **No JWT, no memento client today** — the wire to add.
- **`modules/tools/builtin/graph_memory_tools.py`** — the clone template: `_get_bridge_context()`,
  `_run_async[T](coro, loop)` via `run_coroutine_threadsafe(coro, loop).result(timeout=10s)`, sync
  wrappers that never raise (return strings).
- **`modules/tools/registry.py`** — `ToolRegistry.register(ToolDefinition)`, `get_dspy_tools()`,
  `filter_by_skills(skills)` (**filters by tool NAME**), `exclude(names)`.
- **`modules/pipeline/backend.py`** — `DSPyAgentBackend.process(PipelineInput)`;
  `_process_with_correlation` calls `bridge_context_var.set(BridgeContext(...))`, then runs
  `understand` (LLM `ChainOfThought`, learns `should_respond`/`retrieval_path`) → `retrieve`
  (FAST/DEEP) → `act`/`respond` via `_run_pipeline_in_thread`.
- **`modules/pipeline/modules/understand.py`** — an **LLM** `ChainOfThought`; it does **NOT**
  comprehend via the kernel. The kernel comprehend is a NEW step.
- **`adapters/graph_memory/client.py`** — `GraphMemoryClient` (httpx): `kg_search`, `get_episode`,
  `expand_entity`, `get_stack`, `add_stack_messages`, `_headers(bonfire_id, permission,
  correlation_id)`. **No `comprehend` — add it.**
- **`adapters/telegram/`** — `handler.py` (`TelegramHandler.handle_message`: `should_respond`
  policy → build `PipelineInput` → `backend.process` → reply), `policy.py` (`should_respond`),
  `bot.py`, `history.py`, `formatting.py` — the shape the Matrix adapter mirrors.
- **`models/agent_config.py`** — Beanie `Document AgentConfig{agent_name, agent_username,
  enabled_skills: list[str], persona…}`, `DeploymentConfiguration{platform: telegram|discord,
  bonfire_id, …}` — **no matrix fields; add them.**
- **`modules/chat/chat_routes.py`** — `POST /v1/chat` → `manager.get_runtime(agent_id).backend.process`.

Gateway targets (mmori, branch `cxn/card-model` / PR #2): `POST /v1/tools/{tool}` (Bearer JWT,
label + activation gated), `POST /v1/agents/{agent_id}/activation {cxn_ids}` (Bearer, `sub==agent_id`).
Kernel target (graph-memory, PR #122): `POST /v1/bonfires/{id}/kernel/comprehend {actor_id,
utterance, profile}` → `SemanticFrameDTO{…, applied_cxn_ids}`.

---

## 3. Architecture & data flow

```
player posts in the NPC's Matrix room
 └─ runtime Matrix adapter (matrix-nio, logged in as @bonfires-<npc>) receives the event
      should_respond(is_dm, is_reply_to_npc, is_mention)?  →  build PipelineInput:
        { agent_id=NPC-KG-UUID, bonfire_id="mm-world-v1", actor_id=<player>, text,
          persona=<NPC prompt>, platform=matrix }
      ▼  DSPyAgentBackend.process → _process_with_correlation:
   bridge_context_var.set(BridgeContext(loop, bonfire_id, agent_id, corr,
                          graph_memory=<client>, cxn_gateway=<client>, cxn=CxnToolCtx{base_url, bearer}))  ← JWT wire
   ── comprehend→activate step (NEW; only if a cxn skill is enabled) ──
     frame = await graph_memory.comprehend(bonfire_id, text, profile=agent_id, actor_id)
     await cxn_gateway.push_activation(agent_id, frame.applied_cxn_ids, bearer)
   ───────────────────────────────────────────────────────────
   understand(LLM) → retrieve(light/off for NPCs) → act: dspy.ReAct over the `memento` toolset:
       mm_get_state / mm_search_world / mm_move / mm_attack / mm_take / mm_bolt / mm_act
         each sync tool: read BridgeContext → _run_async(ctx.cxn_gateway.call_tool(
                          tool, args, bearer=ctx.cxn.bearer)) → POST gateway /v1/tools/{tool}
                          (label + ACTIVATION gated by the push above) → never raise
   respond → Matrix adapter posts the reply to the room as @bonfires-<npc>
```

**Speech via the adapter; actions via the tools.** The NPC's spoken reply is posted to the Matrix
room by the adapter; its game actions go through the **cxn tools** (gateway-gated by the NPC JWT +
the per-turn activation). Memory is **tool-driven** (`mm_get_state`), so the `retrieve` stage is
**light/off** for memento NPCs.

---

## 4. Components

### 4.1 Matrix client adapter — `adapters/matrix/` *(new; the bulk of the slice)*
matrix-nio `AsyncClient`. Mirrors the telegram adapter file-for-file:
- `client.py` — login/restore (`@bonfires-<npc>` creds from config, §6), `sync_forever`, room
  membership, send-message.
- `handler.py` — on a room text event: compute `should_respond` (DM / reply-to-NPC / mention),
  build `PipelineInput`, `await backend.process`, post the reply (and ignore own messages).
- `policy.py` — `should_respond(is_dm, is_reply_to_npc, is_mention)` (port telegram's).
- `formatting.py` — markdown→Matrix HTML (`org.matrix.custom.html`).
The adapter consumes the SAME `DSPyAgentBackend`/`manager` as telegram — no pipeline change for
transport. It is wired in `lifespan`/`bootstrap` for agents whose `DeploymentConfiguration.platform
== "matrix"`.

### 4.2 `CxnGatewayClient` — `adapters/cxn_gateway/client.py` *(new, general)*
Async httpx client to **any service exposing the unlock-loop contract**, constructed from a
`base_url` (+ optional auth config). NOT memento-specific — the mmori gateway is one configured
instance. Two methods:
- `async call_tool(*, tool, args, bearer, bonfire_id) -> str` — `POST {base_url}/v1/tools/{tool}`
  with `Authorization: Bearer <bearer>`, returns the tool result rendered for the LLM (JSON →
  string); maps 403 `activation_required`/`capability_missing` + 4xx/5xx to a concise error string
  (the tool wrapper never raises).
- `async push_activation(*, agent_id, cxn_ids, bearer) -> set[str]` —
  `POST {base_url}/v1/agents/{agent_id}/activation {cxn_ids}`, returns the `unlocked` set; never
  raises (logs + returns empty on failure).

### 4.3 JWT wire — `CxnToolCtx` + a local signer
- `adapters/memento/jwt.py`: `sign_npc_jwt(sub: str, *, secret: str, ttl_seconds: int) -> str` —
  HS256 via PyJWT, claims `{sub, type:"npc", iat, exp}` (mirrors the gateway's `engine_auth.sign_jwt`).
- Extend `BridgeContext` with **two** fields: `cxn_gateway: CxnGatewayClient | None = None`
  (the long-lived async client, like `graph_memory`) and `cxn: CxnToolCtx | None = None`
  where `CxnToolCtx{base_url: str, bearer: str}` (frozen, per-turn). The backend builds the bearer
  once per turn (cache per-agent acceptable) and sets both in `bridge_context_var.set(...)`. cxn
  tools call `ctx.cxn_gateway.call_tool(..., bearer=ctx.cxn.bearer, bonfire_id=ctx.bonfire_id)`.
  Config: `JWT_SECRET`, and per-gateway `base_url` (mmori = `MEMENTO_GATEWAY_URL`). *(Multi-gateway
  per agent — a `dict[name, …]` — is a trivial deferred extension; the slice wires one.)*

### 4.4 cxn-tool factory + memento manifest — `modules/tools/builtin/cxn_tools.py` *(new, general)*
A `CxnToolManifest` declares a toolset: a skill name + `CxnToolSpec{name, params}` entries (param
names + types, so each generated wrapper has a proper typed signature for DSPy). `build_cxn_tools(
manifest) -> list[ToolDefinition]` generates one sync ReAct wrapper per spec — each a clone of the
`graph_memory_tools` shape: read `BridgeContext`, `_run_async(ctx.cxn_gateway.call_tool(tool=<name>,
args={…bound params…}, bearer=ctx.cxn.bearer, bonfire_id=ctx.bonfire_id), ctx.loop)`, return the
string, never raise. The `CxnGatewayClient` is the long-lived instance on `BridgeContext.cxn_gateway`
(§4.3).
The **memento manifest** (static config, `adapters/cxn_gateway/manifests/memento.py`) declares skill
`"memento"` + specs for `mm_get_state(entity_name)`, `mm_search_world(query)`, `mm_move(destination)`,
`mm_attack(patient, instrument=None)`, `mm_take(patient)`, `mm_bolt(patient)`, `mm_act(text)`. Another
service supplies its own manifest the same way — no new runtime code.

### 4.5 The comprehend→activate step — in `backend.py` *(new)*
A small async method on `DSPyAgentBackend`, called in `_process_with_correlation` AFTER
`bridge_context_var.set(...)` and BEFORE the threaded `act` stage, **gated** on the memento toolset
(see §4.6). It: (1) `frame = await self._graph_memory.comprehend(bonfire_id, text, profile=agent_id,
actor_id)`; (2) `await self._cxn_gateway.push_activation(agent_id, frame.applied_cxn_ids, bearer)`.
**Never blocks the turn:** comprehend/activation failures are logged and the turn proceeds (tools
needing activation then 403 → surfaced as a tool error string the LLM can react to). Add
`GraphMemoryClient.comprehend(*, bonfire_id, utterance, profile, actor_id) -> SemanticFrame` (httpx
`POST /v1/bonfires/{id}/kernel/comprehend`, `_headers(permission="read")`).

### 4.6 skill group → toolset selection (manifest-driven)
`filter_by_skills` filters by tool **name**, so a single skill name won't select a set. Each
`CxnToolManifest` carries its skill name + tool names, so a **skill-group expansion** maps an
`enabled_skills` entry (e.g. `"memento"`) → that manifest's tool names before `filter_by_skills`.
Registration is config-driven: for each `cxn_gateways` entry the bootstrap builds a
`CxnGatewayClient(base_url)` + `build_cxn_tools(manifest)` and registers them under the manifest's
skill. The same `manifest.skill in enabled_skills` predicate (a) selects the toolset and (b) gates
the §4.5 comprehend→activate step (so a non-cxn agent skips it entirely).

### 4.7 One seeded NPC + grammar + `cxn_gateways` config
- `AgentConfig` for the NPC: `agent_name`, `agent_username="bonfires-<npc>"`, `enabled_skills=["memento"]`,
  persona = the existing mmori `NPC_SYSTEM_PROMPT_TEMPLATE` output; a general
  `cxn_gateways: list[CxnGatewayConfig{name, base_url, skill}]` (the slice has one: the mmori
  gateway, skill `"memento"`); `DeploymentConfiguration` extended with matrix fields
  (`platform="matrix"`, `matrix_homeserver`, `matrix_user_id`, `matrix_access_token`).
- Grammar seed **script** (`scripts/seed_npc_grammar.py`, mmori or runtime): calls the kernel
  `author_grammar` route (graph-memory) for `profile=NPC-UUID` with the ATTACK/MOVE/TAKE/BOLT
  constructions (reuse the M2 `seed_game_grammar` construction specs). Run once before the NPC goes
  live so `comprehend(profile=NPC-UUID)` activates.

---

## 5. Error handling

- **Tools never raise** — the generated cxn tools return concise error strings (gateway 403 →
  `"action unavailable: <marker>"`, timeout → `"the world did not respond"`), so the LLM reasons
  about failure and can clarify or retry. Mirrors `graph_memory_tools`.
- **comprehend/activation best-effort** — failures log + proceed; the turn still runs (degrades to
  "no cards activated" → mutation tools 403 until a valid activation lands).
- **Matrix adapter** — ignore own messages and non-text events; on `backend.process` failure, post a
  short apology (mirrors telegram's error reply); never crash the sync loop.
- **JWT** — minted per turn from `JWT_SECRET`; a missing secret fails fast at bootstrap (config
  validation), not per-turn.

---

## 6. NPC identity & credentials

- **Matrix:** the mmori gateway's `matrix_bridge.py` already provisions/login `@bonfires-<npc>`
  accounts on the homeserver. For the slice, the NPC's `{homeserver, user_id, access_token}` are
  supplied to the runtime via the NPC's `AgentConfig.DeploymentConfiguration` (matrix fields). The
  runtime adapter logs in / restores that session (matrix-nio). Provisioning new accounts at scale
  is a follow-up (the gateway already owns it).
- **Gateway JWT:** `sub = NPC KG UUID` (same id used as `agent_id`/`profile`), so the activation
  push (`sub==agent_id`) and the tool-call identity line up across kernel comprehend, gateway gate,
  and executor `caller_id`. Single id space end-to-end.

---

## 7. Testing

- **`CxnGatewayClient`** (httpx mock / ASGITransport against a stub): `call_tool` posts to
  `/v1/tools/{tool}` with the bearer and renders the result; 403 `activation_required` → error
  string; `push_activation` posts cxn_ids and returns `unlocked`; both never raise on transport error.
- **`build_cxn_tools` + memento manifest** (BridgeContext set in a ContextVar, `CxnGatewayClient`
  mocked): each generated tool reads the ctx, calls `call_tool` with the right `tool`/`args`, returns
  the string, never raises when the client errors; `build_cxn_tools` yields one `ToolDefinition` per
  manifest spec with the right name/signature.
- **JWT signer**: round-trips with the gateway's validation contract (`sub`/`type`/`exp`); a token
  minted here is accepted by the gateway's `validate_jwt` (cross-checked against `engine_auth`).
- **Skill-group expansion**: `enabled_skills=["memento"]` → a registry containing exactly
  the memento manifest's tool names; non-cxn agents exclude them and skip the comprehend step.
- **comprehend→activate step**: `graph_memory.comprehend` + `cxn_gateway.push_activation` mocked
  — the step calls comprehend with `profile=agent_id`, pushes the returned `applied_cxn_ids`, and
  swallows failures (turn proceeds).
- **Matrix adapter**: `should_respond` policy table (DM/reply/mention) mirrors telegram; `handler`
  builds the `PipelineInput` and posts the reply (matrix-nio mocked); own-message + non-text ignored.
- **Integration (the headline proof, Rule-16-style)** via `POST /v1/chat` (no Matrix needed) against
  a running card-model gateway + kernel-seeded NPC grammar: a turn with `text="attack the goblin
  with the iron sword"` → comprehend activates `mm.attack.v1` → activation push → ReAct calls
  `mm_attack` via the REST facade → goblin HP drops → a response is produced. A second turn with no
  attackable target → clarify. Proves runtime↔kernel↔gateway end-to-end.

---

## 8. Definition of done (the slice)

One NPC, configured for Matrix, with a pre-seeded kernel grammar, runs on the bonfires-core
agent-runtime: it receives a player line (Matrix and/or `/v1/chat`), comprehends via its own
grammar, pushes activation to the gateway, acts through the gateway card-tool REST facade
(JWT'd, activation-gated), and replies. The headline `/v1/chat` integration test is green; the unit
suites (client, tools, JWT, skill-group, comprehend step, Matrix policy/handler) are green; the
runtime's existing telegram/graph-memory paths are unaffected (additive). Implementation lands in
`bonfires-ai-core/services/agent-runtime` on a branch off `origin/agent-service`.

---

## 9. Repo, workspace & PR plan

- **Workspace prerequisite:** the runtime only exists on `origin/agent-service` (not `main`/`staging`).
  Implementation needs a working branch off `agent-service` checked out in `bonfires-ai-core`
  (`git worktree` or checkout). The plan's tasks assume that branch is live.
- **Gates:** the agent-runtime uses the bonfires-ai-core toolchain (pyright strict, ruff,
  lint-imports, check-boundaries) — same constraints as graph-memory: services raise domain
  exceptions; keep parenthesized `except (A, B):`; format only touched files.
- **PR:** branch `agent-runtime/memento-npc` → `agent-service` (or `staging` once `agent-service`
  lands). Cross-repo: the spec/plan docs live in `memento-mori` (with the integration line); the
  code lands in `bonfires-ai-core`.

---

## 10. Forward map

- **Multi-NPC spawning** — a spawner that creates `AgentConfig`s + seeds grammars + provisions
  Matrix accounts, targeting the runtime's agents API (replacing the Bonfires SDK glue).
- **Spawn-time grammar authoring** — author each NPC's grammar on creation (incremental
  `author_grammar`), and the kernel **identity-DAG** so race/class traits are truly unspoken.
- **The other agent types** — room narrator, engine referee, master narrator — same bridge, each
  with its own grammar/skill set.
- **Retire the Matrix wake / bonfires-ai dependency** for mmori once coverage is complete; fold in
  the lean-core extraction.
