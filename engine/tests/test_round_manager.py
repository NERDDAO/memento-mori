"""Tests for RoundManager."""

import asyncio
import pytest
from memento.round_manager import RoundManager, PlayerAction


@pytest.mark.asyncio
async def test_round_manager_batches_actions():
    rm = RoundManager(window_seconds=1)
    results = []

    async def on_close(location, actions):
        results.append((location, len(actions)))

    rm.on_round_close(on_close)

    await rm.submit_action("p1", "Kael", "tavern", "look around")
    await rm.submit_action("p2", "Lyra", "tavern", "talk to barkeep")

    assert rm.active_count == 1

    # Wait for round to close
    await asyncio.sleep(1.5)

    assert len(results) == 1
    assert results[0] == ("tavern", 2)
    assert rm.active_count == 0


@pytest.mark.asyncio
async def test_round_manager_separate_locations():
    rm = RoundManager(window_seconds=1)
    results = []

    async def on_close(location, actions):
        results.append(location)

    rm.on_round_close(on_close)

    await rm.submit_action("p1", "Kael", "tavern", "look")
    await rm.submit_action("p2", "Lyra", "market", "browse")

    assert rm.active_count == 2

    await asyncio.sleep(1.5)

    assert len(results) == 2
    assert set(results) == {"tavern", "market"}
