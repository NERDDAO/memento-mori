# Persona State-Store Unification (#4-B-A)

## What Changed

`RoomDriver` (`gateway/src/gateway/room_driver.py`) now resolves each roster entity's `embodiment_agent_id` to its **KG UUID** via an injected `KgProjection` (the new `kg_uuid_for(engine_uuid)` accessor), with a fallback to the engine UUID when no projection is wired. This makes the roster key on the same identifier the execution gate (`engine_auth.check_tool_access`, which reads `client.kg.get_entity(JWT.sub)`) uses, so the two gates resolve the same KG entity.

The live cxn/MCP executor repo (`gateway/src/gateway/mcp_server.py`) is now built by `_build_cxn_repo()`: when `KERNEL_BASE_URL` + `GM_INTERNAL_TOKEN` are set it returns a KG-backed `EventSourcedStateRepository` (live `KgProjection`), so the executor reads/writes the same KG store the gate reads; otherwise it returns `InMemoryStateRepository` (local/test, unchanged from before).

`KgProjection` / `KgProjectionProtocol` / `KgProjectionFake` gained a read-only `kg_uuid_for(engine_uuid) -> str | None` accessor over the existing engine↔KG indirection map.

A keystone test (`engine/tests/state/test_gate_label_parity.py`) proves the comprehend-gate label source (`repo.get_labels` flowing through the real `KgProjection`) and the execution-gate label source (`kg.get_entity(kg_uuid)["labels"]`) read ONE store and move together: revoking a label (dropping the `NPC` kit) strictly shrinks the allowed-tool set on both sides identically.

## Why

Previously the comprehend-side and execution-side capability gates could read entity labels from different stores (the cxn executor used a standalone in-memory repo while the gate read the KG), and the roster shipped the engine UUID while the gate keyed on the KG UUID. They could silently disagree. This slice makes one KG store authoritative in the live path and keys both gates on the KG UUID.

## Base / Branch Note

This slice is built on `opening/engine-core` (the event-sourced-state trunk that contains `KgProjection`/`EventSourcedStateRepository`/`opening.py`), NOT on the persona-capabilities branch — those two arcs are disjoint descendants of `6f851f0` and are not yet integrated.

## Deferred (Not in This Slice)

- **Live `RoomDriver` wiring**: on this base there is no production `RoomDriver` construction site (the `/start` route builds a `TurnRouter`; `RoomDriver` is constructed only in tests). Passing the live projection into `RoomDriver` happens on the persona/GM-rooms lineage when the arcs merge.
- **Capabilities-field coexistence**: the #4-A `capabilities` field on the self-spec lives on the disjoint persona arc; merging the two arcs is future work.
- **Approach A** (engine UUID == KG UUID via an SDK `create_entity` that accepts a caller-supplied UUID), **Mongo-backed StateRepository**, and **gate-reads-through-the-repo** (single read path) remain out of scope.
