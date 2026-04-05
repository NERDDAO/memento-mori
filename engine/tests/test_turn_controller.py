"""Tests for TurnController — fast turn orchestration."""

from unittest.mock import MagicMock, patch

from memento.turn_controller import TurnController
from memento.transport import NullTransport


def _make_controller(**overrides):
    defaults = dict(
        location="tavern",
        location_uuid="loc-123",
        actions=[{"player_name": "Kael", "action": "look around"}],
        transport=NullTransport(),
        npc_wait=0.1,
    )
    defaults.update(overrides)
    return TurnController(**defaults)


def test_run_returns_tuple():
    with patch.object(TurnController, "_narrate", return_value="The tavern is quiet."):
        tc = _make_controller()
        narrative, state_update = tc.run()
        assert isinstance(narrative, str)
        assert isinstance(state_update, dict)


def test_run_emits_ready_phase_on_success():
    transport = MagicMock()
    transport.get_npc_count.return_value = 0
    with patch.object(TurnController, "_narrate", return_value="Narrative."):
        tc = _make_controller(transport=transport)
        tc.run()
        transport.emit_phase.assert_called_with("tavern", "ready", None)


def test_run_emits_ready_on_exception():
    transport = MagicMock()
    with patch.object(TurnController, "_run_inner", side_effect=RuntimeError("boom")):
        tc = _make_controller(transport=transport)
        narrative, state_update = tc.run()
        assert narrative == ""
        transport.emit_phase.assert_called_with("tavern", "ready", None)


def test_combined_action_joins_actions():
    tc = _make_controller(actions=[
        {"player_name": "Kael", "action": "attack goblin"},
        {"player_name": "Lyra", "action": "cast heal"},
    ])
    assert "Kael: attack goblin" in tc.combined_action
    assert "Lyra: cast heal" in tc.combined_action


def test_npc_wait_skips_when_no_npcs():
    transport = MagicMock()
    transport.get_npc_count.return_value = 0
    tc = _make_controller(transport=transport)
    tc._await_npcs()
    transport.clear_npc_responses.assert_not_called()
