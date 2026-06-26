"""Unit tests for _build_cxn_repo() env-gated factory (Task 4).

TDD: tests written first, factory implemented after RED confirmed.

Pure unit — monkeypatches env + SDK getter so no real connection is made.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_factory():
    """Import the factory fresh (avoids cached module-level state between
    tests that flip env vars)."""
    import importlib
    import gateway.mcp_server as mod

    importlib.reload(mod)
    return mod._build_cxn_repo


# ---------------------------------------------------------------------------
# Test: env unset → InMemoryStateRepository
# ---------------------------------------------------------------------------


def test_env_unset_returns_in_memory(monkeypatch):
    """When KERNEL_BASE_URL / GM_INTERNAL_TOKEN are absent, the factory must
    return an InMemoryStateRepository (byte-equivalent to the old hard-wired
    assignment)."""
    monkeypatch.delenv("KERNEL_BASE_URL", raising=False)
    monkeypatch.delenv("GM_INTERNAL_TOKEN", raising=False)

    from gateway.mcp_server import _build_cxn_repo
    from memento.state.in_memory import InMemoryStateRepository

    result = _build_cxn_repo()
    assert isinstance(result, InMemoryStateRepository)


# ---------------------------------------------------------------------------
# Test: env set → EventSourcedStateRepository (KG-backed)
# ---------------------------------------------------------------------------


def test_env_set_returns_event_sourced(monkeypatch):
    """When both KERNEL_BASE_URL and GM_INTERNAL_TOKEN are set, the factory
    must return an EventSourcedStateRepository whose projection is a
    KgProjection wrapping the SDK's .kg attribute."""
    monkeypatch.setenv("KERNEL_BASE_URL", "http://kernel.test")
    monkeypatch.setenv("GM_INTERNAL_TOKEN", "test-token")

    # Stub get_client() so no real SDK connection happens
    dummy_kg = object()

    class _FakeClient:
        kg = dummy_kg

    monkeypatch.setattr(
        "memento.bonfires_client.get_client",
        lambda: _FakeClient(),
    )

    from gateway.mcp_server import _build_cxn_repo
    from memento.state.event_sourced import EventSourcedStateRepository
    from memento.state.kg_projection import KgProjection

    result = _build_cxn_repo()
    assert isinstance(result, EventSourcedStateRepository)
    assert isinstance(result._projection, KgProjection)
    assert result._projection._kg is dummy_kg
