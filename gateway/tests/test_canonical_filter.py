# gateway/tests/test_canonical_filter.py
"""Tests for canonical entity verification in entity routes."""

from unittest.mock import patch, AsyncMock, MagicMock
import pytest


@pytest.fixture
def client():
    from gateway.app import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def _mock_kg_entity():
    """KG returns a Character entity with neighbors."""
    mock = MagicMock()
    mock.kg.get_entity.return_value = {
        "entity": {
            "uuid": "char-1",
            "name": "Kael",
            "labels": ["Player"],
            "summary": "A warrior",
        }
    }
    mock.kg.search.return_value = {
        "entities": [
            {"uuid": "char-1", "name": "Kael", "labels": ["Player"], "summary": "A warrior"},
            {"uuid": "item-1", "name": "Iron Sword", "labels": ["Item"], "summary": "A sword"},
            {"uuid": "ghost-1", "name": "Phantom NPC", "labels": ["Character"], "summary": "Should be filtered"},
        ],
        "edges": [
            {"source_name": "Kael", "target_name": "Iron Sword", "name": "OWNS", "fact": "Kael owns the sword"},
            {"source_name": "Kael", "target_name": "Phantom NPC", "name": "MET", "fact": "Should be filtered"},
        ],
    }
    return mock


async def _mock_exists(entity_id: str, labels: list[str]) -> bool:
    """char-1 and item-1 exist onchain, ghost-1 does not."""
    return entity_id in ("char-1", "item-1")


def test_neighbors_filters_non_canonical(client):
    mock = _mock_kg_entity()
    with patch("gateway.routes.entity.get_client", return_value=mock):
        with patch("gateway.routes.entity.entity_exists_onchain", side_effect=_mock_exists):
            resp = client.get("/api/entity/char-1/neighbors")

    body = resp.json()
    neighbor_names = [n["name"] for n in body["neighbors"]]
    assert "Iron Sword" in neighbor_names
    assert "Phantom NPC" not in neighbor_names

    edge_targets = [e["target"] for e in body["edges"]]
    assert "Iron Sword" in edge_targets
    assert "Phantom NPC" not in edge_targets
