# Memento-Mori Construction-Card Model (Design)

> Spec for the **construction-card** layer of the mmori construction-control system: the cxn
> as a Magic-card-like object that bundles its own activation pattern, cost, effect, and type
> into one declarative thing — composable with other cxns, enforced at the gateway. This is the
> "Gateway + unlock loop" subsystem of the agent-runtime integration
> (`2026-06-20-mmori-agent-runtime-integration-design.md` §4.1 + §9), reframed around the card
> as the core primitive.

## 1. Goal & premise

Make the construction (`cxn`) a **card**: a named, declarative, composable object that fully
specifies a state change — like *Lightning Bolt* (`R`; deal 3 damage; instant). The card *is*
the rules text; nothing about the transition is hidden in handler code. A card bundles:

- **Activation** (form pole) — how it fires: a vernacular pattern the kernel grammar
  comprehends, and/or a game trigger.
- **Cost** — what is checked and paid *before* the effect (HP, an item, a resource).
- **Effect** — the deterministic state mutation(s), declared as data and interpreted by the
  executor (not hard-coded).
- **Type** — one-shot (`action`/`instant`) vs persistent (`permanent`, schema-only this slice).

Cards **compose**: a trait card (`DWARF`) contributes a modifier to how an action card (`MOVE`)
resolves. Effect parameters are `literal` or `derived` from a **resolution context** that
co-active trait cards populate. This is MTG static/continuous abilities, FCG co-activation, and
ECS components — the same idea in three vocabularies.

The agent will eventually **build** cards by composing sub-cxns; this slice delivers the card
**runtime + a seed set** so authoring has a proven substrate to target.

### 1.1 Locked decisions

1. **Per-turn activation set** unlocks structured tools — deterministic, no forgeable creds; KG
   labels stay the outer ring.
2. **Runtime pushes activation** — the runtime's understand-stage comprehension (the incoming
   utterance) POSTs `applied_cxn_ids` to the gateway; that set is which cards are *castable* this
   turn. ("Player input unlocks tool usage.")
3. **Card = `CxnDef` extended**, not a parallel type — `CxnDef` already declares effects as data
   (`effect_template: list[StatePrimitive]`); we add `construct_id`, `card_type`, `cost`,
   `unlocks`, and the composition fields `trigger`/`state_condition`/`modifiers` (all
   `NotRequired`). Additive and backward-compatible.
4. **Executor stays the deterministic authority** — it gains a cost phase and a `deal_damage`
   op *alongside* the existing effect interpretation; the 349-test Day-1 effect path is not
   rewritten.
5. **Trait composition: schema + one proof** — the model fully expresses trait/modifier cards;
   the runtime seeds two modifier cards — one `identity` trait and one `state` status — that
   share a single resolution pass. General multi-trait layer ordering is deferred.

### 1.2 Cut line

**In:** the `CardDef` schema; the cost/effect op vocabulary; the resolution context + two seeded
modifier cards (one `identity`, one `state`); the play-a-card lifecycle (comprehend → activate →
pay cost → resolve effect); the
gateway activation store + push endpoint + `_check_tool_access` extension; the
`POST /v1/tools/{tool}` REST facade; a 6-card seed set; tests.

**Out (forward map, §11):** agent-authoring of new cards; persistent `permanent` cards that
*hold* state (`guild-bank`); shared/multi-profile cards (`the-guild`); general multi-trait layer
stacking; a movement-range mechanic.

---

## 2. Background: what already exists (verified)

- **`CxnDef`** (`engine/src/memento/cxn/types.py:42`) — TypedDict with `name`, `predicate`,
  `mcp_tool_name`, `description`, `semantic_roles`, `restrictions`, `guards`, `chain_mirror`,
  **`effect_template: list[StatePrimitive]`**, `episode_template`. The effect is *already
  declarative data*.
- **`StatePrimitive`** (`types.py:6`) — `substrate` (`transactional`/`memory`/`chain`), `op`
  (Literal incl. `move_entity`, `transfer_item`, …), `args`, `if_condition`. The executor
  interprets these.
- **`CONSTRUCTION_REGISTRY`** (`definitions.py:186`) — `MOVE_CXN`/`ATTACK_CXN`/`TAKE_CXN`.
- **`EffectExecutor.execute(...)`** (`executor.py:174`) — phases: resolve/validate →
  `_phase1_5_transients` (computes `damage`/`computed_hp` via `arithmetic.damage` +
  `arithmetic.clamp_hp`) → `_phase2_transactional` → `_apply_transactional` (`move_entity`,
  `transfer_item`) → `_phase3_memory_and_chain`. Returns `StateUpdate`. All-or-nothing with
  compensation. **Derived effect params already work** (ATTACK damage).
- **Gateway gating** — `_check_tool_access(tool)` (`mcp_server.py:46`) → `_current_identity`
  (JWT `sub`, set by `_BearerAuthMiddleware`) → `check_tool_access(entity_id, tool)`
  (`engine_auth.py:115`) → KG labels → `get_allowed_tools`. `INNATE_TOOLS` bypass. Stable error
  markers `capability_missing:` / `identity_missing:`.
- **`mm_act`** (`cxn_tools.py register_mm_act`) — free-text path: `TurnRouter.handle(text,
  actor_id)` → `ComprehensionClient` → kernel comprehend route (now returns `applied_cxn_ids`).
- **Kernel prereqs (PR'd)** — `author_grammar` route (seed a per-agent grammar) and
  `comprehend(profile)` exposing `applied_cxn_ids`. The activation pattern of a card becomes
  language-castable by authoring it into the world/agent grammar via that route.

---

## 3. The `CardDef` schema

`CardDef` extends `CxnDef` with four additive fields (added as `NotRequired` so the existing
three definitions stay valid; a `normalize_card()` fills defaults). One registry, one type.

```python
# engine/src/memento/cxn/types.py  (additions)

CardType = Literal["action", "instant", "permanent"]   # permanent = schema-only this slice

class CostOp(TypedDict):
    kind: Literal["pay_hp", "consume_item", "pay_resource"]
    args: dict[str, Any]      # pay_hp:{amount}; consume_item:{role|item_kind}; pay_resource:{pool,amount}

class Modifier(TypedDict):
    modifies: str             # param key, e.g. "damage" | "move_distance"
    op: Literal["set", "add", "mul"]
    value: float
    applies_to: list[str]     # predicates/card names this modifies, e.g. ["move"] | ["attack"]

# How a card becomes active:
#   lexical  — fires on a spoken vernacular pattern (action cards)
#   identity — always co-active for the agent; the CHARACTER BUILDER seeds these
#              (race=DWARF, class=WIZARD) into the per-agent grammar (unspoken, §5)
#   state    — active WHILE a state condition holds; CURRENT STATE imposes these
#              (low HP → BLOODIED, poisoned → POISONED)
Trigger = Literal["lexical", "identity", "state"]

class StateCondition(TypedDict):     # for trigger == "state"
    field: str                       # entity field/attr, e.g. "hp"
    cmp: Literal["lt", "lte", "gt", "gte", "eq", "has_label"]
    value: Any                       # threshold or label

class CxnDef(TypedDict):       # EXISTING fields unchanged; NotRequired additions:
    # ... name, predicate, mcp_tool_name, description, semantic_roles, restrictions,
    #     guards, chain_mirror, effect_template, episode_template ...
    construct_id: NotRequired[str]        # kernel↔mmori JOIN KEY, e.g. "mm.move.v1"
    card_type: NotRequired[CardType]      # default "action"
    trigger: NotRequired[Trigger]         # default "lexical"
    state_condition: NotRequired[StateCondition]  # required iff trigger == "state"
    cost: NotRequired[list[CostOp]]       # default []  (zero-cost)
    unlocks: NotRequired[list[str]]       # tool bundle; default [mcp_tool_name]
    modifiers: NotRequired[list[Modifier]] # trait/status cards contribute these; default []
```

- **`construct_id`** is the stable id the kernel emits in `applied_cxn_ids` and the key the
  activation store / unlock map use. It is the single join between the grammar layer and the
  control/state layer.
- **`unlocks`** is the tool **bundle** a card grants (one-to-many): activating a card makes every
  tool in its `unlocks` castable. Defaults to the card's own `mcp_tool_name`.
- **`effect_template`** (existing) is the declarative effect. Effect-op params may be **literal**
  or **derived** (see §4).
- **`modifiers`** turns a card into a **trait/modifier card**: it contributes continuous
  modifiers to the resolution context instead of (or in addition to) a one-shot effect.

### 3.1 Lightning Bolt, as a card

```python
LIGHTNING_BOLT_CXN: CxnDef = {
    "name": "LIGHTNING_BOLT", "predicate": "bolt", "construct_id": "mm.lightning_bolt.v1",
    "mcp_tool_name": "mm_bolt", "card_type": "instant",
    "description": "Hurl a bolt of lightning at a target (patient UUID).",
    "semantic_roles": ["agent", "patient"],
    "cost": [{"kind": "consume_item", "args": {"item_kind": "spark_reagent"}}],
    "effect_template": [{"substrate": "transactional", "op": "deal_damage",
                         "args": {"target": "patient", "amount": 3}, "if_condition": None}],
    "unlocks": ["mm_bolt"], "modifiers": [],
    # restrictions/guards/chain_mirror/episode_template per the existing shape
}
```

A literal `amount: 3`, an explicit cost, `instant` type — the card declares the whole state
change. It proves the schema generalizes beyond the three hard-wired verbs.

---

## 4. Effect & cost ops (the deterministic interpreter)

### 4.1 Effect ops — reuse + one addition

The effect is `effect_template: list[StatePrimitive]`, interpreted by the executor exactly as
today (`move_entity`, `transfer_item`, …). One op is **added**: `deal_damage` —
`args:{target: <role>, amount: <literal | "derived">}`. When `amount` is a literal the executor
applies `clamp_hp(current, amount)`; when `"derived"`, it reads the computed value from the
resolution context (§5). ATTACK keeps its existing `_phase1_5_transients` damage derivation; the
new op simply exposes the same `clamp_hp` write path to a declared amount. **No existing effect
op is changed.**

### 4.2 Effect-op params: literal or derived

A param value is either a literal or `{"derived": "<key>"}`. `derived` reads `<key>` from the
**resolution context** transients (e.g. `damage`, `move_distance`). This already exists for
ATTACK (damage is derived); the schema makes it explicit and available to new cards.

### 4.3 Cost ops — a new pre-effect phase

`cost: list[CostOp]` is checked **and paid** in a new **Phase 0** inside `EffectExecutor.execute`,
*inside the same all-or-nothing transaction* as the effect (a failed effect rolls the cost back
via the existing compensation path). Slice op kinds, all over **existing state**:

- `pay_hp{amount}` — agent loses `amount` HP (clamped; fails if it would drop ≤ 0 unless the
  card allows self-KO).
- `consume_item{role|item_kind}` — remove one matching item from the agent's inventory; fail
  `cost_unpayable:no_item` if absent.
- `pay_resource{pool, amount}` — decrement `agent.attrs.resources[pool]` (a generic pool, empty
  today; **forward-compatible with mana-like resources**, not required for the slice).

Cost failure raises `ConstructionError("cost_unpayable:<reason>")` — no state change escapes
(consistent with the existing guard-failure contract).

---

## 5. Trait cards & the resolution context — unspoken, per-agent

Not every card is a one-shot. A **trait card** (`DWARF`, `STRONG`) is a persistent characteristic
whose `modifiers` contribute to a **resolution context** that action cards read when they resolve.

**Traits are unspoken cxns the agent's own grammar supplies.** When a dwarf says *"I move,"* the
surface text names only `MOVE`, but the **"I" carries the speaker's identity** — `DWARF` hangs off
the self-form in *that agent's grammar* (the identity DAG, §5.1). So comprehending **any**
first-person utterance by that agent co-activates its trait cxns automatically; the dwarf never
has to say "as a dwarf." This is the direct payoff of the per-agent grammar
(`profile=agent_id`): each agent's grammar **is** its trait set — the dwarf's grammar holds
`DWARF`, a human's does not — so trait membership is per-agent by construction, with no global
trait table.

**One channel.** Because identity traits co-activate during comprehension, they ride the **same
`applied_cxn_ids`** as the spoken action cxn. "I move" by a dwarf → `applied_cxn_ids =
[mm.move.v1, mm.trait.dwarf.v1]`. Trait-activation and action-activation are unified: both arrive
through comprehension → the activation set.

**Two sources of modifier cxns.** A modifier card becomes active in one of two ways (its
`trigger`):
- **`identity` (from the character builder).** Race/class cxns (`DWARF`, `WIZARD`) are defined at
  character creation and seeded into the agent's per-agent grammar; they are unspoken and always
  co-active (arrive via `applied_cxn_ids`).
- **`state` (imposed by current state).** Status-effect cxns (`BLOODIED` at low HP, `POISONED`)
  are active **while their `state_condition` holds**. The executor evaluates each `state`-trigger
  card's condition against the loaded agent doc at resolve time and folds active ones in. No
  comprehension or push needed — current state imposes them.

Both sources contribute `modifiers` to the **resolution context**, resolved against the union of
the active-set construct_ids (action + identity traits) and the state-satisfied status cards —
**not** from a bespoke KG-label read:

```
resolve(action_card, active_construct_ids, agent_doc):
  ctx.transients[param] = base(param)
  identity_and_action = [card(tid) for tid in active_construct_ids]
  status = [c for c in cards(trigger="state") if holds(c.state_condition, agent_doc)]
  for c in identity_and_action + status:
      for m in c.modifiers if action.predicate in m.applies_to:
          ctx.transients[m.modifies] = apply(m.op, ctx.transients[m.modifies], m.value)
  # action effect-op `derived` params now read ctx.transients
```

- **Proof (this slice) — one resolution pass, both sources.** Seed two modifier cards that share
  the single resolution pass (the only marginal cost of the second is a trivial condition check):
  - `STRONG` (`trigger:"identity"`, `modifies:"damage", op:"add", value:2, applies_to:["attack"]`)
    — with `mm.trait.strong.v1` in the active set, ATTACK deals `base + 2`.
  - `BLOODIED` (`trigger:"state"`, `state_condition:{field:"hp", cmp:"lte", value:3}`,
    `modifies:"damage", op:"add", value:2, applies_to:["attack"]`) — active *only* while the
    agent's HP ≤ 3; the executor folds it in from current state, no push.
  Reuses the existing `transients["damage"]` path. Proves cxn composition from **both** the
  identity/active-set path and the state-condition path.
- The `DWARF → MOVE distance` case is the same shape against a `move_distance` param; **deferred**
  only because it needs a movement-range mechanic (MOVE is adjacent-room binary today). Schema
  supports it; the proof uses the param that already derives (damage).
- **Deferred:** multi-trait layer ordering (MTG layers: set → add → mul with dependency). The
  slice applies modifiers in a single deterministic pass (sorted by `op` then source
  `construct_id`) and documents that ordering as provisional.

### 5.1 The identity DAG (kernel mechanism, decoupled)

Identity cxns aren't a flat "always-on" set — they hang off the **self-form**. **"I" is a cxn
whose meaning pole links to the agent's identity cxns** (`DWARF`, `FIGHTER`), which are the
**basis**; further cxns (learned traits, status, agent-authored cards) **attach** to them. The
result is a **DAG rooted at the "I" hub** that holds the agent's **compressed state**: structure
is shared (common sub-cxns are shared nodes), so the whole identity + capability set is held as a
graph, not an enumerated list. Comprehending any first-person utterance enters at the "I" root and
**propagates** down the DAG — you get "all the context" (race, class, attached cards) without
flatly re-activating everything. So `applied_cxn_ids` for "I move" by a dwarf-fighter is the
propagation closure `[mm.move.v1, mm.trait.dwarf.v1, mm.class.fighter.v1, …attached…]`.

This is the **same categorial-network co-activation M2 already uses** (the anchorless
argument-structure cxn fires via `add_link`), extended: link the self-form to the identity cxns,
and identity cxns to their attachments. The kernel dependency is therefore an **extension of an
existing mechanism**, not a new always-on subsystem — and it's where per-agent grammars pay off:
each agent's DAG is seeded into its own `profile` grammar via the `author_grammar` route, and the
DAG *is* the agent's accreting state (ties to entrenchment-as-propagation-weight).

**Concrete shape.** The **character builder defines the `I`-binding** — the identity bundle on
the self-form — so any first-person utterance from that agent comprehends with `I` expanded to
its identity cxns:

```
character builder:   I ↦ {DWARF, FIGHTER}     # seeded into the agent's profile grammar
comprehend("I attack the goblin with the iron sword", profile = dwarf-fighter):
   →  I(DWARF, FIGHTER)   attack   (the goblin)   [with the iron sword]
        agent   = ⟨uuid, identity:{dwarf, fighter}⟩      # role arrives pre-enriched
        predicate = attack ;  patient = goblin ;  instrument = iron_sword     # {misc}
   applied_cxn_ids = [mm.attack.v1, mm.trait.dwarf.v1, mm.class.fighter.v1]
```

The agent role is **pre-enriched** with the identity bundle; the executor reads those identity
construct_ids' `modifiers` into the resolution context. The shape is uniform —
`I(<identity>) {verb} {target} {misc}` — so a `MOVE`/`TAKE`/authored verb composes with the same
identity DAG with no special-casing.

**Decoupling holds.** This spec's gateway/executor half is provable **now** regardless of how the
DAG activates: it treats every modifier uniformly as a `construct_id` in the active set. The
slice's tests place `mm.trait.strong.v1` into the activation set directly (standing in for the
DAG having propagated it). When the kernel lands the self-form → identity-DAG propagation, the
unspoken path works end-to-end with **no change** to the executor or gateway — the identity
construct_ids simply start arriving in `applied_cxn_ids` on their own.

---

## 6. The play-a-card lifecycle

Two entry modes, one resolution core.

**Free-text play (`mm_act`)** — comprehend-and-play, atomic:
```
mm_act(text) → TurnRouter comprehends → matches a card's activation pattern (construct_id)
  → executor.execute(card, agent, bindings):  Phase 0 pay cost → resolve effect (+modifiers)
  → StateUpdate
```
`mm_act` is *not* gated on the activation set — it activates inline. (It remains ungated as the
comprehend path; cost still applies.) The `applied_cxn_ids` from this comprehension — the spoken
action cxn **plus the agent's unspoken trait cxns** (§5) — form the active set the executor uses
to resolve modifiers.

**Structured play (`mm_move` / `mm_attack` / `mm_take` / `mm_bolt`)** — the runtime pushed the
turn's activation:
```
runtime understand: comprehend(profile=agent) → applied_cxn_ids
  → POST /v1/agents/{agent}/activation {cxn_ids}   (records which cards are castable this turn)
  → mm_attack(patient_uuid) via REST facade or /mcp:
       _check_tool_access:  identity → KG label (outer) → activation gate (inner)
       executor.execute(...):  Phase 0 pay cost → resolve effect (+modifiers) → StateUpdate
```

The **activation gate**: a cxn-gated tool is castable iff some live `construct_id` in the
caller's activation set has the tool in its `unlocks` bundle (union over the set). Read tools and
`mm_act` are **not** cxn-gated.

---

## 7. Gateway enforcement & REST facade

### 7.1 `ActivationStore` (new) — `gateway/src/gateway/activation_store.py`
In-process, module-level (mirrors `npc_registry`), keyed by agent identity (JWT `sub`):
`dict[str, dict[construct_id, expiry_epoch]]`. API: `record(agent_id, cxn_ids, ttl)` (REPLACES
the agent's set), `active(agent_id) -> set[str]` (drops expired), `clear(agent_id)`. TTL default
~120 s. Single-process only; multi-worker sharing is **out of scope** (flagged).

### 7.2 Activation push endpoint (new) — `POST /v1/agents/{agent_id}/activation`
JWT-gated; `sub` **must equal** path `agent_id` (else `403 identity_mismatch` — an agent
activates only itself). Body `{cxn_ids: list[str], ttl_seconds?: int}`. Records the set; returns
`{"unlocked": [tool_names]}` (the union of `unlocks` over the recorded, map-resolved cxn-ids).
Unknown cxn-ids are recorded but contribute nothing to `unlocked`.

### 7.3 `construct_id → unlocks` resolution
Derived from `CONSTRUCTION_REGISTRY` (`card["unlocks"]`, default `[mcp_tool_name]`) — single-
sourced on the card, **not** a hand-kept side dict. A small `unlock_index()` builds
`construct_id → set[tool]` once.

### 7.4 `_check_tool_access` extension (`mcp_server.py`)
After the existing KG-label check passes, for **cxn-gated tools** (the mutation set:
`mm_move`/`mm_attack`/`mm_take`/`mm_bolt`) require the tool to be in the union of `unlocks` over
`ActivationStore.active(entity_id)`; else raise the new stable marker `activation_required:`
(MCP `RuntimeError` prefix; REST `403` JSON with `"error":"activation_required"`). Order:
identity → `capability_missing` (label) → `activation_required` (activation). Read tools and
`mm_act` are exempt.

### 7.5 REST facade (new) — `POST /v1/tools/{tool_name}`
Second transport over the **same** handlers. The handler core for each tool is **extracted into
a shared async callable**; both the `@mcp.tool` wrapper and the REST route call it, behind the
same `_BearerAuthMiddleware` + `_check_tool_access`. No construction logic is duplicated. Body =
the tool's JSON args; response = the same dict the MCP tool returns. Unknown tool → `404`;
gating failures → `403` with the stable marker.

---

## 8. Components & files

**Engine (`engine/src/memento/cxn/`):**
- `types.py` — add `CardType`, `CostOp`, `Modifier`; extend `CxnDef` with `NotRequired`
  `construct_id`/`card_type`/`cost`/`unlocks`/`modifiers`; `normalize_card()` default-filler.
- `definitions.py` — add the new fields to `MOVE`/`ATTACK`/`TAKE` (`construct_id`
  `mm.move.v1`/`mm.attack.v1`/`mm.take.v1`, `card_type:"action"`, `cost:[]`); add
  `LIGHTNING_BOLT_CXN` (`mm.lightning_bolt.v1`), an `identity` trait `STRONG`
  (`mm.trait.strong.v1`), and a `state` status `BLOODIED`
  (`mm.status.bloodied.v1`, `state_condition hp ≤ 3`); register all in `CONSTRUCTION_REGISTRY`.
- `executor.py` — Phase 0 cost check/pay (in the all-or-nothing tx + compensation); resolution
  context built from active-set construct_ids **plus** `state`-trigger cards whose
  `state_condition` holds against the loaded agent doc; `deal_damage` effect op; literal-or-derived
  param resolution. Existing effect ops untouched.

**Gateway (`gateway/src/gateway/`):**
- `activation_store.py` (new) — `ActivationStore`.
- `routes/activation.py` (new) — the push endpoint.
- `routes/tools.py` (new) — the REST facade over shared handler cores.
- `mcp_server.py` — extract handler cores into shared callables; `unlock_index()`; extend
  `_check_tool_access` with the activation gate + `activation_required:` marker.
- `cxn_tools.py` — handlers play cards (cost flows through the executor); construct_id carried
  on the `MatchedCxn`/play call.

---

## 9. Error contract (stable markers)

- `identity_missing:` — no JWT (existing).
- `capability_missing:` — caller lacks the KG label for the tool (existing; outer gate).
- `activation_required:` — labeled but the card isn't in the caller's per-turn activation set
  (new; inner gate).
- `cost_unpayable:<reason>` — cost cannot be paid (new; raised as `ConstructionError`, no state
  change).
- `identity_mismatch` — activation push `sub` ≠ path `agent_id` (new; `403`).

Both transports surface the same marker so the runtime's `memento_tools` can string-match the
failure and route to clarify/retry.

---

## 10. Testing

- **Schema/normalize:** `normalize_card` fills defaults; existing three defs validate; new fields
  round-trip.
- **Cost (executor):** `pay_hp`/`consume_item` succeed and mutate; insufficient → `cost_unpayable`
  with **no** state change (compensation verified); cost rolls back when the effect fails.
- **`deal_damage` op:** literal `amount:3` applies `clamp_hp`; derived amount reads the context.
- **Trait composition (identity):** agent with `STRONG` in the active set deals `base+2` on
  ATTACK; without it, base. `applies_to` filtering respected (no effect on MOVE/TAKE).
- **Status composition (state):** `BLOODIED` modifies ATTACK damage **only** while `hp ≤ 3`;
  above the threshold it contributes nothing — proves the `state_condition` is evaluated against
  current state, not pushed. Both modifiers stack additively in the single resolution pass.
- **`ActivationStore`:** record replaces; `active` drops expired; TTL honored.
- **Activation endpoint:** `sub`-match required (mismatch → 403); replace semantics; `unlocked`
  bundle = union of `unlocks`; unknown cxn-ids ignored in `unlocked`.
- **`_check_tool_access` matrix:** labeled+activated → pass; labeled+unactivated →
  `activation_required`; unlabeled → `capability_missing` regardless of activation; read tool /
  `mm_act` → ungated.
- **REST↔MCP parity:** `mm_attack` (mutation) and `mm_get_state` (read) return the same shape and
  gate identically across both transports.
- **End-to-end loop:** `POST /activation {mm.attack.v1}` → `POST /v1/tools/mm_attack {patient}`
  succeeds (hp drops, death on lethal); same call *without* activation → `403
  activation_required`. Lightning Bolt: with the reagent → deals 3 + consumes reagent; without →
  `cost_unpayable`.
- **Rule-16 where feasible:** the end-to-end loop runs against the real executor + real state
  repository; a fake JWT caller stands in for the runtime.

---

## 11. Definition of done (the slice)

`CardDef` schema + cost/effect interpreter + resolution context with one trait proof + the play
lifecycle + gateway activation store/endpoint/gate + REST facade, with the 6-card seed set
(`MOVE`/`ATTACK`/`TAKE`/`LIGHTNING_BOLT`/`STRONG`/`BLOODIED`) and the full test set green. The
deterministic
loop is demonstrable end-to-end: comprehended/pushed activation unlocks a structured tool, cost
is paid, the effect (with trait modifiers) resolves, and an unactivated or unaffordable play is
rejected with a stable marker. The Day-1 executor's existing effect path and the 349 engine tests
remain green.

---

## 12. Forward map

- **Character builder → per-agent grammar** — character creation/onboarding seeds the agent's
  `identity` cxns (race/class) into its grammar (`profile=agent_id`) via the `author_grammar`
  route, so they become unspoken always-co-active traits. Needs the kernel's speaker-anchored
  identity-cxn co-activation (§5.1). Richer status-effect library (`POISONED`, `BLESSED`,
  encumbrance) follows the same `state`-trigger shape.
- **Agent-authoring of cards** — incremental `author_grammar` that *adds* a card (its activation
  pattern emerges from conversation vernacular) to an agent's grammar; the agent builds cards
  from sub-cxns at runtime.
- **`permanent` cards that hold state** — `guild-bank` as a persistent card holding assets; the
  `construct_id` is the join key between the grammar layer and a state object. (`card_type`
  already reserves `permanent`.)
- **Shared / multi-profile cards** — `the-guild` as a shared grammar layer members' comprehension
  composes with; needs kernel composable/multi-profile comprehension. Agreeing = sharing a card.
- **General modifier layering** — MTG-style layer ordering (set → add → mul, dependency
  resolution) and a movement-range mechanic so `DWARF → MOVE-distance` resolves literally.
- **Runtime side** — `memento_tools` builtins + NPC JWT mint + Matrix client adapter +
  per-agent grammar seeding (the next spec; this gateway surface is its target).
- **Multi-worker activation store** — shared backing if the gateway scales beyond one process.
- **Entrenchment** — cards strengthen/decay with use (entrenchment-as-propagation-weight from the
  kernel-native HyperMem design); distinct NPC card-pools/voices emerge.
