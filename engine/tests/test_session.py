"""Tests for SessionManager — mocked KG calls."""

from unittest.mock import patch, MagicMock
from memento.session import SessionManager


def _make_mock_client():
    client = MagicMock()
    client.kg.create_entity.return_value = "player-uuid-123"
    client.kg.search.return_value = {
        "entities": [{"uuid": "loc-1", "name": "The Rusty Nail", "labels": ["Location"]}],
        "edges": [],
    }
    client.kg.create_edge.return_value = {"status": "ok"}
    client.kengrams.create.return_value = MagicMock(id="ke-1")
    client.kengrams.pin.return_value = {}
    client.agents.sync.return_value = {}
    return client


def test_create_player():
    mock = _make_mock_client()
    with patch("memento.session.get_client", return_value=mock), \
         patch("memento.session.make_narration_crew") as mock_crew, \
         patch("memento.seed.seed_threshold", return_value={"uuid": "threshold-uuid-1"}), \
         patch("memento.room_manifest.get_client", return_value=mock):
        mock_crew.return_value.kickoff.return_value.raw = "Welcome to the world."
        sm = SessionManager()
        result = sm.create_player("Kael")

    assert result["player_id"] == "player-uuid-123"
    assert result["location_name"] == "The Threshold"
    assert "Welcome" in result["opening_narrative"]
    mock.kg.create_entity.assert_called_once()


def test_end_session():
    mock = _make_mock_client()
    with patch("memento.session.get_client", return_value=mock):
        sm = SessionManager()
        result = sm.end_session("player-uuid-123")

    assert result["status"] == "ended"


def test_create_player_with_wallet():
    mock = _make_mock_client()
    with patch("memento.session.get_client", return_value=mock), \
         patch("memento.session.make_narration_crew") as mock_crew, \
         patch("memento.seed.seed_threshold", return_value={"uuid": "threshold-uuid-1"}), \
         patch("memento.room_manifest.get_client", return_value=mock), \
         patch("memento.tools.chain.is_enabled", return_value=True), \
         patch("memento.tools.chain.register_character") as mock_chain:
        mock_crew.return_value.kickoff.return_value.raw = "Welcome."
        sm = SessionManager()
        result = sm.create_player("Kael", wallet_address="0xabc123")

    assert result["player_id"] == "player-uuid-123"
    mock_chain.assert_called_once_with("player-uuid-123", "Kael", "0xabc123")


def test_handle_death():
    mock = _make_mock_client()
    with patch("memento.session.get_client", return_value=mock):
        with patch("memento.tools.kg.get_client", return_value=mock):
            sm = SessionManager()
            result = sm.handle_death("player-uuid-123", "slain by dragon", "Dragon's Lair")

    assert result["status"] == "dead"
    assert mock.kg.create_edge.called
