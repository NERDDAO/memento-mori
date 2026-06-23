"""Tests for TxLog and ActivationLog — append-only event-sourcing stores.

TDD gate:
- append two TxEntries for the same actor → for_actor returns them in insertion order
- append a TxEntry for a different actor → for_actor isolates per actor
- deltas survive round-trip (stored as-is, retrieved as-is)
- ActivationLog.join(activation_id) returns the matching ActivationRecord
- ActivationLog.join(unknown_id) returns None
- TxLog.for_actor on unknown actor returns empty list
"""
from __future__ import annotations

from datetime import datetime, timezone

from memento.state.tx_log import (
    ActivationLog,
    ActivationRecord,
    InMemoryActivationLog,
    InMemoryTxLog,
    TxEntry,
    TxLog,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ACTOR_A = "actor-uuid-aaaa"
ACTOR_B = "actor-uuid-bbbb"
ACT_1 = "act-uuid-0001"
ACT_2 = "act-uuid-0002"
ACT_3 = "act-uuid-0003"
MSG_1 = "msg-uuid-0001"
MSG_2 = "msg-uuid-0002"
MSG_3 = "msg-uuid-0003"


def _ts() -> datetime:
    return datetime.now(tz=timezone.utc)


def _tx(tx_id: str, activation_id: str, actor_id: str, tool: str, deltas: list[dict[str, object]]) -> TxEntry:
    return TxEntry(
        tx_id=tx_id,
        activation_id=activation_id,
        actor_id=actor_id,
        tool=tool,
        deltas=deltas,
        ts=_ts(),
    )


def _act(activation_id: str, message_id: str, actor_id: str, cxn_id: str, tool: str, roles: list[str]) -> ActivationRecord:
    return ActivationRecord(
        activation_id=activation_id,
        message_id=message_id,
        actor_id=actor_id,
        cxn_id=cxn_id,
        tool=tool,
        roles=roles,
        ts=_ts(),
    )


# ---------------------------------------------------------------------------
# TxLog tests
# ---------------------------------------------------------------------------


def test_txlog_protocol_satisfied() -> None:
    """InMemoryTxLog satisfies the TxLog Protocol at runtime."""
    log: TxLog = InMemoryTxLog()
    assert log is not None


def test_txlog_append_and_for_actor_order() -> None:
    """Two entries for the same actor come back in insertion order."""
    log = InMemoryTxLog()
    tx1 = _tx("tx-001", ACT_1, ACTOR_A, "mm_move", [{"op": "move", "target_uuid": "x"}])
    tx2 = _tx("tx-002", ACT_2, ACTOR_A, "mm_attack", [{"op": "set_attr", "field": "hp", "before": 20, "after": 18}])
    log.append(tx1)
    log.append(tx2)

    result = log.for_actor(ACTOR_A)
    assert len(result) == 2
    assert result[0].tx_id == "tx-001"
    assert result[1].tx_id == "tx-002"


def test_txlog_for_actor_isolation() -> None:
    """for_actor only returns entries for the requested actor."""
    log = InMemoryTxLog()
    log.append(_tx("tx-001", ACT_1, ACTOR_A, "mm_move", []))
    log.append(_tx("tx-002", ACT_2, ACTOR_B, "mm_look", []))
    log.append(_tx("tx-003", ACT_3, ACTOR_A, "mm_attack", []))

    result_a = log.for_actor(ACTOR_A)
    result_b = log.for_actor(ACTOR_B)

    assert len(result_a) == 2
    assert result_a[0].tx_id == "tx-001"
    assert result_a[1].tx_id == "tx-003"
    assert len(result_b) == 1
    assert result_b[0].tx_id == "tx-002"


def test_txlog_for_actor_unknown_returns_empty() -> None:
    """for_actor on an actor with no entries returns an empty list."""
    log = InMemoryTxLog()
    assert log.for_actor("no-such-actor") == []


def test_txlog_deltas_survive_roundtrip() -> None:
    """Delta dicts are stored and retrieved without mutation."""
    deltas = [
        {"op": "set_attr", "target_uuid": "ent-001", "field": "hp", "before": 20, "after": 15},
        {"op": "move", "target_uuid": "ent-001", "from": "room-a", "to": "room-b"},
    ]
    log = InMemoryTxLog()
    log.append(_tx("tx-999", ACT_1, ACTOR_A, "mm_move", deltas))
    result = log.for_actor(ACTOR_A)
    assert result[0].deltas == deltas


# ---------------------------------------------------------------------------
# ActivationLog tests
# ---------------------------------------------------------------------------


def test_activationlog_protocol_satisfied() -> None:
    """InMemoryActivationLog satisfies the ActivationLog Protocol at runtime."""
    log: ActivationLog = InMemoryActivationLog()
    assert log is not None


def test_activationlog_join_returns_matching_record() -> None:
    """join(activation_id) returns the matching ActivationRecord."""
    log = InMemoryActivationLog()
    rec = _act(ACT_1, MSG_1, ACTOR_A, "cxn-move-001", "mm_move", ["mover", "patient"])
    log.append(rec)
    result = log.join(ACT_1)
    assert result is not None
    assert result.activation_id == ACT_1
    assert result.message_id == MSG_1
    assert result.actor_id == ACTOR_A
    assert result.cxn_id == "cxn-move-001"
    assert result.tool == "mm_move"
    assert result.roles == ["mover", "patient"]


def test_activationlog_join_unknown_returns_none() -> None:
    """join on an unknown activation_id returns None."""
    log = InMemoryActivationLog()
    assert log.join("no-such-activation") is None


def test_activationlog_join_after_multiple_appends() -> None:
    """join returns the correct record when multiple records are present."""
    log = InMemoryActivationLog()
    log.append(_act(ACT_1, MSG_1, ACTOR_A, "cxn-move-001", "mm_move", ["mover"]))
    log.append(_act(ACT_2, MSG_2, ACTOR_A, "cxn-attack-001", "mm_attack", ["attacker", "target"]))
    log.append(_act(ACT_3, MSG_3, ACTOR_B, "cxn-look-001", "mm_look", ["looker"]))

    r2 = log.join(ACT_2)
    assert r2 is not None
    assert r2.cxn_id == "cxn-attack-001"
    assert r2.roles == ["attacker", "target"]

    r3 = log.join(ACT_3)
    assert r3 is not None
    assert r3.actor_id == ACTOR_B


def test_activationlog_for_actor_order() -> None:
    """for_actor on ActivationLog returns records in insertion order."""
    log = InMemoryActivationLog()
    log.append(_act(ACT_1, MSG_1, ACTOR_A, "cxn-001", "mm_move", []))
    log.append(_act(ACT_2, MSG_2, ACTOR_B, "cxn-002", "mm_look", []))
    log.append(_act(ACT_3, MSG_3, ACTOR_A, "cxn-003", "mm_attack", []))

    result = log.for_actor(ACTOR_A)
    assert len(result) == 2
    assert result[0].activation_id == ACT_1
    assert result[1].activation_id == ACT_3
