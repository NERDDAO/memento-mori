# Memento-Mori — Start Here (cxn control system)

## What this is

Memento-mori is a permadeath MUD engine. This branch (`cxn/control-system-spec`) is
building the **construction-based control system** — a deterministic, effectful
control layer that replaces the legacy CrewAI crew pipeline for three core actions:
MOVE, ATTACK, and TAKE. A *construction* is a form→meaning→effect triple: an agent
calls it as an MCP tool with UUID arguments, the `EffectExecutor` runs a typed effect
template deterministically (zero LLM calls per action on Day 1), and state is written
to MongoDB through the `StateRepository` port. The legacy `RoundController` and its
crew chains stay in place as an unchanged fallback; they become the low-confidence fork
only at Milestone 2, when the `TurnRouter` and `kernel/comprehend` land. Everything
built here is additive.

---

## 30-second setup check

```bash
cd engine
pip install -e '.[dev]'
pytest --collect-only          # should find tests without errors
pytest -q                      # all green
```

Expected output: `235 passed` (or more as the skeleton grows). If collection fails,
check that you are in `engine/` and that `pip install -e '.[dev]'` completed cleanly.

---

## Legibility map

| Document | What it contains |
|---|---|
| [Spec §1–9](superpowers/specs/2026-06-19-mm-construction-control-system-design.md) | Full architecture — the 3 substrates, 3 constructions, EffectExecutor, state primitives, MCP tool registration, Day-1 vs Milestone-2 cut line, test strategy |
| [Reuse inventory](cxn/reuse-inventory.md) | Every existing symbol the cxn system reuses, with verified `file:line` signatures. Read before touching `chain.py`, `tool_labels.py`, `mcp_server.py`, or `state_update.py`. |
| [Thread sheet](cxn/thread-sheet.md) | Which dev owns which component (C1–C6), work-in-progress status, merge order. Start here if you want to know what to pick up. |
| [GM contract](cxn/gm-contract.md) | The observable contract between the engine and a Game Master / agent: MCP tool signatures, `StateUpdate` shape, error prefixes, and the narration-is-async guarantee. |

The reuse inventory links back to this page. Thread sheet and GM contract are filled
in as later tasks complete — they are placeholder stubs right now; the links are live.

---

## Which thread is mine?

See the **[thread sheet](cxn/thread-sheet.md)**. Each thread maps to one of the five
Day-1 components (C1 `StateRepository`, C2 `MemoryClient`, C3 `Constructicon`,
C4 `EffectExecutor`, C6 `McpToolBridge`). Pick the thread that matches your
component and confirm with the thread sheet before writing any code — the components
are designed to be parallel and independently stubable from Day-1 morning, but the
shared DTO module (`engine/src/memento/cxn/types.py`) must land first.

For architecture questions: spec §8.1 (component boundaries) and §2.2 (agent loop).
For Day-1 done criteria: spec §8.5.
