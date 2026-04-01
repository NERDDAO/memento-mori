"""Unit tests for KG tools — mocked Bonfires client."""

from unittest.mock import patch, MagicMock
from memento.tools.kg import (
    create_entity, search_world, create_edge, update_entity,
    mark_status, remember_event, pin_entity, get_entity,
    get_episodes, get_neighbors,
)


def _make_mock_client():
    client = MagicMock()
    client.kg.create_entity.return_value = "uuid-123"
    client.kg.search.return_value = {
        "entities": [{"uuid": "uuid-123", "name": "Tavern", "labels": ["Location"], "summary": "A dim tavern."}],
        "edges": [],
    }
    client.kg.create_edge.return_value = {"status": "ok"}
    client.kg.update_entity.return_value = {"status": "ok"}
    client.kg.get_entity.return_value = {"uuid": "uuid-123", "name": "Tavern", "summary": "A dim tavern.", "labels": ["Location"]}
    client.agents.sync.return_value = {"stack": {"status": "ok"}}
    client.kengrams.get_active.return_value = MagicMock(id="ke-1")
    client.kengrams.pin.return_value = {"manifest": {}}
    return client


def test_create_entity():
    mock = _make_mock_client()
    with patch("memento.tools.kg.get_client", return_value=mock):
        result = create_entity.run(name="Tavern", entity_type="Location", summary="A dim tavern.")
    assert "uuid-123" in result
    assert "Tavern" in result
    mock.kg.create_entity.assert_called_once()


def test_search_world():
    mock = _make_mock_client()
    with patch("memento.tools.kg.get_client", return_value=mock):
        result = search_world.run(query="tavern")
    assert "Tavern" in result
    assert "Location" in result


def test_create_edge():
    mock = _make_mock_client()
    with patch("memento.tools.kg.get_client", return_value=mock):
        with patch("memento.tools.kg._resolve_entity_uuid", side_effect=["uuid-1", "uuid-2"]):
            result = create_edge.run(source_name="Player", target_name="Tavern", relationship="LOCATED_IN")
    assert "LOCATED_IN" in result


def test_update_entity():
    mock = _make_mock_client()
    with patch("memento.tools.kg.get_client", return_value=mock):
        with patch("memento.tools.kg._resolve_entity_uuid", return_value="uuid-123"):
            result = update_entity.run(name="Tavern", new_summary="A bright tavern.", new_labels="Location,Tavern")
    assert "Updated" in result


def test_mark_status():
    mock = _make_mock_client()
    with patch("memento.tools.kg.get_client", return_value=mock):
        with patch("memento.tools.kg._resolve_entity_uuid", return_value="uuid-1"):
            result = mark_status.run(entity_name="Kael", status="DEAD", cause="slain by goblin")
    assert "DEAD" in result


def test_remember_event():
    mock = _make_mock_client()
    with patch("memento.tools.kg.get_client", return_value=mock):
        result = remember_event.run(summary="A battle took place at the tavern")
    assert "Recorded" in result
    mock.agents.sync.assert_called_once()


def test_pin_entity():
    mock = _make_mock_client()
    with patch("memento.tools.kg.get_client", return_value=mock):
        with patch("memento.tools.kg._resolve_entity_uuid", return_value="uuid-123"):
            result = pin_entity.run(entity_name="Tavern")
    assert "Pinned" in result
    mock.kengrams.pin.assert_called_once()


def test_get_entity():
    mock = _make_mock_client()
    with patch("memento.tools.kg.get_client", return_value=mock):
        with patch("memento.tools.kg._resolve_entity_uuid", return_value="uuid-123"):
            result = get_entity.run(name="Tavern")
    assert "Tavern" in result
    assert "Location" in result


def test_get_episodes():
    mock = _make_mock_client()
    with patch("memento.tools.kg.get_client", return_value=mock):
        result = get_episodes.run(limit=5)
    assert "Tavern" in result  # returns same mock search results


def test_get_neighbors():
    mock = _make_mock_client()
    with patch("memento.tools.kg.get_client", return_value=mock):
        result = get_neighbors.run(entity_name="Tavern")
    assert "Tavern" in result


def test_create_entity_not_found():
    mock = _make_mock_client()
    with patch("memento.tools.kg.get_client", return_value=mock):
        with patch("memento.tools.kg._resolve_entity_uuid", return_value=None):
            result = mark_status.run(entity_name="Ghost", status="DEAD")
    assert "Error" in result
