"""Tests for session route input validation."""

import pytest
from pydantic import ValidationError
from gateway.routes.session import CreateSessionRequest


def test_valid_session_request():
    req = CreateSessionRequest(
        player_name="Kael",
        wallet_address="0x" + "a" * 40,
    )
    assert req.player_name == "Kael"
    assert req.game_id == "default"


def test_player_name_too_long():
    with pytest.raises(ValidationError):
        CreateSessionRequest(
            player_name="a" * 31,
            wallet_address="0x" + "a" * 40,
        )


def test_player_name_invalid_chars():
    with pytest.raises(ValidationError):
        CreateSessionRequest(
            player_name="Kael<script>",
            wallet_address="0x" + "a" * 40,
        )


def test_wallet_address_too_short():
    with pytest.raises(ValidationError):
        CreateSessionRequest(
            player_name="Kael",
            wallet_address="0xabc",
        )


def test_wallet_address_invalid_format():
    with pytest.raises(ValidationError):
        CreateSessionRequest(
            player_name="Kael",
            wallet_address="not-a-wallet-address-at-all!!!",
        )


def test_wallet_address_valid_hex():
    req = CreateSessionRequest(
        player_name="Kael",
        wallet_address="0xAbCdEf1234567890aBcDeF1234567890AbCdEf12",
    )
    assert req.wallet_address.startswith("0x")


def test_player_name_with_spaces():
    req = CreateSessionRequest(
        player_name="Kael the Brave",
        wallet_address="0x" + "a" * 40,
    )
    assert req.player_name == "Kael the Brave"
