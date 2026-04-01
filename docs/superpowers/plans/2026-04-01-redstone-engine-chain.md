# Redstone Engine Chain Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a chain write layer to the Memento Mori engine that dual-writes game state to both the Bonfires KG and Redstone L2 (MUD tables). After each turn, fetch the Graphiti-extracted episode and push it onchain.

**Architecture:** A thin `chain.py` module wraps MUD system calls via web3.py. The 5 KG tools in `kg.py` are decorated to also fire chain writes. Post-turn, the engine polls for the latest Graphiti episode (async, with retry) then pushes it to Redstone. Gateway sends status events to the client via WebSocket.

**Tech Stack:** Python, web3.py, Bonfires SDK (episodes.latest), CrewAI, FastAPI

**Spec:** `docs/superpowers/specs/2026-04-01-redstone-integration-design.md`

**Depends on:**
- Plan A (contracts) — DONE, deployed locally
- Bonfires SDK `episodes.latest()` — DONE, added to bonfire-cli

---

## Task 1: Chain Configuration

**Files:**
- Create: `engine/src/memento/config/chain.py`

- [ ] **Step 1: Create chain config module**

```python
# engine/src/memento/config/chain.py
"""Redstone chain configuration. Reads from env vars."""

import os


REDSTONE_RPC = os.getenv("REDSTONE_RPC", "http://localhost:8545")
MUD_WORLD_ADDRESS = os.getenv("MUD_WORLD_ADDRESS", "")
ENGINE_PRIVATE_KEY = os.getenv("ENGINE_PRIVATE_KEY", "")
CHAIN_ENABLED = bool(MUD_WORLD_ADDRESS and ENGINE_PRIVATE_KEY)
```

- [ ] **Step 2: Add env vars to .env.example**

Append to the project's `.env` or `.env.example`:

```bash
# === Redstone Chain ===
REDSTONE_RPC=http://localhost:8545
MUD_WORLD_ADDRESS=
ENGINE_PRIVATE_KEY=
```

- [ ] **Step 3: Commit**

```bash
git add engine/src/memento/config/chain.py
git commit -m "feat(engine): add chain configuration for Redstone dual-write"
```

---

## Task 2: Chain Write Module

**Files:**
- Create: `engine/src/memento/tools/chain.py`

This is the core module. It wraps web3.py calls to the MUD World contract. All functions are fire-and-forget (async submission via threading) with graceful failure — if the chain is down, KG writes still succeed.

- [ ] **Step 1: Create chain.py**

```python
# engine/src/memento/tools/chain.py
"""Thin wrapper around MUD system calls on Redstone.

All functions are non-blocking — chain writes are submitted in a background
thread. If the chain is unavailable, errors are logged but never block gameplay.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid as _uuid
from typing import Any

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
    """Convert a UUID string to bytes32 for Solidity."""
    clean = uuid_str.replace("-", "").replace("kg:entity:", "")
    if len(clean) < 32:
        clean = clean.ljust(64, "0")
    return bytes.fromhex(clean[:64])


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

def register_character(uuid: str, name: str, wallet: str, level: int = 1) -> None:
    """Register a character onchain."""
    _send_tx(
        "registerCharacter",
        _uuid_to_bytes32(uuid),
        name,
        wallet or "0x0000000000000000000000000000000000000000",
        0,  # EntityType.Character
    )


def record_death(character_uuid: str, cause: str, location: str, level: int, tick: int) -> None:
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


def register_location(uuid: str, name: str, region: str, discoverer_wallet: str = "") -> None:
    """Register a location onchain."""
    _send_tx(
        "registerLocation",
        _uuid_to_bytes32(uuid),
        name,
        region,
        discoverer_wallet or "0x0000000000000000000000000000000000000000",
    )


def record_event(event_type: str, actors: list[str], location: str, summary: str, tick: int) -> None:
    """Record a world event onchain."""
    event_type_map = {
        "combat_outcome": 0, "quest_complete": 1, "npc_death": 2,
        "discovery": 3, "faction_change": 4, "death": 5, "game_event": 6,
    }
    _send_tx(
        "recordEvent",
        _uuid_to_bytes32(_uuid.uuid4().hex),
        event_type_map.get(event_type, 6),  # default to GameEvent
        ",".join(actors),
        location,
        summary[:500],  # truncate to avoid gas issues
        tick,
    )


def record_episode(
    uuid: str,
    name: str,
    summary: str,
    entities: list[dict],
    edges: list[dict],
    tick: int,
) -> None:
    """Record a Graphiti episode onchain with extracted entities and edges as JSON."""
    _send_tx(
        "recordEpisode",
        _uuid_to_bytes32(uuid),
        name[:200],
        summary[:1000],
        json.dumps(entities, default=str)[:2000],
        json.dumps(edges, default=str)[:2000],
        tick,
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


def update_reputation(wallet: str, faction_uuid: str, delta: int) -> None:
    """Update faction reputation onchain."""
    _send_tx(
        "updateReputation",
        wallet,
        _uuid_to_bytes32(faction_uuid),
        delta,
    )


def is_enabled() -> bool:
    """Check if chain writes are enabled."""
    from memento.config.chain import CHAIN_ENABLED
    return CHAIN_ENABLED
```

- [ ] **Step 2: Verify module loads**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine
PYTHONPATH=src python -c "from memento.tools.chain import is_enabled; print('enabled:', is_enabled())"
```

Expected: `enabled: False` (no env vars set)

- [ ] **Step 3: Commit**

```bash
git add engine/src/memento/tools/chain.py
git commit -m "feat(engine): add chain write module for Redstone MUD calls"
```

---

## Task 3: Decorate KG Tools with Chain Writes

**Files:**
- Modify: `engine/src/memento/tools/kg.py`

Add chain calls after successful KG writes. Chain calls are non-blocking (fire-and-forget threads), so they don't slow down the game loop.

- [ ] **Step 1: Add chain imports and calls to kg.py**

At the top of `engine/src/memento/tools/kg.py`, add:

```python
from memento.tools import chain as _chain
```

Then add chain calls inside the existing tool functions:

In `create_entity` (after the `return` line that returns the UUID string), add before the return:

```python
    # Chain dual-write
    if _chain.is_enabled():
        entity_type_lower = entity_type.lower()
        if entity_type_lower in ("character", "player", "npc"):
            _chain.register_character(uuid, name, "", 1)
        elif entity_type_lower in ("item", "weapon", "armor", "consumable"):
            _chain.register_item(uuid, name, summary[:50], "", "")
        elif entity_type_lower in ("location", "room", "region"):
            _chain.register_location(uuid, name, summary[:50], "")
```

In `create_edge` (after the successful return), add before the return:

```python
    # Chain dual-write for death edges
    if _chain.is_enabled() and relationship.upper() in ("DIED_AT", "KILLED_BY"):
        _chain.record_death(source_uuid or "", fact, target_name, 0, 0)
```

In `mark_status` (after the successful return), add before the return:

```python
    # Chain dual-write for death status
    if _chain.is_enabled() and status.lower() == "dead":
        _chain.record_death(entity_uuid or "", cause, "", 0, 0)
```

In `remember_event` (after the sync call), add:

```python
    # Chain dual-write
    if _chain.is_enabled():
        _chain.record_event("game_event", [], "", summary, 0)
```

- [ ] **Step 2: Read the current kg.py to get exact line numbers and variable names before editing**

Read `engine/src/memento/tools/kg.py` fully and verify the exact variable names used in each function. The chain calls must use the same variables.

- [ ] **Step 3: Verify module loads**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine
PYTHONPATH=src python -c "from memento.tools.kg import create_entity; print('ok')"
```

- [ ] **Step 4: Commit**

```bash
git add engine/src/memento/tools/kg.py
git commit -m "feat(engine): add chain dual-write to KG tools"
```

---

## Task 4: Post-Turn Episode Sync

**Files:**
- Modify: `engine/src/memento/flows/game_turn.py`

After the turn completes and Graphiti processes the episode, poll for the latest episode and push it onchain. The polling is needed because `sync()` returns immediately but Graphiti extraction is async.

- [ ] **Step 1: Add episode sync to post_turn**

Read `engine/src/memento/flows/game_turn.py`. The `post_turn` method is the last step in the flow. Add after the existing time advancement code:

```python
        # Chain: fetch latest Graphiti episode and push onchain
        if _chain.is_enabled():
            self._sync_episode_to_chain()

    def _sync_episode_to_chain(self) -> None:
        """Poll for the latest Graphiti episode and push to Redstone."""
        import time
        from memento.bonfires_client import get_client
        from memento.tools import chain as _chain

        try:
            client = get_client()
            # Poll for up to 10 seconds (Graphiti extraction is usually <2s)
            latest = None
            for _ in range(5):
                time.sleep(2)
                episodes = client.kg.search("", num_results=1)
                ep_list = episodes.get("episodes", [])
                if ep_list:
                    latest = ep_list[0]
                    break

            if not latest:
                return

            # Extract structured data from episode
            ep_uuid = latest.get("uuid", "")
            ep_name = latest.get("name", "")
            content = latest.get("content", {})
            ep_summary = content.get("content", "") if isinstance(content, dict) else str(content)

            # Get entities and edges from the search context
            entities = episodes.get("entities", [])
            edges = episodes.get("edges", [])

            entity_list = [
                {"uuid": e.get("uuid", ""), "name": e.get("name", ""), "labels": e.get("labels", [])}
                for e in entities[:20]  # cap to avoid gas issues
            ]
            edge_list = [
                {"source": e.get("source_node_name", ""), "target": e.get("target_node_name", ""),
                 "relationship": e.get("name", ""), "fact": e.get("fact", "")}
                for e in edges[:20]
            ]

            tick = self.state.world_time.get("tick", 0) if isinstance(self.state.world_time, dict) else 0
            _chain.record_episode(ep_uuid, ep_name, ep_summary, entity_list, edge_list, tick)

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Episode chain sync failed: {e}")
```

- [ ] **Step 2: Verify the flow still runs**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine
PYTHONPATH=src python -c "from memento.flows.game_turn import GameTurnFlow; print('ok')"
```

- [ ] **Step 3: Commit**

```bash
git add engine/src/memento/flows/game_turn.py
git commit -m "feat(engine): post-turn episode sync to Redstone chain"
```

---

## Task 5: Gateway Status Events

**Files:**
- Modify: `gateway/src/gateway/ws.py` (or wherever WebSocket messages are sent)

Send `{ type: 'status', phase: '...' }` messages to the client WebSocket during the chain sync pipeline. The client's status bar already handles these.

- [ ] **Step 1: Read the current ws.py to understand how messages are sent**

Read `gateway/src/gateway/ws.py` to find the `send_to_player` or equivalent function.

- [ ] **Step 2: Add status phase messages**

The Matrix bridge receives engine output and forwards to WebSocket. Add status messages at key points:

Before sending narrative to client:
```python
await ws_hub.send_to_player(player_id, {"type": "status", "phase": "extracting"})
```

After narrative sent, before chain sync would happen (engine-side):
```python
await ws_hub.send_to_player(player_id, {"type": "status", "phase": "pushing"})
```

After everything is done:
```python
await ws_hub.send_to_player(player_id, {"type": "status", "phase": "synced"})
```

Note: The exact integration depends on where the Matrix bridge processes engine responses. Read the code first.

- [ ] **Step 3: Commit**

```bash
git add gateway/
git commit -m "feat(gateway): send chain sync status events to client WebSocket"
```

---

## Task 6: Session Chain Integration

**Files:**
- Modify: `engine/src/memento/session.py`
- Modify: `gateway/src/gateway/routes/session.py`

Wire chain writes into character creation and death handling.

- [ ] **Step 1: Add chain calls to session.py**

In `create_player`, after the KG entity is created:
```python
from memento.tools import chain as _chain
if _chain.is_enabled():
    _chain.register_character(uuid, player_name, "", 1)
```

In `handle_death`, after the KG edges are created:
```python
from memento.tools import chain as _chain
if _chain.is_enabled():
    _chain.record_death(player_id, cause, location, 0, 0)
```

- [ ] **Step 2: Add optional wallet_address to CreateSessionRequest**

In `gateway/src/gateway/routes/session.py`, add to `CreateSessionRequest`:
```python
wallet_address: str = ""
```

Pass it through to `create_player` (for future use when wallet connect is added to the client).

- [ ] **Step 3: Commit**

```bash
git add engine/src/memento/session.py gateway/src/gateway/routes/session.py
git commit -m "feat(engine): chain writes on character creation and death"
```

---

## Task 7: Add web3.py Dependency

**Files:**
- Modify: `engine/requirements.txt` or `pyproject.toml`

- [ ] **Step 1: Add web3 to engine dependencies**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine
echo "web3>=6.0.0" >> requirements.txt
pip install web3>=6.0.0
```

Or if using pyproject.toml, add to dependencies.

- [ ] **Step 2: Commit**

```bash
git add engine/requirements.txt
git commit -m "chore(engine): add web3.py dependency for chain writes"
```

---

## Task 8: Integration Test — Local Anvil

**Files:**
- Create: `engine/tests/test_chain.py`

- [ ] **Step 1: Write integration test**

```python
# engine/tests/test_chain.py
"""Integration test: chain writes against local anvil.

Requires anvil running on port 8545 with contracts deployed.
Skip if anvil not available.
"""

import os
import pytest

# Skip if no chain config
pytestmark = pytest.mark.skipif(
    not os.getenv("MUD_WORLD_ADDRESS"),
    reason="MUD_WORLD_ADDRESS not set — skip chain tests",
)


def test_chain_module_loads():
    from memento.tools.chain import is_enabled
    assert isinstance(is_enabled(), bool)


def test_uuid_to_bytes32():
    from memento.tools.chain import _uuid_to_bytes32
    result = _uuid_to_bytes32("c800dabf-b1ef-4033-a594-b1d7f80ee316")
    assert len(result) == 32
    assert isinstance(result, bytes)


def test_register_character_does_not_raise():
    """Smoke test — just verify it doesn't crash. Actual chain verification needs cast."""
    from memento.tools.chain import register_character
    # This fires a background thread. With chain disabled, it should be a no-op.
    register_character("test-uuid", "TestHero", "", 1)
```

- [ ] **Step 2: Run tests**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine
PYTHONPATH=src pytest tests/test_chain.py -v
```

- [ ] **Step 3: Commit**

```bash
git add engine/tests/test_chain.py
git commit -m "test(engine): add chain module integration tests"
```

---

## Task 9: Update .env with Local Anvil Config

**Files:**
- Modify: `/home/at0x/Vaults/Bonfires/memento-mori/.env`

- [ ] **Step 1: Add chain env vars for local development**

After deploying contracts to local anvil (from Plan A), get the world address from `contracts/packages/contracts/worlds.json` and add to `.env`:

```bash
# Read world address from deployment
WORLD_ADDR=$(python3 -c "import json; print(json.load(open('contracts/packages/contracts/worlds.json')).get('31337',{}).get('address',''))")

# Append to .env (don't commit .env!)
cat >> .env << EOF

# === Redstone Chain (local anvil) ===
REDSTONE_RPC=http://localhost:8545
MUD_WORLD_ADDRESS=$WORLD_ADDR
ENGINE_PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
EOF
```

- [ ] **Step 2: Verify chain is enabled**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine
source ../.env
PYTHONPATH=src python -c "from memento.tools.chain import is_enabled; print('chain enabled:', is_enabled())"
```

Expected: `chain enabled: True`

- [ ] **Step 3: Do NOT commit .env — just verify it works**
