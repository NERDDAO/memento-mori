import pytest

from gateway.scene_activation import SceneActivationService


class _State:
    def __init__(self, bonfire_id=None):
        self.cxn_repo = object()
        self.agent_runtime_client = object()
        self.scene_registry = {}
        if bonfire_id is not None:
            self.bonfire_id = bonfire_id


def test_from_app_state_threads_bonfire_id():
    svc = SceneActivationService.from_app_state(
        _State(bonfire_id="6650000000000000000000f1")
    )
    assert svc._bonfire_id == "6650000000000000000000f1"


def test_from_app_state_falls_back_to_slug_when_absent():
    svc = SceneActivationService.from_app_state(_State())  # no bonfire_id attr
    assert svc._bonfire_id == "mm-world-v1"


def test_register_cxn_tools_threads_bonfire_id_into_executor():
    from mcp.server.fastmcp import FastMCP

    from gateway.cxn_tools import register_cxn_tools
    from memento.memory.null_client import NullMemoryClient
    from memento.state.chain_mirror import NoopChainMirror
    from memento.state.in_memory import InMemoryStateRepository

    executor = register_cxn_tools(
        FastMCP("t"),
        None,
        InMemoryStateRepository(),
        NoopChainMirror(),
        NullMemoryClient(),
        bonfire_id="6650000000000000000000f1",
    )
    assert executor._bonfire_id == "6650000000000000000000f1"
