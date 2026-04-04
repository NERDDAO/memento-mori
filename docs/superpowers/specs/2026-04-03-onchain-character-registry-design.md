# Onchain Character Registry + Local Chain Dev

**Date**: 2026-04-03

## Context

Character resume (wallet → character lookup) is broken because the KG text search is unreliable for structured lookups — it returns unrelated entities instead of the User entity that owns the characters. Characters are already registered onchain via `chain.register_character()` with their wallet address stored in the MUD `Characters` table. The onchain data is deterministic and queryable by wallet — no text search needed.

This spec adds a local chain dev environment (Anvil + MUD store-indexer) and rewires character resume to use onchain data as the source of truth.

## 1. Dev Stack: `./dev.sh chain`

### Docker Services

Add to `docker-compose.dev.yml`:

**Anvil** (local Ethereum node):
- Image: `ghcr.io/foundry-rs/foundry:latest`
- Command: `anvil --host 0.0.0.0 --block-time 2`
- Port: 8545
- Healthcheck: `cast chain-id --rpc-url http://localhost:8545`

**MUD Store Indexer** (chain state reader):
- Image: `ghcr.io/latticexyz/store-indexer:latest`
- Port: 3001
- Env: `RPC_HTTP_URL=http://anvil:8545`, `FOLLOW_BLOCK_TAG=latest`, `SQLITE_FILENAME=/data/indexer.db`
- Depends on: anvil
- Volume: `mud-indexer-data:/data`

### dev.sh Integration

New mode: `./dev.sh chain`
- Starts Docker infra (mongo, neo4j, weaviate) + anvil + mud-indexer
- Waits for Anvil healthcheck
- Deploys contracts: `cd memento-mori/contracts/packages/contracts && pnpm install && pnpm deploy:local`
- Parses `MUD_WORLD_ADDRESS` from deploy output
- Writes chain env vars to `memento-mori/.env.dev`:
  ```
  REDSTONE_RPC=http://localhost:8545
  MUD_WORLD_ADDRESS=<deployed address>
  ENGINE_PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
  MUD_INDEXER_URL=http://localhost:3001
  ```
- Then starts delve + bonfires-ai + webapp (same as `./dev.sh all`)

`./dev.sh all` remains unchanged — no chain services.

### Prerequisites

- Foundry (`forge`, `cast`, `anvil`) installed
- pnpm installed
- Node 20+

## 2. Gateway Chain Read Path

### New function in `gateway/src/gateway/chain_client.py`

```python
async def fetch_characters_by_wallet(wallet_address: str) -> list[dict]:
    """Query MUD indexer for all Characters owned by a wallet address.
    
    Returns list of {id (UUID string), name, wallet, level, alive, createdAt}.
    """
```

**Implementation:**
- Query the MUD store-indexer's SQL API endpoint
- The store-indexer supports queries via `POST /api/logs` or `GET /api/tables/:tableId` with query params
- Filter `Characters` table rows where `wallet` field matches the wallet address
- Convert `bytes32` ids back to UUID strings via hex-stripping and dash-insertion
- Return structured list

### Death info lookup

```python
async def fetch_death_info(character_id_bytes32: str) -> dict | None:
    """Query Deaths table for a character's death record."""
```

- Query `Deaths` table, filter by `characterId == character_id_bytes32`
- Returns `{cause, location, level, tick, timestamp}` or None

## 3. Character Resume Route

### Modified `/api/session/characters` in `gateway/src/gateway/routes/session.py`

```python
@router.post("/session/characters")
async def list_characters(req: CharactersRequest):
    from gateway.chain_client import fetch_characters_by_wallet, fetch_death_info
    from memento.config.chain import CHAIN_ENABLED
    
    if CHAIN_ENABLED:
        # Onchain path: query MUD indexer
        characters = await fetch_characters_by_wallet(req.wallet_address)
        for char in characters:
            if not char.get("alive", True):
                death = await fetch_death_info(char["id_bytes32"])
                if death:
                    char["is_dead"] = True
                    char["death_cause"] = death.get("cause", "")
                    char["death_location"] = death.get("location", "")
                else:
                    char["is_dead"] = True
                    char["death_cause"] = ""
                    char["death_location"] = ""
            else:
                char["is_dead"] = False
        return {"characters": characters}
    else:
        # Fallback: KG-based lookup (unreliable but works when chain is off)
        from memento.session import SessionManager
        sm = SessionManager()
        characters = await asyncio.to_thread(sm.get_user_characters, req.wallet_address)
        return {"characters": characters}
```

### Data flow

```
Client: POST /api/session/characters {wallet_address}
  ↓
Gateway: CHAIN_ENABLED?
  ├─ YES → fetch_characters_by_wallet(wallet) via MUD indexer HTTP
  │        → for dead chars: fetch_death_info(characterId)
  │        → return [{player_id, player_name, level, alive, is_dead, death_cause, death_location}]
  └─ NO  → SessionManager.get_user_characters(wallet) via KG search (fallback)
  ↓
Client: show character picker (alive + memorial dead)
  ↓
Client: user selects character → POST /api/session/join {player_id}
  ↓
Gateway: SessionManager.restore_player_state(player_id) via KG UUID lookup
  → return full game state (location, room_map, inventory, quests)
```

The chain handles the wallet→character registry (deterministic). The KG handles rich game state (inventory, quests, room_map) via UUID lookup (reliable).

## 4. UUID ↔ bytes32 Conversion

Existing `uuid_to_bytes32_hex()` in `chain_client.py` handles UUID → bytes32.

Add reverse:
```python
def bytes32_to_uuid(hex_str: str) -> str:
    """Convert 0x-prefixed bytes32 hex back to UUID string."""
    clean = hex_str.replace("0x", "").rstrip("0")
    # Pad to 32 hex chars (standard UUID without dashes)
    if len(clean) <= 32:
        clean = clean.ljust(32, "0")
    return f"{clean[:8]}-{clean[8:12]}-{clean[12:16]}-{clean[16:20]}-{clean[20:32]}"
```

## 5. Env Vars Summary

| Variable | Dev value | Purpose |
|----------|-----------|---------|
| `REDSTONE_RPC` | `http://localhost:8545` | Anvil RPC |
| `MUD_WORLD_ADDRESS` | `<from deploy>` | Deployed world contract |
| `ENGINE_PRIVATE_KEY` | `0xac0974...` (Anvil default) | Engine wallet for writes |
| `MUD_INDEXER_URL` | `http://localhost:3001` | Store-indexer HTTP |
| `CHAIN_ENABLED` | Auto (`true` when address + key set) | Feature flag |

## 6. Files Modified/Created

| File | Action | What |
|------|--------|------|
| `docker-compose.dev.yml` | Modify | Add anvil + mud-indexer services |
| `dev.sh` | Modify | Add `chain` mode with deploy step |
| `gateway/src/gateway/chain_client.py` | Modify | Add `fetch_characters_by_wallet`, `fetch_death_info`, `bytes32_to_uuid` |
| `gateway/src/gateway/routes/session.py` | Modify | Onchain path in `/session/characters` |
| `memento-mori/.env.chain.example` | Exists | Already has correct values |

## 7. Verification

1. `./dev.sh chain` — Anvil starts, contracts deploy, indexer starts, world address written to .env.dev
2. Create a character in the game — verify it appears in MUD indexer (`curl http://localhost:3001/api/...`)
3. Disconnect, reconnect with same wallet — character picker shows the character from onchain data
4. Kill a character — death record appears onchain, memorial shows in picker
5. `./dev.sh all` (no chain) — character resume falls back to KG search, still works (unreliably)
