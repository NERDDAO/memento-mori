"""Tests for round close callback."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from memento.round_manager import PlayerAction


@pytest.mark.asyncio
async def test_send_batch_to_matrix():
    from gateway.round_callback import make_round_callback

    mock_bridge = MagicMock()
    mock_bridge.connected = True
    mock_bridge.get_or_create_room = AsyncMock(return_value="!room123")
    mock_bridge.send_action = AsyncMock()
    mock_bridge.ensure_npcs_in_room = AsyncMock()
    mock_bridge.client = MagicMock()
    mock_bridge.client.room_send = AsyncMock()
    mock_bridge.token = "test-token"

    mock_ws_hub = MagicMock()
    mock_ws_hub.broadcast_to_location = AsyncMock()

    callback = make_round_callback(mock_bridge, mock_ws_hub)

    actions = [
        PlayerAction(player_id="p1", player_name="Kael", action="attack goblin"),
        PlayerAction(player_id="p2", player_name="Thane", action="search room"),
    ]

    await callback("The Threshold", actions)

    mock_bridge.client.room_send.assert_called_once()
    call_args = mock_bridge.client.room_send.call_args
    assert call_args[0][0] == "!room123"
    content = call_args[0][2]
    assert content["com.bonfires.rpg"]["type"] == "player-action-batch"
    assert content["com.bonfires.rpg"]["batch"] is True
    assert len(content["com.bonfires.rpg"]["actions"]) == 2

    # send_action called once per player action
    assert mock_bridge.send_action.call_count == 2


@pytest.mark.asyncio
async def test_callback_noop_when_bridge_disconnected():
    from gateway.round_callback import make_round_callback

    mock_bridge = MagicMock()
    mock_bridge.connected = False

    callback = make_round_callback(mock_bridge, MagicMock())

    actions = [PlayerAction(player_id="p1", player_name="Kael", action="look")]
    await callback("tavern", actions)

    assert not mock_bridge.get_or_create_room.called
