"""Keystone proof — both capability gates read ONE KG store.

This test verifies that the comprehend-gate label source
(``repo.get_labels(engine_uuid)`` flowing through
``EventSourcedStateRepository → KgProjection.get → _DictKg.get_entity_or_none``)
and the execution-gate label source
(``proj.kg_uuid_for(engine_uuid)`` → ``kg.get_entity_or_none(kg_uuid)["labels"]``
directly on the same store) are backed by ONE mutable dict.

A label mutation applied directly to the dict store must move both read paths
together — before AND after mutation the two sides agree.  This test exercises
the security-relevant REVOCATION direction: dropping the "NPC" kit label
strictly SHRINKS the allowed-tool set, and both gates lose the revoked
capability atomically.

Design of _DictKg
-----------------
``KgProjection.create`` calls ``kg.create_entity(name, labels, attributes, summary)``
synchronously (wrapped in ``asyncio.to_thread``); the return value is the
KG-assigned uuid.  ``KgProjection.get`` then calls
``kg.get_entity_or_none(kg_uuid)`` and expects a dict with at minimum:
  {"labels": [...], "attributes": {...}, "name": str, "uuid": str}
``_from_kg_entity`` (called by ``KgProjection.get``) reads ``entity.get("labels")``.

``_DictKg`` is a minimal synchronous stub that satisfies exactly those two
contract points.  It assigns its own KG uuid (``kg-<counter>``) at
``create_entity`` time, stores the full entity shape, and exposes the live
mutable dict via ``get_entity_or_none``.  ``get_entity`` is a thin alias used
by the execution-gate assertion (``kg.get_entity(kg_uuid)["labels"]``).

No other methods are implemented — ``KgProjection.create`` calls
``kg.create_edge`` for the LOCATED_IN edge only when ``doc["location_uuid"]``
is set; we supply a doc without a location to keep the double minimal.
"""

from __future__ import annotations

from typing import Any

import pytest

from memento.state.chain_mirror import NoopChainMirror
from memento.state.event_sourced import EventSourcedStateRepository
from memento.state.kg_projection import KgProjection
from memento.state.tx_log import InMemoryActivationLog, InMemoryTxLog
from memento.tools.tool_labels import get_allowed_tools

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

ENGINE_UUID = "engine-uuid-gate-proof-0001"
# Revocation proof: "Character" is NOT a kit, so get_allowed_tools(["Character"])
# == INNATE_TOOLS only.  Dropping the "NPC" kit label strictly REMOVES the
# NPC-kit tools (e.g. mm_attack) — a non-vacuous SHRINK of capabilities.
INITIAL_LABELS: list[str] = ["Character", "NPC"]
MUTATED_LABELS: list[str] = ["Character"]
# A tool granted ONLY by the NPC kit (not INNATE, not by "Character") — the
# concrete capability we prove is revoked from both gates after the label drop.
REVOKED_TOOL = "mm_attack"


# ---------------------------------------------------------------------------
# _DictKg — minimal synchronous KG double
#
# KgProjection.get calls (via asyncio.to_thread):
#   1. kg.get_entity_or_none(kg_uuid) → dict with {"labels", "attributes", "name", "uuid"}
# KgProjection.create calls (via asyncio.to_thread):
#   1. kg.create_entity(name, labels, attributes, summary) → kg_uuid str
#   2. kg.create_edge(...)   ← only if location_uuid is set; we omit it here
#
# The entity dict is stored by reference so a direct mutation to
# self._store[kg_uuid]["labels"] is immediately visible to both read paths.
# ---------------------------------------------------------------------------


class _DictKg:
    """Minimal synchronous KG double — only the methods KgProjection actually calls."""

    def __init__(self) -> None:
        # kg_uuid → entity dict (mutable, stored by reference)
        self._store: dict[str, dict[str, Any]] = {}
        self._counter = 0

    def _new_kg_uuid(self) -> str:
        self._counter += 1
        return f"kg-uuid-{self._counter:04d}"

    # Called by KgProjection.create (via asyncio.to_thread)
    def create_entity(
        self,
        name: str,
        labels: list[str],
        attributes: dict[str, Any],
        summary: str,
    ) -> str:
        kg_uuid = self._new_kg_uuid()
        self._store[kg_uuid] = {
            "uuid": kg_uuid,
            "name": name,
            "labels": list(labels),  # copy so KgProjection's list doesn't alias
            "attributes": dict(attributes),
            "summary": summary,
        }
        return kg_uuid

    # Called by KgProjection.get (via asyncio.to_thread)
    def get_entity_or_none(self, kg_uuid: str) -> dict[str, Any] | None:
        return self._store.get(kg_uuid)

    # Convenience alias used by the execution-gate assertion
    def get_entity(self, kg_uuid: str) -> dict[str, Any]:
        entity = self._store.get(kg_uuid)
        if entity is None:
            raise KeyError(f"entity not found: {kg_uuid!r}")
        return entity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_npc_doc() -> dict[str, Any]:
    """Minimal EntityDoc for an NPC with no location (avoids create_edge call)."""
    return {
        "uuid": ENGINE_UUID,
        "name": "Aldric the Merchant",
        "kind": "character",
        "labels": list(INITIAL_LABELS),
        "location_uuid": None,  # no location → no create_edge call needed
        "attrs": {"hp": 30, "max_hp": 30, "inventory": []},
        "is_dead": False,
    }


def _build_repo(kg: _DictKg) -> tuple[EventSourcedStateRepository, KgProjection]:
    """Wire up a real KgProjection wrapping the dict KG, and an EventSourcedStateRepository."""
    proj = KgProjection(kg=kg)
    repo = EventSourcedStateRepository(
        tx_log=InMemoryTxLog(),
        activation_log=InMemoryActivationLog(),
        projection=proj,
        chain=NoopChainMirror(),
    )
    return repo, proj


# ---------------------------------------------------------------------------
# Keystone proof
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_both_capability_gates_read_one_kg_store() -> None:
    """Comprehend-gate and execution-gate read the same KG dict.

    Proof structure
    ---------------
    1. seed_entity via the repo (writes to _DictKg via KgProjection.create)
    2. BEFORE mutation — assert both read paths return identical labels and
       identical get_allowed_tools() sets.
    3. Mutate labels directly in the backing _DictKg store (simulates a KG
       label update from outside the engine — e.g. a DM REVOKES an NPC's
       agency by dropping the "NPC" kit label).
    4. AFTER mutation — assert both read paths pick up the shrunken label set
       and again agree on get_allowed_tools(), and that the revoked tool is
       gone from BOTH gates.

    The comprehend-gate path is:
       repo.get_labels(engine_uuid)
         → EventSourcedStateRepository.get_labels
         → KgProjection.get(engine_uuid)
         → asyncio.to_thread(kg.get_entity_or_none, kg_uuid)
         → _from_kg_entity(entity, engine_uuid=engine_uuid)
         → doc["labels"]

    The execution-gate path is:
       proj.kg_uuid_for(engine_uuid) → kg_uuid
       kg.get_entity(kg_uuid)["labels"]
       (direct read on the same _DictKg._store)
    """
    kg = _DictKg()
    repo, proj = _build_repo(kg)

    # ── Step 1: seed entity ──────────────────────────────────────────────────
    await repo.seed_entity(_make_npc_doc())  # type: ignore[arg-type]

    # Confirm the KG uuid indirection map is populated
    kg_uuid = proj.kg_uuid_for(ENGINE_UUID)
    assert kg_uuid is not None, "kg_uuid_for must return a server uuid after create"

    # ── Step 2: BEFORE mutation — both gates must agree ──────────────────────
    comprehend_before = await repo.get_labels(ENGINE_UUID)
    exec_before = kg.get_entity(kg_uuid)["labels"]

    assert set(comprehend_before) == set(INITIAL_LABELS), (
        f"comprehend-gate before: expected {INITIAL_LABELS!r}, got {comprehend_before!r}"
    )
    assert set(exec_before) == set(INITIAL_LABELS), (
        f"execution-gate before: expected {INITIAL_LABELS!r}, got {exec_before!r}"
    )
    # The keystone claim — before mutation, both sides agree
    assert set(comprehend_before) == set(exec_before), (
        f"GATES DIVERGE before mutation: comprehend={comprehend_before!r} exec={exec_before!r}"
    )

    tools_before_comprehend = get_allowed_tools(comprehend_before)
    tools_before_exec = get_allowed_tools(exec_before)
    assert tools_before_comprehend == tools_before_exec, (
        "get_allowed_tools() diverges before mutation: "
        f"comprehend={tools_before_comprehend!r} exec={tools_before_exec!r}"
    )

    # ── Step 3: mutate the KG store (label change) ───────────────────────────
    # Directly update the mutable dict in the store — both read paths must see it.
    kg._store[kg_uuid]["labels"] = list(MUTATED_LABELS)

    # ── Step 4: AFTER mutation — both gates must agree on new labels ─────────
    comprehend_after = await repo.get_labels(ENGINE_UUID)
    exec_after = kg.get_entity(kg_uuid)["labels"]

    assert set(comprehend_after) == set(MUTATED_LABELS), (
        f"comprehend-gate after: expected {MUTATED_LABELS!r}, got {comprehend_after!r}"
    )
    assert set(exec_after) == set(MUTATED_LABELS), (
        f"execution-gate after: expected {MUTATED_LABELS!r}, got {exec_after!r}"
    )
    # The keystone claim — after mutation, both sides still agree
    assert set(comprehend_after) == set(exec_after), (
        f"GATES DIVERGE after mutation: comprehend={comprehend_after!r} exec={exec_after!r}"
    )

    tools_after_comprehend = get_allowed_tools(comprehend_after)
    tools_after_exec = get_allowed_tools(exec_after)
    assert tools_after_comprehend == tools_after_exec, (
        "get_allowed_tools() diverges after mutation: "
        f"comprehend={tools_after_comprehend!r} exec={tools_after_exec!r}"
    )

    # ── Step 5: the mutation must be visible (proof is non-vacuous) ──────────
    assert tools_before_comprehend != tools_after_comprehend, (
        "Mutation had no effect on get_allowed_tools — proof is vacuous. "
        f"before={tools_before_comprehend!r} after={tools_after_comprehend!r}"
    )
    # Revocation: capabilities only SHRANK — strict subset after the label drop.
    assert tools_after_comprehend < tools_before_comprehend, (
        "Dropping the NPC kit label must STRICTLY shrink the tool set. "
        f"before={tools_before_comprehend!r} after={tools_after_comprehend!r}"
    )
    # The concrete revoked capability: an NPC-kit-only tool, present before and
    # gone after — on the comprehend gate AND the execution gate.
    assert REVOKED_TOOL in tools_before_comprehend
    assert REVOKED_TOOL not in tools_after_comprehend
    assert REVOKED_TOOL in tools_before_exec
    assert REVOKED_TOOL not in tools_after_exec
