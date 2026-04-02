"""Tests for RoundManager."""

import asyncio
import pytest
from memento.round_manager import RoundManager, PlayerAction


@pytest.mark.asyncio
async def test_round_manager_batches_actions():
    rm = RoundManager(window_seconds=0.5)
    results = []

    async def on_close(location, actions):
        results.append((location, len(actions)))

    rm.on_round_close(on_close)

    await rm.submit_action("p1", "Kael", "tavern", "look around")
    await rm.submit_action("p2", "Lyra", "tavern", "talk to barkeep")

    assert rm.active_count == 1

    # Wait for round to close
    await asyncio.sleep(1.0)

    assert len(results) == 1
    assert results[0] == ("tavern", 2)
    assert rm.active_count == 0


@pytest.mark.asyncio
async def test_round_manager_separate_locations():
    rm = RoundManager(window_seconds=0.5)
    results = []

    async def on_close(location, actions):
        results.append(location)

    rm.on_round_close(on_close)

    await rm.submit_action("p1", "Kael", "tavern", "look")
    await rm.submit_action("p2", "Lyra", "market", "browse")

    assert rm.active_count == 2

    await asyncio.sleep(1.0)

    assert len(results) == 2
    assert set(results) == {"tavern", "market"}


@pytest.mark.asyncio
async def test_duplicate_rejection():
    rm = RoundManager(window_seconds=1.0)

    accepted1 = await rm.submit_action("p1", "Kael", "tavern", "attack goblin")
    accepted2 = await rm.submit_action("p1", "Kael", "tavern", "cast fireball")

    assert accepted1 is True
    assert accepted2 is False

    round_ = rm.active_rounds.get("tavern")
    assert round_ is not None
    assert len(round_.actions) == 1  # Only the first action


@pytest.mark.asyncio
async def test_different_players_accepted():
    rm = RoundManager(window_seconds=1.0)

    a1 = await rm.submit_action("p1", "Kael", "tavern", "attack")
    a2 = await rm.submit_action("p2", "Lyra", "tavern", "defend")
    a3 = await rm.submit_action("p3", "Brom", "tavern", "flee")

    assert a1 is True
    assert a2 is True
    assert a3 is True

    round_ = rm.active_rounds.get("tavern")
    assert len(round_.actions) == 3


@pytest.mark.asyncio
async def test_window_extends_on_new_player():
    rm = RoundManager(window_seconds=0.5)
    results = []

    async def on_close(location, actions):
        results.append(len(actions))

    rm.on_round_close(on_close)

    await rm.submit_action("p1", "Kael", "tavern", "look")
    await asyncio.sleep(0.3)  # 0.3s in, window would close at 0.5s
    await rm.submit_action("p2", "Lyra", "tavern", "talk")
    # Window extended — should close ~0.5s after Lyra's action

    await asyncio.sleep(0.4)  # 0.7s total — first window would have expired
    assert len(results) == 0  # But round should still be open (extended)

    await asyncio.sleep(0.3)  # 1.0s total — extended window expires
    assert len(results) == 1
    assert results[0] == 2


@pytest.mark.asyncio
async def test_on_action_callback():
    rm = RoundManager(window_seconds=1.0)
    action_events = []

    async def on_action(location, new_action, all_actions):
        action_events.append((location, new_action.player_name, len(all_actions)))

    rm.on_action(on_action)

    await rm.submit_action("p1", "Kael", "tavern", "look")
    await rm.submit_action("p2", "Lyra", "tavern", "talk")

    assert len(action_events) == 2
    assert action_events[0] == ("tavern", "Kael", 1)
    assert action_events[1] == ("tavern", "Lyra", 2)


@pytest.mark.asyncio
async def test_get_pending_actions():
    rm = RoundManager(window_seconds=1.0)

    await rm.submit_action("p1", "Kael", "tavern", "look")
    await rm.submit_action("p2", "Lyra", "tavern", "talk")

    pending = rm.get_pending_actions("tavern")
    assert len(pending) == 2
    assert pending[0].player_name == "Kael"
    assert pending[1].player_name == "Lyra"

    # No round at market
    assert rm.get_pending_actions("market") == []


@pytest.mark.asyncio
async def test_is_round_active():
    rm = RoundManager(window_seconds=0.5)

    assert rm.is_round_active("tavern") is False
    await rm.submit_action("p1", "Kael", "tavern", "look")
    assert rm.is_round_active("tavern") is True

    await asyncio.sleep(0.7)
    assert rm.is_round_active("tavern") is False
