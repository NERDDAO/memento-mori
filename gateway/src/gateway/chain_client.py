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


def bytes32_to_uuid(hex_str: str) -> str:
    """Convert 0x-prefixed bytes32 hex back to UUID string.

    Reverses uuid_to_bytes32_hex: strips 0x prefix, trims trailing zeros,
    pads to 32 hex chars, inserts UUID dashes.
    """
    clean = hex_str.replace("0x", "").rstrip("0")
    if len(clean) < 32:
        clean = clean.ljust(32, "0")
    clean = clean[:32]
    return f"{clean[:8]}-{clean[8:12]}-{clean[12:16]}-{clean[16:20]}-{clean[20:32]}"


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


async def fetch_characters_by_wallet(wallet_address: str) -> list[dict]:
    """Query MUD indexer for all Characters owned by a wallet address.

    Uses the indexer's SQL API (requires ENABLE_UNSAFE_QUERY_API=true on indexer).
    Returns list of character dicts with player_id, player_name, level, alive.
    """
    sql_url = f"{MUD_INDEXER_URL}/api/sql"
    wallet_lower = wallet_address.lower()

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(sql_url, params={
                "query": f"SELECT * FROM memento__Characters WHERE wallet = '{wallet_lower}'"
            })
            if resp.status_code == 200:
                data = resp.json()
                rows = data if isinstance(data, list) else data.get("rows", data.get("result", []))
                characters = []
                for row in rows:
                    if isinstance(row, dict):
                        characters.append({
                            "player_id": bytes32_to_uuid(row.get("id", "")),
                            "id_bytes32": row.get("id", ""),
                            "player_name": row.get("name", "Unknown"),
                            "level": int(row.get("level", 1)),
                            "alive": bool(row.get("alive", True)),
                            "health": int(row.get("level", 1)) * 100,
                            "archetype": "",
                        })
                return characters
            else:
                logger.warning(f"MUD indexer SQL query returned {resp.status_code}")
                return []
        except httpx.HTTPError as e:
            logger.warning(f"MUD indexer query failed: {e}")
            return []


async def fetch_death_info(character_id: str) -> dict | None:
    """Query Deaths table for a character's death record.

    Args:
        character_id: UUID string of the character

    Returns dict with {cause, location, level, tick} or None.
    """
    b32 = uuid_to_bytes32_hex(character_id)
    sql_url = f"{MUD_INDEXER_URL}/api/sql"

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(sql_url, params={
                "query": f"SELECT * FROM memento__Deaths WHERE characterId = '{b32}'"
            })
            if resp.status_code == 200:
                data = resp.json()
                rows = data if isinstance(data, list) else data.get("rows", data.get("result", []))
                if rows and isinstance(rows, list) and len(rows) > 0:
                    row = rows[0]
                    return {
                        "cause": row.get("cause", ""),
                        "location": row.get("location", ""),
                        "level": int(row.get("level", 0)),
                        "tick": int(row.get("tick", 0)),
                    }
            return None
        except httpx.HTTPError as e:
            logger.warning(f"Death info query failed: {e}")
            return None
