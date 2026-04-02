"""Tests for the Pinata IPFS module."""

import hashlib
import json
from unittest.mock import patch, MagicMock

import pytest


def test_hash_json_deterministic():
    """Same data always produces the same hash regardless of key insertion order."""
    from memento.tools.ipfs import _hash_json

    data_a = {"name": "Episode 1", "summary": "Things happened", "tick": 42}
    data_b = {"tick": 42, "summary": "Things happened", "name": "Episode 1"}

    assert _hash_json(data_a) == _hash_json(data_b)


def test_hash_json_returns_bytes32():
    """Hash output is 32 bytes (keccak256)."""
    from memento.tools.ipfs import _hash_json

    result = _hash_json({"test": "data"})
    assert isinstance(result, bytes)
    assert len(result) == 32


@patch("memento.tools.ipfs.requests.post")
def test_pin_json_success(mock_post):
    """pin_json uploads to Pinata and returns (cid, hash)."""
    from memento.tools.ipfs import pin_json

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"IpfsHash": "QmTestCid123"}
    mock_post.return_value = mock_response

    data = {"name": "The Fall of Ashwick", "summary": "Kael discovered the vault"}

    with patch("memento.tools.ipfs.PINATA_JWT", "test-jwt-token"):
        cid, content_hash = pin_json(data)

    assert cid == "QmTestCid123"
    assert isinstance(content_hash, bytes)
    assert len(content_hash) == 32

    # Verify the POST was called correctly
    call_args = mock_post.call_args
    assert call_args[0][0] == "https://api.pinata.cloud/pinning/pinJSONToIPFS"
    assert call_args[1]["headers"]["Authorization"] == "Bearer test-jwt-token"

    # Verify keccak256 hash is in pin metadata
    body = call_args[1]["json"]
    assert "pinataMetadata" in body
    assert "keccak256" in body["pinataMetadata"]["keyvalues"]


@patch("memento.tools.ipfs.requests.post")
def test_pin_json_failure_returns_none(mock_post):
    """pin_json returns (None, None) on Pinata API failure."""
    from memento.tools.ipfs import pin_json

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = Exception("Server error")
    mock_post.return_value = mock_response

    with patch("memento.tools.ipfs.PINATA_JWT", "test-jwt-token"):
        cid, content_hash = pin_json({"test": "data"})

    assert cid is None
    assert content_hash is None


def test_pin_json_disabled_without_jwt():
    """pin_json returns (None, None) when PINATA_JWT is empty."""
    from memento.tools.ipfs import pin_json

    with patch("memento.tools.ipfs.PINATA_JWT", ""):
        cid, content_hash = pin_json({"test": "data"})

    assert cid is None
    assert content_hash is None
