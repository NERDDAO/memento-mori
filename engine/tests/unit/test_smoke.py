"""Proves the async test toolchain is wired (pytest-asyncio, asyncio_mode=auto)."""
import memento.cxn  # noqa: F401
import memento.state  # noqa: F401
import memento.memory  # noqa: F401


async def test_async_smoke():
    """A bare async test that runs only if asyncio_mode='auto' is configured."""
    assert True
