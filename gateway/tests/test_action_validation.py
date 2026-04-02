"""Tests for action route input validation."""

import pytest
from pydantic import ValidationError
from gateway.routes.action import ActionRequest


def test_valid_action():
    req = ActionRequest(player_id="abc-123", action="look around", location="tavern")
    assert req.player_id == "abc-123"
    assert req.action == "look around"


def test_action_whitespace_normalization():
    req = ActionRequest(player_id="abc", action="  hello   world  ")
    assert req.action == "hello world"


def test_action_too_long():
    with pytest.raises(ValidationError):
        ActionRequest(player_id="abc", action="a" * 501)


def test_empty_action():
    with pytest.raises(ValidationError):
        ActionRequest(player_id="abc", action="")


def test_player_id_invalid_chars():
    with pytest.raises(ValidationError):
        ActionRequest(player_id="abc;DROP TABLE", action="look")


def test_player_id_empty():
    with pytest.raises(ValidationError):
        ActionRequest(player_id="", action="look")


def test_player_id_too_long():
    with pytest.raises(ValidationError):
        ActionRequest(player_id="a" * 65, action="look")


def test_location_too_long():
    with pytest.raises(ValidationError):
        ActionRequest(player_id="abc", action="look", location="x" * 201)


def test_location_optional():
    req = ActionRequest(player_id="abc", action="look")
    assert req.location == ""
