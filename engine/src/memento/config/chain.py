# engine/src/memento/config/chain.py
"""Redstone chain configuration. Reads from env vars."""

import os


REDSTONE_RPC = os.getenv("REDSTONE_RPC", "http://localhost:8545")
MUD_WORLD_ADDRESS = os.getenv("MUD_WORLD_ADDRESS", "")
ENGINE_PRIVATE_KEY = os.getenv("ENGINE_PRIVATE_KEY", "")
CHAIN_ENABLED = bool(MUD_WORLD_ADDRESS and ENGINE_PRIVATE_KEY)
MUD_INDEXER_URL = os.getenv("MUD_INDEXER_URL", "http://localhost:3333")

PINATA_JWT = os.getenv("PINATA_JWT", "")
IPFS_ENABLED = bool(PINATA_JWT)

# Epoch config — commits happen at session boundaries by default
EPOCH_ENABLED = os.getenv("EPOCH_ENABLED", "true").lower() in ("true", "1", "yes")
EPOCH_INTERVAL_TICKS = int(os.getenv("EPOCH_INTERVAL_TICKS", "0"))  # 0 = session boundaries only
