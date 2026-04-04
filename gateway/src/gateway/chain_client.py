# gateway/src/gateway/chain_client.py
"""MUD indexer HTTP client. Proxies reads from Redstone via the indexer service."""

import os
import httpx
import logging

logger = logging.getLogger(__name__)

MUD_INDEXER_URL = os.getenv("MUD_INDEXER_URL", "http://localhost:3333")

ALLOWED_TABLES = frozenset({
    "Characters", "Deaths", "Items",
})

# Label → MUD table mapping for canonical verification
# Only entity types with onchain tables are mapped here.
# Unmapped types (Location, Region, etc.) pass through from KG directly.
LABEL_TABLE_MAP: dict[str, str] = {
    "Character": "Characters",
    "Player": "Characters",
    "Item": "Items",
    "Weapon": "Items",
    "Armor": "Items",
    "Consumable": "Items",
}


def uuid_to_bytes32_hex(uuid_str: str) -> str:
    """Convert UUID string to 0x-prefixed bytes32 hex for indexer queries."""
    clean = uuid_str.replace("-", "").replace("kg:entity:", "")
    try:
        padded = clean.ljust(64, "0")[:64]
        return "0x" + padded
    except ValueError:
        raw = uuid_str.encode("utf-8")[:32]
        return "0x" + raw.ljust(32, b"\x00").hex()


def table_for_labels(labels: list[str]) -> str | None:
    """Return the MUD table name for a set of KG labels, or None if no match."""
    for label in labels:
        if label in LABEL_TABLE_MAP:
            return LABEL_TABLE_MAP[label]
    return None


async def fetch_chain_record(table: str, entity_id: str) -> dict | list | None:
    """Fetch a record from the MUD indexer. Returns data dict, list, or None if not found."""
    if table not in ALLOWED_TABLES:
        return None

    b32 = uuid_to_bytes32_hex(entity_id)
    url = f"{MUD_INDEXER_URL}/api/tables/{table}/{b32}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.json()
            return None
        except httpx.HTTPError as e:
            logger.warning(f"MUD indexer request failed: {e}")
            return None


async def entity_exists_onchain(entity_id: str, labels: list[str]) -> bool:
    """Check if an entity with the given labels exists in the corresponding MUD table."""
    table = table_for_labels(labels)
    if table is None:
        # No matching table — entity type not tracked onchain, allow it through
        return True
    result = await fetch_chain_record(table, entity_id)
    return result is not None
