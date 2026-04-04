# engine/src/memento/tools/chain.py
"""Thin wrapper around MUD system calls on Redstone.

All functions are non-blocking — chain writes are submitted in a background
thread. If the chain is unavailable, errors are logged but never block gameplay.
"""

from __future__ import annotations

import json
import logging
import threading

logger = logging.getLogger(__name__)

# Lazy-initialized web3 instance
_w3 = None
_account = None
_world_address = None
_world_abi: list[dict] | None = None


def _get_web3():
    """Lazy-init web3 connection and account."""
    global _w3, _account, _world_address
    if _w3 is not None:
        return _w3, _account, _world_address

    from memento.config.chain import CHAIN_ENABLED, REDSTONE_RPC, MUD_WORLD_ADDRESS, ENGINE_PRIVATE_KEY

    if not CHAIN_ENABLED:
        return None, None, None

    try:
        from web3 import Web3
        _w3 = Web3(Web3.HTTPProvider(REDSTONE_RPC))
        _account = _w3.eth.account.from_key(ENGINE_PRIVATE_KEY)
        _world_address = Web3.to_checksum_address(MUD_WORLD_ADDRESS)
        logger.info(f"Chain connected: {REDSTONE_RPC}, world: {_world_address}")
        return _w3, _account, _world_address
    except Exception as e:
        logger.warning(f"Chain init failed: {e}")
        return None, None, None


def _uuid_to_bytes32(uuid_str: str) -> bytes:
    """Convert a UUID string to bytes32 for Solidity.

    Handles standard UUIDs (hex after stripping dashes) and arbitrary strings
    (encoded as UTF-8 and zero-padded). Always returns exactly 32 bytes.
    """
    clean = uuid_str.replace("-", "").replace("kg:entity:", "")
    try:
        # Pad hex string to exactly 64 hex chars (32 bytes) before decoding
        padded = clean.ljust(64, "0")[:64]
        return bytes.fromhex(padded)
    except ValueError:
        # Non-hex string: encode as UTF-8 and zero-pad to 32 bytes
        raw = uuid_str.encode("utf-8")[:32]
        return raw.ljust(32, b"\x00")


def _send_tx(fn_name: str, *args):
    """Submit a transaction in a background thread. Fire-and-forget."""
    def _do():
        try:
            w3, account, world_addr = _get_web3()
            if not w3 or not account or not world_addr:
                return

            # Build function call data using the function selector
            # MUD namespaces functions as memento__functionName
            from web3 import Web3
            fn_sig = f"memento__{fn_name}"

            # For now, use low-level encoding
            # In production, load the IWorld ABI for type-safe calls
            contract = w3.eth.contract(address=world_addr, abi=_get_abi())
            fn = getattr(contract.functions, fn_sig)(*args)

            tx = fn.build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 500_000,
                "gasPrice": w3.eth.gas_price,
            })
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            logger.info(f"Chain tx sent: {fn_name} -> {tx_hash.hex()}")
        except Exception as e:
            logger.warning(f"Chain write failed ({fn_name}): {e}")

    threading.Thread(target=_do, daemon=True).start()


def _get_abi() -> list[dict]:
    """Load the IWorld ABI. Cached after first load."""
    global _world_abi
    if _world_abi is not None:
        return _world_abi

    import os
    abi_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..", "..",  # engine/ -> memento-mori/
        "contracts", "packages", "contracts", "out", "IWorld.sol", "IWorld.json",
    )
    abi_path = os.path.normpath(abi_path)
    try:
        with open(abi_path) as f:
            data = json.load(f)
            _world_abi = data.get("abi", data)
            return _world_abi
    except FileNotFoundError:
        logger.warning(f"IWorld ABI not found at {abi_path}, chain calls will fail")
        return []


# ── Public API ──

def register_character(uuid: str, name: str, wallet: str) -> None:
    """Register a character onchain."""
    from web3 import Web3
    checksum_wallet = Web3.to_checksum_address(wallet) if wallet else "0x0000000000000000000000000000000000000000"
    _send_tx(
        "registerCharacter",
        _uuid_to_bytes32(uuid),
        name,
        checksum_wallet,
        0,  # EntityType.Character
    )


def record_death(character_uuid: str, cause: str, location: str, tick: int) -> None:
    """Record a permanent death onchain."""
    _send_tx(
        "killCharacter",
        _uuid_to_bytes32(character_uuid),
        cause,
        location,
        tick,
    )


def register_item(uuid: str, name: str, rarity: str, owner_uuid: str, location_uuid: str) -> None:
    """Register an item onchain."""
    _send_tx(
        "registerItem",
        _uuid_to_bytes32(uuid),
        name,
        rarity,
        _uuid_to_bytes32(owner_uuid) if owner_uuid else b"\x00" * 32,
        _uuid_to_bytes32(location_uuid) if location_uuid else b"\x00" * 32,
    )


def transfer_item(item_uuid: str, new_owner_uuid: str) -> None:
    """Transfer item ownership onchain."""
    _send_tx(
        "transferItem",
        _uuid_to_bytes32(item_uuid),
        _uuid_to_bytes32(new_owner_uuid),
    )


def drop_item(item_uuid: str, location_uuid: str) -> None:
    """Drop item at a location onchain (e.g., on death)."""
    _send_tx(
        "dropItem",
        _uuid_to_bytes32(item_uuid),
        _uuid_to_bytes32(location_uuid),
    )


def is_enabled() -> bool:
    """Check if chain writes are enabled."""
    from memento.config.chain import CHAIN_ENABLED
    return CHAIN_ENABLED
