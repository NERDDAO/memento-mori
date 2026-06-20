# graph-memory Contract & Decommission Inventory

Filled by Tasks 6 / Track C+E.

> **Status:** placeholder — Track C contract section to be added above this line.

---

## Decommission inventory (tools/kg.py)

> **Purpose.** A new dev must be able to answer two questions at a glance: (1) which `tools/kg.py` call-sites are already superseded by the cxn skeleton, and (2) which ones are still live and must not be deleted. This section answers both.

### Background

`engine/src/memento/tools/kg.py` wraps the Bonfires SDK's `client.kg.*` methods as CrewAI tools consumed by crew files, and exposes the private helper `_resolve_entity_uuid` for inline imports. The cxn layer (spec §2 / §4) replaces these for three actions — MOVE, ATTACK, TAKE — by routing their state writes through `StateRepository` (MongoDB) and `MemoryClient` (graph-memory kernel) instead of the Delve HTTP API. For every other action category the old crews and their `tools/kg.py` imports remain the live path.

**Note on `client.kg.*` direct callers.** Many engine modules (`heartbeat.py`, `epoch.py`, `flows/`, `round_controller.py`, `agent_controller.py`, `world_reaction.py`, `session.py`, `seed.py`, `turn_controller.py`, `inventory_actions.py`, `inventory_manifest.py`, `room_manifest.py`, `matrix_listener.py`) call `client.kg.*` directly via the Bonfires SDK — they do **not** import `tools/kg.py`. They are catalogued in §2 below and are all **fallback-for-rest** (the cxn skeleton does not touch them).

---

### 1. tools/kg.py — importer call-sites

These are files that contain `from memento.tools.kg import …` or `from memento.tools.kg import _resolve_entity_uuid`.

| File | Line | Function(s) imported | Label | Notes |
|---|---|---|---|---|
| `engine/src/memento/crews/combat/attack/crew.py` | 5 | `search_world` | **replaced-for-3-actions** | `AttackResolutionCrew` — named in spec §9.1 as eliminated for ATTACK |
| `engine/src/memento/crews/combat/assessment/crew.py` | 6 | `search_world`, `get_entity` | **replaced-for-3-actions** | `CombatAssessmentCrew` — named in spec §9.1 as eliminated for ATTACK |
| `engine/src/memento/crews/combat/consequence/crew.py` | 5 | `update_entity`, `create_edge` | **replaced-for-3-actions** | `ConsequenceCrew` — named in spec §9.1 as eliminated for ATTACK |
| `engine/src/memento/crews/combat/permadeath/crew.py` | 5 | `search_world`, `mark_status`, `create_edge`, `remember_event`, `pin_entity` | **replaced-for-3-actions** | Permadeath outcome for ATTACK; death flag moves to `set_attr` + `chain_kill` primitive |
| `engine/src/memento/crews/event_detection/inventory/crew.py` | 5 | `search_world` | **replaced-for-3-actions** | `InventoryDetectorCrew` — named in spec §9.1 as eliminated for TAKE |
| `engine/src/memento/crews/narrative/memory/crew.py` | 5 | `remember_event` | **replaced-for-3-actions** | `MemoryConsolidationCrew` / `EpisodicMemoryFlow` — named in spec §9.1; episode persistence moves to `ingest_episode` primitive via `MemoryClient` |
| `engine/src/memento/tools/movement.py` | 175, 182 | `client.kg.get_entity`, `client.kg.update_entity` (direct SDK, not kg.py import) | **replaced-for-3-actions** | `mm_move` NPC position update in KG; the cxn `CXN.MOVE` `move_entity` primitive owns position writes. *These are direct `client.kg.*` calls, not kg.py imports — listed here for completeness.* |
| `engine/src/memento/crews/context/crew.py` | 6 | `search_world`, `get_entity`, `get_neighbors` | **fallback-for-rest** | `ContextCrew` — spec §9.2: still used on non-cxn turns; spec §9.1 eliminates it only for MOVE/ATTACK/TAKE when UUID args make world-context retrieval unnecessary |
| `engine/src/memento/crews/narrative/narration/crew.py` | 6 | `search_world` | **fallback-for-rest** | `NarrationCrew` / `mm_narrate` — spec §9.2 explicitly left alone; post-state, non-blocking |
| `engine/src/memento/crews/event_detection/quest/crew.py` | 5 | `search_world` | **fallback-for-rest** | `QuestDetectorCrew` — spec §9.2 explicitly left alone |
| `engine/src/memento/crews/event_detection/world_change/crew.py` | 5 | `search_world` | **fallback-for-rest** | `WorldChangeDetectorCrew` — spec §9.2 explicitly left alone |
| `engine/src/memento/crews/quest/design/crew.py` | 5 | `search_world`, `create_entity` | **fallback-for-rest** | Quest design crew — spec §9.2 quest/faction left alone |
| `engine/src/memento/crews/faction/generation/crew.py` | 5 | `search_world`, `create_entity`, `create_edge` | **fallback-for-rest** | Faction generation crew — spec §9.2 left alone |
| `engine/src/memento/crews/faction/reputation/crew.py` | 6 | `update_entity` | **fallback-for-rest** | `ReputationCrew` — spec §9.2 explicitly left alone |
| `engine/src/memento/crews/world_gen/location/crew.py` | 5 | `search_world`, `create_entity`, `create_edge` | **fallback-for-rest** | World-gen crew — spec §9.2: generation crews left alone |
| `engine/src/memento/crews/world_gen/region_design/crew.py` | 5 | `search_world`, `create_entity` | **fallback-for-rest** | World-gen crew — spec §9.2 left alone |
| `engine/src/memento/crews/world_gen/exit_connection/crew.py` | 5 | `create_edge`, `search_world` | **fallback-for-rest** | World-gen crew — spec §9.2 left alone |
| `engine/src/memento/crews/item_gen/concept/crew.py` | 5 | `search_world` | **fallback-for-rest** | Item-gen crew — spec §9.2 left alone |
| `engine/src/memento/crews/npc_gen/concept/crew.py` | 5 | `search_world` | **fallback-for-rest** | NPC-gen crew — spec §9.2 left alone |
| `engine/src/memento/crews/npc_gen/planning/crew.py` | 5 | `search_world` | **fallback-for-rest** | NPC-gen crew — spec §9.2 left alone |
| `engine/src/memento/crews/npc_gen/finalization/crew.py` | 5 | `create_entity`, `create_edge` | **fallback-for-rest** | NPC-gen crew — spec §9.2 left alone |
| `engine/src/memento/tools/state.py` | 30, 52 | `client.kg.search`, `client.kg.get_edges` (direct SDK, not kg.py import) | **fallback-for-rest** | `get_entity_state` — NPC state inspection tool; spec §9.2 left alone. *Direct SDK calls, not kg.py imports.* |
| `engine/src/memento/tools/movement.py` | 56, 64 | `client.kg.get_entity`, `client.kg.get_edges` (direct SDK) | **fallback-for-rest** | `move_within_room` — NPC within-room spatial helper; not the same path as CXN.MOVE. *Direct SDK calls.* |
| `engine/src/memento/agent_controller.py` | 352 | `_resolve_entity_uuid` (inline import) | **fallback-for-rest** | UUID fallback when caller provides no location UUID; agent-spawning path, unchanged |
| `engine/src/memento/matrix_listener.py` | 200 | `_resolve_entity_uuid` (inline import) | **fallback-for-rest** | Resolves location name→UUID for Matrix-sourced player turns; unchanged |
| `engine/src/memento/session.py` | 384 | `_resolve_entity_uuid` (inline import) | **fallback-for-rest** | Death marking fallback UUID resolution; player session management, unchanged |
| `engine/src/memento/spike/crew.py` | 5 | `create_entity`, `search_world` | **fallback-for-rest** | Spike / scratch file — not in any production path |

---

### 2. Direct client.kg.* callers (not via tools/kg.py)

These modules call the Bonfires SDK `client.kg.*` API directly. They were not routed through `tools/kg.py` and are **all fallback-for-rest** — the cxn skeleton does not touch them. They are catalogued here so nothing is confused with the crew-level importer list above.

| Module | Call count | Representative calls | Label |
|---|---|---|---|
| `engine/src/memento/heartbeat.py` | 4 | `kg.get_stack_status`, `kg.process_stack`, `kg.wait_for_job`, `kg.get_latest_episode` | **fallback-for-rest** |
| `engine/src/memento/epoch.py` | 2 | `kg.search` (entity type sweeps) | **fallback-for-rest** |
| `engine/src/memento/flows/npc_gen.py` | 1 | `kg.update_entity` | **fallback-for-rest** |
| `engine/src/memento/flows/enrichment.py` | 5 | `kg.get_entity`, `kg.update_entity` | **fallback-for-rest** |
| `engine/src/memento/flows/art_gen.py` | 1 | `kg.update_entity` | **fallback-for-rest** |
| `engine/src/memento/flows/world_gen.py` | 1 | `kg.update_entity` | **fallback-for-rest** |
| `engine/src/memento/round_controller.py` | 6 | `kg.get_edges`, `kg.get_entity`, `kg.update_entity`, `kg.create_entity`, `kg.create_edge` | **fallback-for-rest** |
| `engine/src/memento/agent_controller.py` | 3 | `kg.create_entity` (narrator/engine entity seeding) | **fallback-for-rest** |
| `engine/src/memento/world_reaction.py` | 8 | `kg.search`, `kg.create_entity`, `kg.create_edge`, `kg.update_entity` | **fallback-for-rest** |
| `engine/src/memento/turn_controller.py` | 3 | `kg.get_latest_episode`, `kg.get_entity_or_none`, `kg.get_entity`, `kg.update_entity` | **fallback-for-rest** |
| `engine/src/memento/inventory_actions.py` | ~20 | `kg.get_entity`, `kg.update_entity`, `kg.create_entity`, `kg.create_edge`, `kg.get_edges`, `kg.update_edge` | **fallback-for-rest** |
| `engine/src/memento/inventory_manifest.py` | 5 | `kg.get_edges`, `kg.get_entity`, `kg.create_edge`, `kg.update_edge` | **fallback-for-rest** |
| `engine/src/memento/session.py` | ~20 | `kg.create_entity`, `kg.create_edge`, `kg.search`, `kg.get_edges`, `kg.get_entity` | **fallback-for-rest** |
| `engine/src/memento/seed.py` | 8 | `kg.get_entity`, `kg.search`, `kg.create_entity`, `kg.create_edge`, `kg.update_entity` | **fallback-for-rest** |
| `engine/src/memento/room_manifest.py` | 3 | `kg.get_entity`, `kg.get_edges` | **fallback-for-rest** |
| `engine/src/memento/matrix_listener.py` | 1 | `kg.search` (location list) | **fallback-for-rest** |

---

### 3. Delve / Bonfires-KG archival status

**Finding (from spec and repo):** The Bonfires "KG" stack — Graphiti-on-Neo4j fronted by the Delve HTTP API, exposed to the engine via the Bonfires Python SDK (`client.kg.*`) — is documented as **being archived** by the construction system spec.

Spec §1.1 states explicitly:

> "That stack is being **archived**. Keeping it would mean maintaining a Graphiti fork, a Neo4j instance, the Delve FastAPI process, the Bonfires Python SDK, and roughly 30 call-sites…"

Spec §9.1 identifies the Day-1 scope: the 30 `tools/kg.py` Delve call-sites are "eliminated for the three skeleton actions." Spec §9.2 explicitly notes that "all other Delve call-sites (quest/faction/lore/codex)" are left alone as fallback — meaning the Delve service must remain running for non-MOVE/ATTACK/TAKE turns until every action category is covered by a construction.

**Cannot confirm a hard shutdown date or a merged "archived" branch from the repo alone.** The spec names the archival intent but the Delve service itself lives outside this repo (`delve/` in the parent workspace). The sentence "That stack is being archived" reflects the roadmap direction, not a completed decommission. Track C (graph-memory contract section above this line) will document the live graph-memory kernel endpoints that partially replace Delve's memory role.

---

### 4. Safe-to-delete checklist

Do **not** delete `tools/kg.py` or any of the crew files above until:

- [ ] Every action category listed in §9.2 has been covered by a cxn construction **or** a written decision to drop it.
- [ ] The `RoundController` / `TurnController` legacy paths have been removed or gated off.
- [ ] All `session.py`, `inventory_actions.py`, `inventory_manifest.py`, `seed.py`, `world_reaction.py`, and `room_manifest.py` direct `client.kg.*` calls have migrated to `StateRepository` or `MemoryClient`.
- [ ] The Bonfires SDK dependency (`bonfires` / `client.kg`) has been removed from `engine/pyproject.toml`.

Until all four boxes are checked, `tools/kg.py` is load-bearing for non-cxn turns.
