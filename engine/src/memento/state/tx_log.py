"""TxLog and ActivationLog — append-only event-sourcing stores.

This module defines:
- TxEntry        — one state-change transaction record (§ event-sourcing spine)
- ActivationRecord — construction activation that gave a TxEntry its provenance
- TxLog          — Protocol for the transaction log
- ActivationLog  — Protocol for the activation log

Implementations
---------------
InMemoryTxLog        (this module) — list-backed, Day-1 default; no persistence.
InMemoryActivationLog (this module) — list-backed, Day-1 default; no persistence.

MongoTxLog / MongoActivationLog (FUTURE — engine/src/memento/state/mongo_tx_log.py)
    Beanie/Motor-backed against MongoDB.  Swap in behind the Protocol; no callers
    outside this package import concrete classes by name.

No component outside engine/src/memento/state/ should import concrete classes.
All callers depend only on the Protocols (TxLog, ActivationLog) and the TypedDicts
defined here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


# ---------------------------------------------------------------------------
# Document shapes
# ---------------------------------------------------------------------------


@dataclass
class TxEntry:
    """A single state-change transaction record.

    Fields
    ------
    tx_id          : globally unique transaction identifier (UUID string)
    activation_id  : the ActivationRecord that produced this transaction
    actor_id       : the entity whose action caused this transaction
    tool           : the mm_* tool name (e.g. "mm_move", "mm_attack")
    deltas         : ordered list of StateDelta-shaped dicts recording what
                     changed (op / target_uuid / field / before / after)
    ts             : UTC timestamp of when the transaction was appended
    """

    tx_id: str
    activation_id: str
    actor_id: str
    tool: str
    deltas: list[dict[str, object]]
    ts: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


@dataclass
class ActivationRecord:
    """A construction activation — the provenance record for a TxEntry.

    Fields
    ------
    activation_id  : globally unique activation identifier (UUID string)
    message_id     : the LLM message turn that triggered this activation
    actor_id       : the entity whose message activated the construction
    cxn_id         : the Construction identifier that was activated
    tool           : the mm_* tool that was selected
    roles          : ordered list of role labels (e.g. ["mover", "patient"])
    ts             : UTC timestamp of when the activation was recorded
    """

    activation_id: str
    message_id: str
    actor_id: str
    cxn_id: str
    tool: str
    roles: list[str] = field(default_factory=list)
    ts: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class TxLog(Protocol):
    """Port for the append-only transaction log.

    All identifiers are UUID strings.

    ``for_actor`` returns entries in append order (oldest first).  The
    EffectExecutor (C4) and EventSourcedStateRepository (Task 3) are the only
    callers outside this package.
    """

    def append(self, entry: TxEntry) -> None:
        """Append a transaction record to the log."""
        ...

    def for_actor(self, actor_id: str) -> list[TxEntry]:
        """Return all transaction records for an actor, in append order."""
        ...


class ActivationLog(Protocol):
    """Port for the append-only activation log.

    ``join(activation_id)`` returns the single matching ActivationRecord, or
    None if no record with that activation_id exists.  Used by Task 3's
    EventSourcedStateRepository to hydrate provenance when replaying a
    TxEntry.
    """

    def append(self, record: ActivationRecord) -> None:
        """Append an activation record to the log."""
        ...

    def for_actor(self, actor_id: str) -> list[ActivationRecord]:
        """Return all activation records for an actor, in append order."""
        ...

    def join(self, activation_id: str) -> ActivationRecord | None:
        """Return the ActivationRecord with the given activation_id, or None."""
        ...


# ---------------------------------------------------------------------------
# In-memory implementations
# ---------------------------------------------------------------------------


class InMemoryTxLog:
    """List-backed TxLog for tests and local development.

    Thread-safety: none — single-threaded Day-1 use only.
    """

    def __init__(self) -> None:
        self._entries: list[TxEntry] = []

    def append(self, entry: TxEntry) -> None:
        """Append a transaction record."""
        self._entries.append(entry)

    def for_actor(self, actor_id: str) -> list[TxEntry]:
        """Return all entries for actor_id in insertion order."""
        return [e for e in self._entries if e.actor_id == actor_id]


class InMemoryActivationLog:
    """List-backed ActivationLog for tests and local development.

    Thread-safety: none — single-threaded Day-1 use only.
    """

    def __init__(self) -> None:
        self._records: list[ActivationRecord] = []

    def append(self, record: ActivationRecord) -> None:
        """Append an activation record."""
        self._records.append(record)

    def for_actor(self, actor_id: str) -> list[ActivationRecord]:
        """Return all activation records for actor_id in insertion order."""
        return [r for r in self._records if r.actor_id == actor_id]

    def join(self, activation_id: str) -> ActivationRecord | None:
        """Return the record with the given activation_id, or None."""
        for record in self._records:
            if record.activation_id == activation_id:
                return record
        return None
