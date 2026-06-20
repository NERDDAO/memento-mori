"""ChainMirror seam — fire-and-forget write-through to the on-chain permadeath subset.

The executor (C4) never imports ``tools/chain.py`` directly; it calls a
``ChainMirror`` façade so chain writes can be disabled in tests without
monkeypatching. See spec §6.3.

Implementations
---------------
``NoopChainMirror``  — does nothing; the Day-1 test double.
``LiveChainMirror``  — wraps ``tools/chain.py``; no-ops when ``chain.is_enabled()``
                       is false. Imports of ``tools/chain.py`` are done lazily so
                       that unit tests (which use ``NoopChainMirror``) never pull in
                       web3 / RNG / CrewAI tooling.

Contract: implementations MUST NOT raise — errors are logged and gameplay
continues. Chain writes are always the final step of an action and never
participate in rollback.
"""
from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class ChainMirror(Protocol):
    """Non-blocking. Implementations must not raise — errors are logged; gameplay continues."""

    def on_character_death(
        self, character_id: str, cause: str, location_id: str, tick: int
    ) -> None:
        """Mirror a permadeath to chain (maps to chain.record_death — NO killer_id)."""
        ...

    def on_item_transferred(self, item_id: str, new_owner_id: str) -> None:
        """Mirror an item ownership change to chain (maps to chain.transfer_item — arity 2)."""
        ...


class NoopChainMirror:
    """Test/dev double — every chain call is a silent no-op."""

    def on_character_death(
        self, character_id: str, cause: str, location_id: str, tick: int
    ) -> None:
        return None

    def on_item_transferred(self, item_id: str, new_owner_id: str) -> None:
        return None


class LiveChainMirror:
    """Wraps ``tools/chain.py``; no-ops when chain is disabled.

    ``tools/chain.py`` is imported lazily (inside the methods) so that the
    common test path — which never touches a live chain — does not import web3.
    Every public ``chain.py`` function is itself fire-and-forget; we additionally
    swallow any exception so the effect path can never be broken by a chain fault.
    """

    def on_character_death(
        self, character_id: str, cause: str, location_id: str, tick: int
    ) -> None:
        try:
            from memento.tools import chain  # lazy: avoid web3 import in tests

            if not chain.is_enabled():
                return None
            # NO killer_id — record_death takes none (reuse-inventory §1.1).
            chain.record_death(
                character_uuid=character_id,
                cause=cause,
                location=location_id,
                tick=tick,
            )
        except Exception:  # pragma: no cover - fire-and-forget
            logger.exception("LiveChainMirror.on_character_death failed (non-fatal)")
        return None

    def on_item_transferred(self, item_id: str, new_owner_id: str) -> None:
        try:
            from memento.tools import chain  # lazy

            if not chain.is_enabled():
                return None
            # arity 2 (reuse-inventory §1.2).
            chain.transfer_item(item_uuid=item_id, new_owner_uuid=new_owner_id)
        except Exception:  # pragma: no cover - fire-and-forget
            logger.exception("LiveChainMirror.on_item_transferred failed (non-fatal)")
        return None
