# gateway/src/gateway/chain_client.py
"""MUD indexer HTTP client. Proxies reads from Redstone via the indexer service."""

import os
import httpx
import logging

logger = logging.getLogger(__name__)

MUD_INDEXER_URL = os.getenv("MUD_INDEXER_URL", "http://localhost:3333")

ALLOWED_TABLES = frozenset({
    "Characters", "Deaths", "Items",
    "Position", "EntitiesAtPosition", "Terrain",
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
    "Location": "Terrain",
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


MUD_WORLD_ADDRESS = os.getenv("MUD_WORLD_ADDRESS", "")
CHAIN_ID = 31337  # Local Anvil default


async def fetch_characters_by_wallet(wallet_address: str) -> list[dict]:
    """Query MUD indexer for all Characters owned by a wallet address.

    Fetches all store logs from the indexer, filters for Characters table
    entries matching the wallet address, and decodes the MUD-encoded data.
    Returns list of character dicts.
    """
    if not MUD_WORLD_ADDRESS:
        return []

    wallet_lower = wallet_address.lower()
    logs_url = f"{MUD_INDEXER_URL}/api/logs"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(logs_url, params={
                "input": f'{{"chainId":{CHAIN_ID},"address":"{MUD_WORLD_ADDRESS}","filters":[]}}'
            })
            if resp.status_code != 200:
                logger.warning(f"MUD indexer returned {resp.status_code}")
                return []

            data = resp.json()
            logs = data.get("logs", [])

            characters = []
            for log in logs:
                args = log.get("args", {})
                table_id = args.get("tableId", "")

                # Check if this is a Characters table entry
                # MUD encodes table names as bytes32 — "Characters" in memento namespace
                try:
                    table_name = bytes.fromhex(table_id.replace("0x", "")).rstrip(b"\x00").decode("utf-8", errors="ignore")
                except Exception:
                    continue

                if "Characters" not in table_name:
                    continue

                # Decode the static data (wallet, entityType, level, alive, createdAt)
                # ABI layout: address(20) + uint8(1) + uint32(4) + bool(1) + uint256(32) = 58 bytes
                static_data = args.get("staticData", "0x")
                key_tuple = args.get("keyTuple", [])
                dynamic_data = args.get("dynamicData", "0x")

                if not key_tuple:
                    continue

                char_id = key_tuple[0]

                try:
                    static_bytes = bytes.fromhex(static_data.replace("0x", ""))
                    if len(static_bytes) < 58:
                        continue

                    # Decode fields per MUD Characters schema:
                    # wallet: address (20 bytes)
                    char_wallet = "0x" + static_bytes[0:20].hex()
                    # entityType: uint8 (1 byte)
                    # entity_type = static_bytes[20]
                    # level: uint32 (4 bytes)
                    level = int.from_bytes(static_bytes[21:25], "big")
                    # alive: bool (1 byte)
                    alive = bool(static_bytes[25])
                    # createdAt: uint256 (32 bytes)
                    # created_at = int.from_bytes(static_bytes[26:58], "big")

                    # Decode dynamic data (name: string)
                    name = "Unknown"
                    try:
                        name_bytes = bytes.fromhex(dynamic_data.replace("0x", ""))
                        if name_bytes:
                            name = name_bytes.decode("utf-8", errors="ignore").rstrip("\x00")
                    except Exception:
                        pass

                    if char_wallet.lower() != wallet_lower:
                        continue

                    characters.append({
                        "player_id": bytes32_to_uuid(char_id),
                        "id_bytes32": char_id,
                        "player_name": name or "Unknown",
                        "level": max(level, 1),
                        "alive": alive,
                        "health": max(level, 1) * 100,
                        "archetype": "",
                    })
                except Exception as e:
                    logger.debug(f"Failed to decode character record: {e}")
                    continue

            return characters
        except httpx.HTTPError as e:
            logger.warning(f"MUD indexer query failed: {e}")
            return []


async def fetch_death_info(character_id: str) -> dict | None:
    """Query Deaths table for a character's death record.

    Scans indexer logs for Deaths table entries matching the character ID.
    Returns dict with {cause, location, level, tick} or None.
    """
    if not MUD_WORLD_ADDRESS:
        return None

    b32 = uuid_to_bytes32_hex(character_id)
    logs_url = f"{MUD_INDEXER_URL}/api/logs"

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(logs_url, params={
                "input": f'{{"chainId":{CHAIN_ID},"address":"{MUD_WORLD_ADDRESS}","filters":[]}}'
            })
            if resp.status_code != 200:
                return None

            data = resp.json()
            for log in data.get("logs", []):
                args = log.get("args", {})
                table_id = args.get("tableId", "")
                try:
                    table_name = bytes.fromhex(table_id.replace("0x", "")).rstrip(b"\x00").decode("utf-8", errors="ignore")
                except Exception:
                    continue

                if "Deaths" not in table_name:
                    continue

                # Deaths key is keccak256(characterId, timestamp) — check static data
                static_data = args.get("staticData", "0x")
                dynamic_data = args.get("dynamicData", "0x")

                try:
                    static_bytes = bytes.fromhex(static_data.replace("0x", ""))
                    # Deaths schema: characterId(32) + level(4) + tick(32) + timestamp(32) = 100 bytes
                    if len(static_bytes) < 68:
                        continue
                    death_char_id = "0x" + static_bytes[0:32].hex()
                    if death_char_id.rstrip("0") != b32.rstrip("0"):
                        continue

                    level = int.from_bytes(static_bytes[32:36], "big")
                    tick = int.from_bytes(static_bytes[36:68], "big")

                    # Dynamic data: cause(string) + location(string)
                    cause = ""
                    location = ""
                    try:
                        dyn_bytes = bytes.fromhex(dynamic_data.replace("0x", ""))
                        # MUD encodes dynamic fields with length prefixes
                        text = dyn_bytes.decode("utf-8", errors="ignore").rstrip("\x00")
                        parts = text.split("\x00")
                        if parts:
                            cause = parts[0]
                        if len(parts) > 1:
                            location = parts[1]
                    except Exception:
                        pass

                    return {
                        "cause": cause,
                        "location": location,
                        "level": level,
                        "tick": tick,
                    }
                except Exception:
                    continue

            return None
        except httpx.HTTPError as e:
            logger.warning(f"Death info query failed: {e}")
            return None


async def fetch_position(entity_id: str) -> dict | None:
    """Fetch entity position from onchain Position table."""
    hex_id = uuid_to_bytes32_hex(entity_id)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{MUD_INDEXER_URL}/api/tables/Position/{hex_id}")
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        logger.debug("Position fetch failed for %s", entity_id)
    return None


async def fetch_terrain(location_id: str) -> dict | None:
    """Fetch room terrain from onchain Terrain table."""
    hex_id = uuid_to_bytes32_hex(location_id)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{MUD_INDEXER_URL}/api/tables/Terrain/{hex_id}")
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        logger.debug("Terrain fetch failed for %s", location_id)
    return None


async def write_position(entity_id: str, location_id: str, x: int, y: int) -> bool:
    """Write entity position onchain via World contract."""
    try:
        from gateway.chain_writer import call_system
        return await call_system("memento__setPosition", [
            uuid_to_bytes32_hex(entity_id),
            uuid_to_bytes32_hex(location_id),
            x, y,
        ])
    except Exception:
        logger.warning("Position write failed for %s", entity_id, exc_info=True)
        return False


async def write_terrain(location_id: str, width: int, height: int, terrain_bytes: bytes) -> bool:
    """Write room terrain onchain via World contract."""
    try:
        from gateway.chain_writer import call_system
        return await call_system("memento__setTerrain", [
            uuid_to_bytes32_hex(location_id),
            width, height, terrain_bytes,
        ])
    except Exception:
        logger.warning("Terrain write failed for %s", location_id, exc_info=True)
        return False
