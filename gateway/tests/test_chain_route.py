# gateway/tests/test_chain_route.py
"""Tests for /api/chain/{table}/{id} route."""

from unittest.mock import patch, AsyncMock
import pytest


@pytest.fixture
def client():
    from gateway.app import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_chain_route_valid_table(client):
    mock_data = {"name": "Wanderer", "wallet": "0xabc", "level": 3, "alive": True, "createdAt": 1711929600}
    with patch("gateway.routes.chain.fetch_chain_record", new_callable=AsyncMock, return_value=mock_data):
        resp = client.get("/api/chain/Characters/c800dabf-b1ef-4033-a594-b1d7f80ee316")
    assert resp.status_code == 200
    body = resp.json()
    assert body["table"] == "Characters"
    assert body["data"]["name"] == "Wanderer"


def test_chain_route_invalid_table(client):
    resp = client.get("/api/chain/BadTable/some-id")
    assert resp.status_code == 400


def test_chain_route_not_found(client):
    with patch("gateway.routes.chain.fetch_chain_record", new_callable=AsyncMock, return_value=None):
        resp = client.get("/api/chain/Characters/nonexistent-id")
    assert resp.status_code == 404
