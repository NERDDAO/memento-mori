# Onchain Character Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add local chain dev environment (Anvil + MUD indexer) and rewire character resume to use onchain data instead of unreliable KG text search.

**Architecture:** Add Anvil + MUD store-indexer to Docker Compose, auto-deploy contracts via `dev.sh chain`, gateway queries indexer for wallet→character mapping, falls back to KG when chain is disabled.

**Tech Stack:** Anvil (Foundry), MUD store-indexer (SQLite mode), httpx (Python HTTP client), Docker Compose

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `docker-compose.dev.yml` | Modify | Add anvil + mud-indexer services |
| `dev.sh` | Modify | Add `chain` mode with contract deploy |
| `gateway/src/gateway/chain_client.py` | Modify | Add `fetch_characters_by_wallet`, `fetch_death_info`, `bytes32_to_uuid` |
| `gateway/src/gateway/routes/session.py` | Modify | Onchain path in `/session/characters` |
| `engine/src/memento/config/chain.py` | Modify | Add `MUD_INDEXER_URL` config |

---

### Task 1: Add Anvil + MUD Indexer to Docker Compose

**Files:**
- Modify: `docker-compose.dev.yml`

- [ ] **Step 1: Add anvil and mud-indexer services**

Add the following services to `docker-compose.dev.yml`, before the `volumes:` section:

```yaml
  # Local Ethereum chain (Foundry Anvil)
  anvil:
    image: ghcr.io/foundry-rs/foundry:latest
    entrypoint: ["anvil", "--host", "0.0.0.0", "--block-time", "2"]
    ports:
      - "8545:8545"
    profiles:
      - chain

  # MUD Store Indexer — indexes onchain MUD tables for query
  mud-indexer:
    image: ghcr.io/latticexyz/store-indexer:latest
    entrypoint: ["pnpm", "sqlite-indexer"]
    ports:
      - "3333:3333"
    environment:
      RPC_HTTP_URL: "http://anvil:8545"
      FOLLOW_BLOCK_TAG: "latest"
      SQLITE_FILENAME: "/data/indexer.db"
      PORT: "3333"
      ENABLE_UNSAFE_QUERY_API: "true"
    volumes:
      - mud_indexer_data:/data
    depends_on:
      - anvil
    profiles:
      - chain
```

And add the volume to the `volumes:` section:

```yaml
  mud_indexer_data:
```

The `profiles: [chain]` means these services only start when explicitly requested.

- [ ] **Step 2: Verify compose config parses**

Run: `docker compose -f /home/at0x/Vaults/Bonfires/docker-compose.dev.yml config --profiles chain 2>&1 | grep -E "anvil|mud-indexer" | head -5`
Expected: Shows both services

- [ ] **Step 3: Commit**

```bash
cd /home/at0x/Vaults/Bonfires
git add docker-compose.dev.yml
git commit -m "infra: add anvil + MUD store-indexer to docker-compose (chain profile)"
```

---

### Task 2: Add `chain` mode to dev.sh

**Files:**
- Modify: `dev.sh`

- [ ] **Step 1: Add chain variables and deploy function**

After the `start_webapp()` function (around line 158), add:

```bash
start_chain() {
  echo -e "${CYAN}Starting chain services (anvil + mud-indexer)...${NC}"
  docker compose -f "$COMPOSE_FILE" --profile chain up -d anvil mud-indexer

  echo -e "${CYAN}Waiting for Anvil on :8545...${NC}"
  for i in {1..30}; do
    if cast chain-id --rpc-url http://localhost:8545 2>/dev/null; then
      echo -e "${GREEN}Anvil ready (chain $(cast chain-id --rpc-url http://localhost:8545)).${NC}"
      break
    fi
    sleep 1
  done

  # Deploy MUD contracts
  echo -e "${CYAN}Deploying MUD contracts...${NC}"
  local MM_DIR="$ROOT/memento-mori"
  local CONTRACTS_DIR="$MM_DIR/contracts/packages/contracts"
  if [ ! -d "$CONTRACTS_DIR/node_modules" ]; then
    echo -e "${YELLOW}Installing contract dependencies...${NC}"
    (cd "$MM_DIR/contracts" && pnpm install)
  fi

  local DEPLOY_OUTPUT
  DEPLOY_OUTPUT=$(cd "$CONTRACTS_DIR" && pnpm deploy:local 2>&1)
  echo "$DEPLOY_OUTPUT" | tail -5

  # Extract world address from deploy output
  local WORLD_ADDR
  WORLD_ADDR=$(echo "$DEPLOY_OUTPUT" | grep -oP '0x[a-fA-F0-9]{40}' | tail -1)
  if [ -z "$WORLD_ADDR" ]; then
    echo -e "${RED}Failed to extract MUD_WORLD_ADDRESS from deploy output${NC}"
    echo "$DEPLOY_OUTPUT"
    return 1
  fi
  echo -e "${GREEN}MUD World deployed at: $WORLD_ADDR${NC}"

  # Write chain env vars to memento-mori/.env.dev
  local ENV_FILE="$MM_DIR/.env.dev"
  # Remove existing chain vars (commented or not)
  sed -i '/^#\?\s*REDSTONE_RPC=/d' "$ENV_FILE"
  sed -i '/^#\?\s*MUD_WORLD_ADDRESS=/d' "$ENV_FILE"
  sed -i '/^#\?\s*ENGINE_PRIVATE_KEY=/d' "$ENV_FILE"
  sed -i '/^#\?\s*MUD_INDEXER_URL=/d' "$ENV_FILE"

  # Append active chain vars
  cat >> "$ENV_FILE" << CHAIN_EOF

# Chain config (auto-set by dev.sh chain)
REDSTONE_RPC=http://localhost:8545
MUD_WORLD_ADDRESS=$WORLD_ADDR
ENGINE_PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
MUD_INDEXER_URL=http://localhost:3333
CHAIN_EOF

  echo -e "${GREEN}Chain config written to memento-mori/.env.dev${NC}"
  echo -e "  Anvil:     ${GREEN}localhost:8545${NC}"
  echo -e "  Indexer:   ${GREEN}localhost:3333${NC}"
  echo -e "  World:     ${GREEN}$WORLD_ADDR${NC}"
  echo ""
}
```

- [ ] **Step 2: Add chain case to the mode switch**

In the `case "$MODE" in` block (around line 169), add before the `*` default case:

```bash
  chain)
    use_dev_env
    start_infra
    start_chain
    start_delve
    sleep 3
    start_agents
    start_webapp
    ;;
```

- [ ] **Step 3: Update usage comment**

At the top of `dev.sh`, update the usage comment to include:
```bash
#   ./dev.sh chain        # all + anvil chain + MUD indexer + contract deploy
```

And update the `*` case:
```bash
    echo "Usage: $0 [all|chain|delve|agents|webapp|infra|seed|down|reset]"
```

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires
git add dev.sh
git commit -m "feat: add ./dev.sh chain mode with Anvil + MUD deploy + indexer"
```

---

### Task 3: Add MUD_INDEXER_URL to engine chain config

**Files:**
- Modify: `engine/src/memento/config/chain.py`

- [ ] **Step 1: Add MUD_INDEXER_URL**

Add after line 10 (`CHAIN_ENABLED = ...`):

```python
MUD_INDEXER_URL = os.getenv("MUD_INDEXER_URL", "http://localhost:3333")
```

- [ ] **Step 2: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/config/chain.py
git commit -m "feat(engine): add MUD_INDEXER_URL config"
```

---

### Task 4: Add onchain read functions to chain_client.py

**Files:**
- Modify: `gateway/src/gateway/chain_client.py`

- [ ] **Step 1: Add bytes32_to_uuid conversion**

Add after the existing `uuid_to_bytes32_hex` function (after line 37):

```python
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
```

- [ ] **Step 2: Add fetch_characters_by_wallet**

Add after `entity_exists_onchain` (after line 74):

```python
async def fetch_characters_by_wallet(wallet_address: str) -> list[dict]:
    """Query MUD indexer for all Characters owned by a wallet address.
    
    Queries the indexer's tRPC getLogs endpoint for Characters table records,
    then filters by wallet address. Returns list of character dicts.
    """
    import json as _json

    # The MUD store-indexer tRPC endpoint for fetching table records
    url = f"{MUD_INDEXER_URL}/trpc/getLogs"

    # Query params: fetch all records from the Characters table
    # The indexer uses tRPC batch format
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Try the SQL API first (requires ENABLE_UNSAFE_QUERY_API=true on indexer)
            sql_url = f"{MUD_INDEXER_URL}/api/sql"
            resp = await client.get(sql_url, params={
                "query": f"SELECT * FROM memento__Characters WHERE wallet = '{wallet_address.lower()}'"
            })
            if resp.status_code == 200:
                rows = resp.json()
                return _parse_character_rows(rows, wallet_address)
        except httpx.HTTPError:
            pass

        # Fallback: fetch all characters via tRPC and filter client-side
        try:
            resp = await client.post(url, json={
                "0": {
                    "json": {
                        "input": {
                            "tableIds": [],  # empty = all tables
                        }
                    }
                }
            })
            if resp.status_code == 200:
                data = resp.json()
                # Parse tRPC response format
                records = data.get("0", {}).get("result", {}).get("data", {}).get("json", {}).get("logs", [])
                characters = []
                for record in records:
                    if "Characters" not in record.get("args", {}).get("tableId", ""):
                        continue
                    value = record.get("args", {}).get("staticData", {})
                    if not value:
                        continue
                    # Decode and filter by wallet
                    char = _decode_character_record(record)
                    if char and char.get("wallet", "").lower() == wallet_address.lower():
                        characters.append(char)
                return characters
        except httpx.HTTPError as e:
            logger.warning(f"MUD indexer query failed: {e}")
            return []

    return []


def _parse_character_rows(rows: list | dict, wallet_address: str) -> list[dict]:
    """Parse SQL API response rows into character dicts."""
    if isinstance(rows, dict):
        rows = rows.get("rows", rows.get("result", []))
    characters = []
    for row in rows:
        if isinstance(row, dict):
            char_wallet = row.get("wallet", "")
            if char_wallet.lower() == wallet_address.lower():
                characters.append({
                    "player_id": bytes32_to_uuid(row.get("id", "")),
                    "id_bytes32": row.get("id", ""),
                    "player_name": row.get("name", "Unknown"),
                    "level": int(row.get("level", 1)),
                    "alive": bool(row.get("alive", True)),
                    "health": int(row.get("level", 1)) * 100,  # Estimate from level
                })
    return characters


def _decode_character_record(record: dict) -> dict | None:
    """Decode a tRPC log record into a character dict."""
    try:
        args = record.get("args", {})
        key_tuple = args.get("keyTuple", [])
        if not key_tuple:
            return None
        char_id = key_tuple[0] if key_tuple else ""
        # The static/encoded data needs ABI decoding — for now return raw
        return {
            "player_id": bytes32_to_uuid(char_id),
            "id_bytes32": char_id,
            "player_name": "",  # Needs ABI decode
            "level": 1,
            "alive": True,
            "wallet": "",
        }
    except Exception:
        return None


async def fetch_death_info(character_id: str) -> dict | None:
    """Query Deaths table for a character's death record.
    
    Args:
        character_id: UUID string of the character
    
    Returns dict with {cause, location, level, tick} or None.
    """
    b32 = uuid_to_bytes32_hex(character_id)
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            # Try SQL API
            sql_url = f"{MUD_INDEXER_URL}/api/sql"
            resp = await client.get(sql_url, params={
                "query": f"SELECT * FROM memento__Deaths WHERE characterId = '{b32}'"
            })
            if resp.status_code == 200:
                rows = resp.json()
                if isinstance(rows, dict):
                    rows = rows.get("rows", rows.get("result", []))
                if rows:
                    row = rows[0] if isinstance(rows, list) else rows
                    return {
                        "cause": row.get("cause", ""),
                        "location": row.get("location", ""),
                        "level": int(row.get("level", 0)),
                        "tick": int(row.get("tick", 0)),
                    }
        except httpx.HTTPError as e:
            logger.warning(f"Death info query failed: {e}")

        # Fallback: try direct record lookup if we have a death ID
        # Deaths are keyed by keccak256(characterId, timestamp), so we can't do direct lookup
        # without knowing the timestamp. SQL query is the primary path.
        return None
```

- [ ] **Step 3: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add gateway/src/gateway/chain_client.py
git commit -m "feat(gateway): add onchain character lookup via MUD indexer"
```

---

### Task 5: Wire onchain path into /session/characters route

**Files:**
- Modify: `gateway/src/gateway/routes/session.py`

- [ ] **Step 1: Update list_characters to use onchain path when enabled**

Replace the `list_characters` function (currently around lines 114-124):

```python
@router.post("/session/characters")
async def list_characters(req: CharactersRequest):
    """List existing characters for a wallet address.
    
    When chain is enabled, queries the MUD indexer for authoritative
    wallet→character mapping. Falls back to KG search when chain is off.
    """
    from memento.config.chain import CHAIN_ENABLED

    if CHAIN_ENABLED:
        # Onchain path: query MUD indexer (authoritative)
        from gateway.chain_client import fetch_characters_by_wallet, fetch_death_info
        try:
            characters = await fetch_characters_by_wallet(req.wallet_address)
            for char in characters:
                if not char.get("alive", True):
                    death = await fetch_death_info(char["player_id"])
                    char["is_dead"] = True
                    char["death_cause"] = death.get("cause", "") if death else ""
                    char["death_location"] = death.get("location", "") if death else ""
                else:
                    char["is_dead"] = False
                    char["death_cause"] = ""
                    char["death_location"] = ""
            return {"characters": characters}
        except Exception:
            logger.warning("Onchain character lookup failed, falling back to KG", exc_info=True)

    # Fallback: KG-based lookup
    try:
        from memento.session import SessionManager
        sm = SessionManager()
        characters = await asyncio.to_thread(sm.get_user_characters, req.wallet_address)
        return {"characters": characters}
    except Exception:
        logger.warning("Character list failed", exc_info=True)
        return {"characters": []}
```

- [ ] **Step 2: Verify gateway imports**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/gateway && python -c "from gateway.routes.session import router; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add gateway/src/gateway/routes/session.py
git commit -m "feat(gateway): use onchain character lookup when chain is enabled"
```

---

### Task 6: End-to-End Verification

- [ ] **Step 1: Start chain dev environment**

Run: `cd /home/at0x/Vaults/Bonfires && ./dev.sh chain`

Expected:
- Anvil starts on :8545
- Contracts deploy, world address printed
- MUD indexer starts on :3333
- Chain env vars written to memento-mori/.env.dev
- Delve, bonfires-ai, webapp start

- [ ] **Step 2: Start memento-mori**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori && ./start.sh --dev`

Expected: Gateway starts with `CHAIN_ENABLED=true` (env vars set by dev.sh)

- [ ] **Step 3: Create a character and verify onchain registration**

Create a character in the game. Check the indexer:

```bash
curl -s "http://localhost:3333/api/sql?query=SELECT%20*%20FROM%20memento__Characters" | python3 -m json.tool
```

Expected: Character appears in indexer with correct wallet address.

- [ ] **Step 4: Test character resume**

Disconnect and reconnect with same wallet. The character picker should show the character from onchain data.

- [ ] **Step 5: Commit any fixes**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add -A
git commit -m "fix: address e2e verification issues for onchain character registry"
```
