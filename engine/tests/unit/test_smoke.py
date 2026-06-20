"""Proves the async test toolchain is wired (pytest-asyncio, asyncio_mode=auto)."""
import memento.cxn  # noqa: F401
import memento.state  # noqa: F401
import memento.memory  # noqa: F401


async def test_async_smoke():
    """A bare async test that runs only if asyncio_mode='auto' is configured."""
    assert True


def test_fixtures_uuids_present():
    from tests import fixtures
    for name in ("KAEL", "GOBLIN", "IRON_SWORD", "ASH_MARKET", "RIVER_GATE"):
        val = getattr(fixtures, name)
        assert isinstance(val, str) and len(val) == 24  # 24-hex ObjectId shape
