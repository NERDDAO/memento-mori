# Persona Arc Integration + Surfaced Executor Identifier Gap

## What Changed

The two disjoint arcs — `opening/engine-core` (#4-B-A state-store unification) and `persona/npc-capabilities` (#4-A label-gated capabilities) — are now unified on branch `persona/arc-integration` (off `opening/engine-core`, with `persona/npc-capabilities` merged in).

`RoomDriver._npc_self_spec` (`gateway/src/gateway/room_driver.py`) now carries BOTH fields from the two arcs: `capabilities` (populated by `get_allowed_tools(labels)` from the persona-capabilities arc) AND the KG-uuid `embodiment_agent_id` (populated via `_embodiment_id` → `projection.kg_uuid_for`, from the #4-B-A arc).

## Chain Proven at the Test Level

`gateway/tests/test_gm_room_loop_e2e.py::test_capability_chain_enforced_over_one_store` drives the full integrated chain:

**labels → roster `capabilities` + KG-uuid `embodiment_agent_id` → per-self JWT → real `check_tool_access` (un-stubbed) reading one shared label store → enforcement**

Run in **identity-uuid mode** (KG uuid == engine uuid): allowed `mm_move` → 200 with a real state change (`location_uuid == room_b_id`); revoke the NPC kit in that one store → `mm_move` → 403 `capability_missing`. Only `broadcast_tool_event` is stubbed; the gate genuinely reads the store.

## Surfaced Gap (Deferred)

The capability gate keys on the JWT `sub` (the KG uuid, post-#4-B-A) while `EffectExecutor` resolves the acting agent by the **engine** uuid — `KgProjection.get` returns `None` for anything outside its engine→KG key space. A genuinely *distinct* KG-uuid `sub` would therefore need a `kg_uuid→engine` resolution at the route/executor boundary that does not exist today.

This is deferred to the live-stack slice. Engine≠KG-uuid label parity itself stays covered by the `engine/tests/state/test_gate_label_parity.py` keystone.

## Deferred (Later Slices)

- **First production `RoomDriver` call site** + the scene-activation trigger that constructs and drives it live.
- **Multi-service live-stack e2e**: gateway + real `persona/service-revision` agent-runtime + KG, proving the full chain including real FCG authoring and a genuinely distinct KG uuid (with the `kg_uuid→engine` executor resolution).
- **#4-C** role→param binding (`SemanticFrame.roles` → deterministic tool args).
- **#4-B remaining**: Mongo-backed `StateRepository`, gate-reads-through-the-repo (single read path), opening-path repo unification, Approach A (engine uuid == KG uuid via SDK supplied-uuid).
