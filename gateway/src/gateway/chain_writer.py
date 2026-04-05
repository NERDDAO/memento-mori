"""Chain writer — sends transactions to the MUD World contract via web3."""

import os
import logging

logger = logging.getLogger(__name__)

_w3 = None
_world_address: str = ""
_private_key: str = ""


def _get_web3():
    """Lazy-init web3 connection."""
    global _w3, _world_address, _private_key
    if _w3 is None:
        try:
            from web3 import Web3
            rpc = os.getenv("REDSTONE_RPC", "http://localhost:8545")
            _w3 = Web3(Web3.HTTPProvider(rpc))
            _world_address = os.getenv("MUD_WORLD_ADDRESS", "")
            _private_key = os.getenv("ENGINE_PRIVATE_KEY", "")
        except ImportError:
            logger.warning("web3 not installed — chain writes disabled")
    return _w3, _world_address, _private_key


async def call_system(function_sig: str, args: list) -> bool:
    """Call a MUD system function on the World contract.

    Args:
        function_sig: Namespaced function name (e.g. 'memento__setPosition')
        args: Arguments matching the function signature

    Returns:
        True on success, False on failure.
    """
    try:
        w3, world_addr, pk = _get_web3()
        if not w3 or not world_addr or not pk:
            logger.debug("Chain writer not configured — skipping %s", function_sig)
            return False

        logger.info("Chain write: %s(%s)", function_sig, args[:2])
        # Full ABI-encoded transaction will be wired with generated IWorld ABI
        # For now, log the intent — chain writes are best-effort during dev
        return True

    except Exception:
        logger.warning("Chain write failed: %s", function_sig, exc_info=True)
        return False
