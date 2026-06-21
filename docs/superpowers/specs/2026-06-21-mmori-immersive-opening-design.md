# Memento Mori — Immersive Opening & The Self-Agent Loop

**Status:** Design (brainstormed 2026-06-21)
**Author:** brainstormed with the user
**Supersedes/builds on:** `2026-06-20-mmori-construction-card-model-design.md`, `2026-06-19-mm-construction-control-system-design.md`, `2026-06-20-mmori-agent-runtime-integration-design.md`. Operationalizes the identity-DAG that the card model left as a decoupled dependency.

---

## 1. Problem & Goal

A player who knows only the name "Memento Mori" arrives with zero context. The opening must land three beats — in this order — without a manual or a tutorial pop-up:

1. **Permadeath** — make the stakes real and *felt*.
2. **Controls** — teach how to act, diegetically.
3. **A goal** — give them something to achieve, and let them achieve it.

…starting from one authored **seed room** (specific items, specific objective), with the world generating onward from there.

The deeper opportunity: the engine is a **construction grammar** (comprehend → activate → unlock tools → deterministic effect). Today the UI shows none of that soul — it renders prose and a damage number in a log, and the pretext canvas is underleveraged. This design makes the *experience* immersive while keeping the engine invisible, and in doing so resolves a missing primitive: **there is no self-agent.** The player currently types into a void. We give the player a self.

**Non-goal:** exposing the cxn engine to the player. The engine stays invisible; what the player feels is immersion.

---

## 2. The Spine — the inverted, grammar-bounded loop

The engine stops being *a thing the agent calls* and becomes **a kit of tools the grammar unlocks**. The construction grammar *is* the action space: an agent can only ever do what the player's comprehended language activates.

```
player free text
   → comprehend (profile = the acting agent's grammar)        [kernel]
   → activates construction(s): mm.look / mm.take / mm.attack / mm.move …
   → those constructions UNLOCK exactly their bounded tools    [gateway gate]
   → the agent acts ONLY through the unlocked tools            [voice + judgment]
   → engine commits canon deterministically                   [authority]
   → pretext renders the accretion
```

Three roles, cleanly separated:

- **Grammar = the boundary.** What you *say*, comprehended, determines which tools exist this turn. Nothing that comprehends → no tool unlocks (the diegetic "you don't know how to do that"). The action space is the construction set, not "anything an LLM might invent." This is the safety rail that keeps an agentic game on rails.
- **Agent = the voice + judgment** inside those bounds. It calls unlocked tools, supplies prose, and *proposes* candidate detail. It cannot reach for a tool the grammar didn't unlock.
- **Engine = the canon.** Owns room state, runs deterministic effects (damage, take, move), decides what becomes real on intent (lazy materialization). The LLM never holds authoritative state.

This is the unlock loop already shipped (memento-mori #2 gateway + bonfires-ai-core #121/#122/#123), repurposed as the game's core control surface.

### 2.1 The self ("I") is the master agency gate

Two levels of grammar-gating, not one:

- **Verb-constructions gate actions:** `mm.attack` unlocks the attack tool.
- **The self-construction gates agency itself:** an agent's **"I"** must be active for *any* of its tools to unlock. "I" is the root of the identity DAG (race/class/state bundle, per the card model) and is now also the agent's **on-switch**. No active "I" → no agency.

This makes the player a **first-class agent, symmetric with every NPC.** The only asymmetry is where the "I" gets its intent:

```
PLAYER self-agent:   "I"  ← driven by human inner-dialogue (the chat box)
NPC self-agent:      "I"  ← driven by an LLM
```

The chat box is the character's **interiority**; the self-agent is its **embodiment**. The human supplies the inner voice; the agent acts it out into the world through grammar-bounded tools. *Who is the player in the world?* — an agent whose "I" you author live, one thought at a time.

### 2.2 The name is the external handle to a self

The identity DAG rooted at "I" carries a **name binding**, bidirectional:

- **From inside:** "I" → my self → my tools unlock. (My POV; for the player, always-on while it is my turn.)
- **From outside:** my **name** ("Bob") is how another self references my "I". When "Bob" is comprehended inside another agent's utterance, the scene resolves the token → the agent whose `I.name == "Bob"` → **pushes activation to that agent's profile** → its "I" lights up → its tools unlock → it takes a grammar-bounded **reactive turn**.

### 2.3 The player turn is two comprehension steps

The chat box is the human **directing their own agent**, not speaking into the world. The agent is what speaks into the world:

```
human chat (inner direction, spoken TO my agent)
   → my self-agent comprehends it as intent             [interiority]
   → my "I" is active → it UTTERS an in-world line + acts through unlocked tools   [embodiment]
   → that utterance names "Bob"  → comprehended in the scene → Bob's "I" activates
   → Bob reacts: comprehends the event → utters + acts → may name others → bounded cascade
```

The **utterance is the universal message**; the **name is the address.** Every agent — player or NPC — runs the identical cycle: *comprehend what is addressed to me → my "I" gates my tools → I utter + act → my utterance addresses the next agent.* A scene is a message-passing graph of selves; utterances are the edges; names are the routing; grammar bounds what each self can do on its turn.

**Reaction trigger (decided):** **named or targeted only.** An agent reacts only when it is a participant in a comprehended frame — explicitly named ("Bob, run") or bound as a role (attack the goblin → goblin is patient). Bystanders stay dormant until referenced. The trigger is the *acting agent's uttered output*, not the human's raw input: type "warn the dwarf," the agent utters "Bob, behind you!", and *that* triggers Bob.

**Mediation is deliberate.** Because the self-agent interprets inner dialogue, it may phrase or target things differently than the human would literally. That mediation is the point ("acts it out"). It is a tunable dial; the V1 default is **faithful-but-embodying** (says what you meant, in-character). The dial itself is deferred.

---

## 3. The seed room and the three beats

The seed is **sparse and salience-weighted** — load-bearing facts, not a built room:

```
ROOM: the deep roads (seed)
  facts (high→low salience):
    • a dying adventurer — just cut down, bleeding out      [salience: forced-first]
    • the thing that killed them — still here, in the dark   [salience: high]
    • an iron blade — fallen from their hand                 [salience: medium]
    • a gate — the only way on                               [salience: medium]
  exits: { on → (ungenerated) }
```

The beats are not scripted — they are what accretion in salience order produces:

- **Beat 1 · Permadeath (witnessed).** The dying adventurer is `forced-first` salience, so the first `look` (or the room's unprompted opening describe) surfaces them *dying in front of you*. The engine marks them dead; they **do not come back**: no respawn, the corpse persists as canon. The player learns permadeath by watching it spend someone before they have risked anything.
- **Beat 2 · Controls (diegetic).** The teaching surface is the prose itself. The dying words are phrased as a sayable verb — *"take… the blade…"* → the player echoes `take the blade`, comprehension fires `mm.take`, it works. The agent paints affordances using exactly the verbs the grammar knows. Lazy promotion makes improvisation feel alive: `search the body`, `light the torch` work as long as the verb comprehends — training the real lesson, "say what you mean, not a memorized command."
- **Beat 3 · Goal.** As accretion continues, the gate and the threat-between-you-and-it surface. The goal condenses with no quest-giver: *get out alive.* The win-condition is a deterministic engine predicate — **player crosses the `on` exit** — and crossing it is the **generation handoff** that builds the next room.

The engine adds one thin **director**: it owns the seed's salience ordering (so death lands first) and watches the win-predicate (so the handoff fires). It does *not* script dialogue or outcomes.

### 3.1 Lazy canon (decided)

Prose flows freely and cheaply. The moment the player tries to ACT on a described-but-unseeded thing (`take the torch`), the engine **materializes** it into a real, persistent entity on demand. Attention + intent drive what becomes canon. "Take the torch" is what *makes* the torch exist. Materialization dedups against the candidate detail the narrator already floated, so "the torch" you take *is* the torch it described.

---

## 4. Systems

Tags: **[REUSE]** as-is · **[EXTEND]** add to it · **[NEW]** build it. The load-bearing infrastructure is already shipped; this design is mostly new verbs and new wiring on an existing spine.

| # | System | Status | Seam |
|---|--------|--------|------|
| 1 | **Comprehension + grammar boundary** | [REUSE] kernel `comprehend_utterance`/`author_grammar`/comprehend route + runtime `_comprehend_and_activate`; **[EXTEND]** author a LOOK/EXAMINE construction into the room grammar alongside MOVE/ATTACK/TAKE | `build_attack_grammar` → `build_room_grammar` with the look cxn |
| 2 | **Tool kit (the inverted engine)** | [REUSE] gateway `activation_store`/`_check_tool_access`/`routes/tools.py`/`build_cxn_tools`/`CxnGatewayClient`; **[EXTEND]** add `mm_look` to `MEMENTO_MANIFEST` + `_UNLOCK_INDEX` (`mm.look.v1 → mm_look`) | manifest entry + unlock-index row |
| 3 | **Seed-room state + authoring format** | [REUSE] `StateRepository`/`InMemoryStateRepository`/entity model; **[NEW]** sparse seed schema (facts + salience + exits) + loader | `engine/.../seed/room_seed.py` + loader writing to StateRepository |
| 4 | **Description / narration (the voice)** | [NEW] stateless `describe` tool (structured state in → prose out, floats non-canon candidate detail); [REUSE] agent-runtime / room-narrator as the calling agent | unlocked `mm_look` handler → describe; narrator owns voice |
| 5 | **Lazy materialization (canon minting)** | [EXTEND] `EntityResolver` gains promote-on-miss; **[NEW]** promoter invents entity (id, name, bounded attribute schema), dedups vs narrator candidates, writes canon, verb proceeds | `EntityResolver.resolve` promote branch → StateRepository write |
| 6 | **Director (beat orchestration)** | [NEW] thin — owns seed salience ordering, watches win-predicate, fires handoff; no dialogue/outcome scripting | per-room director object the TurnRouter consults |
| 7 | **Permadeath canon** | [REUSE] NPC death path (`chain.record_death`/death-episode, mark dead, no respawn, corpse persists). **Player run-wipe deferred** | existing death path, flagged no-respawn |
| 8 | **Generation handoff** | [NEW] stubbable — on exit-cross, generate next room from exit context (reuse seed format + one LLM pass), or stub to one authored second room; procgen later | director win-handler → room generator → new seed → loader |
| 9 | **Client rendering (pretext payoff)** | [REUSE] unified canvas/narrative typewriter/present/map/cards; **[EXTEND]** render accretion + inner/embodiment split + card lighting/death-darkening | reuse `state_update.room_map` + present; possibly one new "materialized" WS event |
| 10 | **Self ("I") construction + name binding** | [NEW] operationalizes the identity DAG: each agent's "I" gates its toolkit and carries a `name`; promotes the card model's deferred dependency to a built thing | extend `author_grammar` to seed an `I` cxn keyed to the agent's name; gate unlock-index on active-"I" |
| 11 | **Name → self resolution + activation fan-out** | [EXTEND] `_comprehend_and_activate` generalized from one profile to *self + referenced selves*: a named/referenced agent's profile gets activated | comprehension surfaces a name role → director resolves → `push_activation(profile=that agent)` |
| 12 | **Scene turn orchestration (reaction cascade)** | [NEW] thin — director runs referenced agents' reactive turns in order with a **depth cap** so cascades terminate | director owns the turn queue |
| 13 | **Player self-agent (inner dialogue)** | [NEW] human-intent backend: chat → comprehend as *direction* → self-agent emits an in-world utterance + tool actions (gated by active player-"I"); utterance re-enters scene as the trigger. Mechanically identical to an NPC turn; only the intent source differs | `InnerDialogueBackend` variant of `DSPyAgentBackend` |

**Shape of the work:** ~6 NEW units (seed format+loader, describe tool, promoter, director, room generator stub, inner-dialogue backend) + the self-"I"/name systems; ~4 EXTENSIONS (look construction, manifest/unlock row, resolver promote-branch, fan-out, client accretion). Everything authoritative — comprehension, gateway gate, executor, state — is reuse.

---

## 5. Rendering (pretext)

Rule: **render the immersion, never the mechanism.** No "construction activated" badges; the engine stays invisible. Mapping onto the existing panels:

- **Narrative panel** (typewriter) → the **woven turn-stream**, with the signature **inner-dialogue / embodiment split**:
  - your chat → **dim, italic** — *thought* (what you told your agent)
  - your agent's uttered line + action → **bright, in-character** — *embodiment*
  - other selves' reactions → **their role color**

  One typographic distinction communicates the entire self-agent model with zero chrome.
- **Cards panel = the selves.** A card is **lit** (bright border) when that self's "I" is active (its turn); dormant selves **dimmed**. When the witnessed adventurer dies, their card **goes dark / becomes a corpse-card** — permadeath rendered, not narrated. Reuses the box-drawing card renderer as-is.
- **Character panel = your self.** The sidebar "I" — your identity made visible.
- **Present + map = accretion.** Show only what has been *surfaced*; entities **appear** as they lazy-materialize; the map **fills in** as you look. The room condenses into being; typewriter pacing sells it.
- **Viewer panel** (currently empty) holds the **focused entity** when you examine something — the blade, the body, the gate.
- **Input** reframed as inner voice — the prompt is a thought (`…`), not a command line.

---

## 6. Scope — Vertical 1

The thinnest slice that proves **every novel keystone once**, in one seed room.

**In V1:**
- One seed room (sparse, salience-weighted) + loader
- **Player self-agent** (inner-dialogue backend) — the direct→utter→act two-step
- **One reactive NPC self** (the threat, or a companion) — proves name→self activation at **cascade depth 1**
- `look` → describe tool → **lazy-canon materialization** (with dedup against narrator candidates)
- The three beats: **witnessed death** (the adventurer, scripted-salience), **controls** (diegetic prose), **goal** (cross the `on` exit = win-predicate)
- Client: **accretion render + inner/embodiment typographic split + card lighting / death-darkening**
- Generation handoff **stubbed** (a "the road goes on…" close, or one second authored room)

**Deferred to V2+:**
- Full multi-agent cascade (depth > 1, many named reactors)
- Real **generation handoff → procgen** engine
- **Player permadeath run-wipe** (V1 only *witnesses* death)
- Perception/witness reactions (we chose named-or-targeted-only)
- Identity-DAG modifier richness (STRONG/BLOODIED beyond card-model minimum)
- The literalness dial

V1 is genuinely playable: a stranger arrives, looks, watches someone die, hears a name, speaks it, and is playing — with the self/agency model and look-to-build both proven, on top of the comprehension + gateway + executor spine already shipped.

---

## 7. Open questions (for the plan stage)

- **Profiles & repos across two repos.** The kernel/runtime live in `bonfires-ai-core`; the engine/gateway/seed/director live in `memento-mori`. V1 needs a clean account of which repo owns the seed loader, the director, and the inner-dialogue backend, and how the player-self profile is authored (it needs an "I" grammar too).
- **Where the describe LLM call lives.** Stateless tool in the engine vs. narrator agent in the runtime — Section 4 keeps state authoritative in the engine, but the prose call's home (and its model) needs pinning.
- **Materialization attribute schema.** The bounded attribute set the promoter may invent (takeable / weapon-power / lit / …) and its deterministic defaults.
- **Cascade termination.** The exact depth cap and the turn-queue ordering for depth-1 (player acts → one reactor) — trivial in V1 but the interface should generalize.
- **Client WS contract.** Whether accretion + materialization reuse `state_update`/`room_map`/present, or warrant one new "materialized" event; and how the inner/embodiment split is signalled (a `channel`/`kind` on the narrative message).
