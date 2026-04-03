# engine/tests/test_chain.py
"""Chain module unit tests. No chain connection needed."""

import os


def test_chain_module_loads():
    """chain.py loads without errors even without web3 installed."""
    from memento.tools.chain import is_enabled
    assert isinstance(is_enabled(), bool)


def test_chain_disabled_by_default():
    """Without env vars, chain is disabled."""
    from memento.tools.chain import is_enabled
    # Unless env vars are set in the test environment
    if not os.getenv("MUD_WORLD_ADDRESS"):
        assert is_enabled() is False


def test_uuid_to_bytes32():
    """UUID conversion produces 32 bytes."""
    from memento.tools.chain import _uuid_to_bytes32
    result = _uuid_to_bytes32("c800dabf-b1ef-4033-a594-b1d7f80ee316")
    assert len(result) == 32
    assert isinstance(result, bytes)


def test_uuid_to_bytes32_short():
    """Short UUIDs get padded."""
    from memento.tools.chain import _uuid_to_bytes32
    result = _uuid_to_bytes32("abc123")
    assert len(result) == 32


def test_register_character_noop_when_disabled():
    """When chain is disabled, register_character is a silent no-op."""
    from memento.tools.chain import register_character
    # Should not raise even with chain disabled
    register_character("test-uuid", "TestHero", "")


def test_record_death_noop_when_disabled():
    from memento.tools.chain import record_death
    record_death("test-uuid", "dragon fire", "The Threshold", 42)
