# Plan C: Client Onchain UX — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add mandatory wallet connection, gateway-proxied MUD indexer reads, canonical entity verification, and wiki onchain tab to the Memento Mori client.

**Architecture:** Two-step character creation (wallet connect → name), gateway chain proxy endpoint `/api/chain/{table}/{id}` backed by MUD indexer, canonical entity filtering on all entity endpoints, wiki Lore/Chain tab system. Status bar is already complete.

**Tech Stack:** TypeScript/Bun (client), FastAPI/Python (gateway), EIP-1193 `window.ethereum` (wallet), `httpx` (gateway→indexer proxy)

**Spec:** `docs/superpowers/specs/2026-04-01-client-onchain-ux-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `client/src/chain/wallet.ts` | Wallet connection logic (EIP-1193), address formatting |
| `gateway/src/gateway/routes/chain.py` | `/api/chain/{table}/{id}` — proxy MUD indexer reads |
| `gateway/src/gateway/chain_client.py` | MUD indexer HTTP client, UUID→bytes32 conversion, table validation |
| `gateway/tests/test_chain_route.py` | Tests for chain route + canonical verification |

### Modified Files
| File | Change |
|------|--------|
| `client/index.html` | Two-step overlay HTML + wallet CSS |
| `client/src/app.ts` | Wallet gate flow, pass wallet to `initSession()` |
| `client/src/state/session.ts` | `walletAddress` on `Session`, send in POST body |
| `client/src/ui/wiki.ts` | Tab bar (Lore/Chain), chain data fetch + render per entity type |
| `gateway/src/gateway/app.py` | Register chain router |
| `gateway/src/gateway/routes/session.py` | `wallet_address` required on `CreateSessionRequest` |
| `gateway/src/gateway/routes/entity.py` | Canonical entity verification filter |
| `engine/src/memento/session.py` | Pass `wallet_address` through to `chain.register_character()` |

---

## Task 1: Wallet Module (`client/src/chain/wallet.ts`)

**Files:**
- Create: `client/src/chain/wallet.ts`

- [ ] **Step 1: Create wallet module**

```typescript
// client/src/chain/wallet.ts
/**
 * Wallet connection via EIP-1193 (window.ethereum).
 * No library dependencies — raw provider API.
 */

declare global {
  interface Window {
    ethereum?: {
      request(args: { method: string; params?: unknown[] }): Promise<unknown>;
      on(event: string, handler: (...args: unknown[]) => void): void;
      removeListener(event: string, handler: (...args: unknown[]) => void): void;
    };
  }
}

let connectedAddress: string | null = null;

export function hasProvider(): boolean {
  return typeof window.ethereum !== 'undefined';
}

export async function connectWallet(): Promise<string> {
  if (!window.ethereum) {
    throw new Error('No wallet provider found');
  }
  const accounts = (await window.ethereum.request({
    method: 'eth_requestAccounts',
  })) as string[];
  if (!accounts.length) {
    throw new Error('No accounts returned');
  }
  connectedAddress = accounts[0];
  localStorage.setItem('mm_wallet', connectedAddress);
  return connectedAddress;
}

export function getAddress(): string | null {
  if (connectedAddress) return connectedAddress;
  return localStorage.getItem('mm_wallet');
}

export function formatAddress(addr: string): string {
  if (addr.length < 10) return addr;
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/chain/wallet.ts
git commit -m "feat(client): add wallet connection module (EIP-1193)"
```

---

## Task 2: Two-Step Character Creation Overlay

**Files:**
- Modify: `client/index.html:252-269` (char-create-overlay)
- Modify: `client/index.html:283-299` (CSS, add wallet styles)

- [ ] **Step 1: Replace char-create-overlay HTML**

In `client/index.html`, replace the existing `#char-create-overlay` div:

```html
  <div id="char-create-overlay">
    <h1>MEMENTO MORI</h1>
    <!-- Step 1: Wallet -->
    <div id="wallet-step">
      <p id="wallet-prompt">Connect your wallet to enter</p>
      <button id="wallet-connect-btn">Connect Wallet</button>
      <p id="wallet-no-provider" class="hidden" style="color: var(--text-damage); font-size: 13px;">
        A browser wallet is required to play Memento Mori.
      </p>
    </div>
    <!-- Step 2: Name (hidden until wallet connected) -->
    <div id="name-step" class="hidden">
      <p id="wallet-address" style="color: var(--text-heal); font-size: 12px; letter-spacing: 1px;"></p>
      <p>What is your name, wanderer?</p>
      <input type="text" id="char-name-input" placeholder="Enter name" />
      <button id="char-create-btn">Enter the World</button>
    </div>
  </div>
```

- [ ] **Step 2: Add wallet CSS**

In the `<style>` block, after the existing `#char-create-overlay button` rule (around line 268), add:

```css
    #wallet-connect-btn {
      background: var(--accent); color: #fff; border: none; padding: 8px 24px;
      font-family: inherit; cursor: pointer;
    }
    #wallet-address { margin-bottom: 8px; }
```

- [ ] **Step 3: Commit**

```bash
git add client/index.html
git commit -m "feat(client): two-step character creation overlay with wallet gate"
```

---

## Task 3: Session State — Wallet Address

**Files:**
- Modify: `client/src/state/session.ts:6-13` (Session interface)
- Modify: `client/src/state/session.ts:41-59` (initSession)

- [ ] **Step 1: Add walletAddress to Session interface**

In `client/src/state/session.ts`, add `walletAddress` to the interface and default:

```typescript
export interface Session {
  playerId: string;
  sessionId: string;
  playerName: string;
  walletAddress: string;
  currentLocation: string;
  connected: boolean;
  openingNarrative: string;
}

const session: Session = {
  playerId: '',
  sessionId: '',
  playerName: '',
  walletAddress: '',
  currentLocation: '',
  connected: false,
  openingNarrative: '',
};
```

- [ ] **Step 2: Update initSession to accept and send wallet**

Change the `initSession` signature and POST body:

```typescript
export async function initSession(playerName: string, walletAddress: string): Promise<Session> {
  const resp = await fetch(`${GATEWAY_URL}/api/session/create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_name: playerName, wallet_address: walletAddress }),
  });
  const data = await resp.json();
  session.playerId = data.player_id;
  session.sessionId = data.session_id;
  session.playerName = playerName;
  session.walletAddress = walletAddress;
  session.currentLocation = data.location;
  session.openingNarrative = data.opening_narrative || '';

  localStorage.setItem('mm_player_id', session.playerId);
  localStorage.setItem('mm_player_name', playerName);
  localStorage.setItem('mm_wallet', walletAddress);

  connectWebSocket();
  return session;
}
```

- [ ] **Step 3: Commit**

```bash
git add client/src/state/session.ts
git commit -m "feat(client): add walletAddress to Session, send with create request"
```

---

## Task 4: Wire Wallet Gate in App

**Files:**
- Modify: `client/src/app.ts:1-22` (imports)
- Modify: `client/src/app.ts:178-199` (enterWorld)
- Modify: `client/src/app.ts:302-318` (DOMContentLoaded, char creation wiring)

- [ ] **Step 1: Add wallet import**

Add at the top of `client/src/app.ts`, after the other imports:

```typescript
import { hasProvider, connectWallet, formatAddress, getAddress } from './chain/wallet';
```

- [ ] **Step 2: Update enterWorld to accept and pass wallet**

```typescript
async function enterWorld(playerName: string, walletAddress: string): Promise<void> {
  const overlay = document.getElementById('char-create-overlay')!;
  overlay.classList.add('hidden');

  const session = await initSession(playerName, walletAddress);
  gameState = createInitialState(playerName);
  gameState.location.name = session.currentLocation;

  if (!gameState.roomMap) {
    applyStateUpdate(gameState, { room_map: getThresholdMap() });
  }
  registerMapEntities(gameState.roomMap);
  renderAllPanels();
  narrative.addBlock(`Welcome, ${playerName}. You find yourself at ${session.currentLocation}.`, 'system');

  if (session.openingNarrative) {
    const segments = parseNarrative(session.openingNarrative);
    narrative.addHtml(renderSegments(segments), 'narrative');
  }

  (document.getElementById('action-input') as HTMLInputElement).focus();
}
```

- [ ] **Step 3: Wire wallet connect button and two-step flow**

Replace the character creation wiring block at the end of `DOMContentLoaded` (the section with `nameInput`, `enterBtn`, `nameInput.addEventListener`, and `nameInput.focus()`):

```typescript
  // Character creation — two-step wallet gate
  const walletConnectBtn = document.getElementById('wallet-connect-btn')!;
  const walletStep = document.getElementById('wallet-step')!;
  const nameStep = document.getElementById('name-step')!;
  const walletPrompt = document.getElementById('wallet-prompt')!;
  const walletNoProvider = document.getElementById('wallet-no-provider')!;
  const walletAddressEl = document.getElementById('wallet-address')!;
  const nameInput = document.getElementById('char-name-input') as HTMLInputElement;
  const enterBtn = document.getElementById('char-create-btn')!;

  // Check for wallet provider on load
  if (!hasProvider()) {
    walletConnectBtn.classList.add('hidden');
    walletNoProvider.classList.remove('hidden');
  }

  walletConnectBtn.addEventListener('click', async () => {
    try {
      walletPrompt.textContent = 'Connecting...';
      const addr = await connectWallet();
      walletStep.classList.add('hidden');
      nameStep.classList.remove('hidden');
      walletAddressEl.textContent = `\u2713 ${formatAddress(addr)}`;
      nameInput.focus();
    } catch {
      walletPrompt.textContent = 'Connection rejected. Try again.';
    }
  });

  enterBtn.addEventListener('click', () => {
    const name = nameInput.value.trim() || 'Wanderer';
    const wallet = getAddress();
    if (wallet) enterWorld(name, wallet);
  });

  nameInput.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      const name = nameInput.value.trim() || 'Wanderer';
      const wallet = getAddress();
      if (wallet) enterWorld(name, wallet);
    }
  });
```

- [ ] **Step 4: Commit**

```bash
git add client/src/app.ts
git commit -m "feat(client): wire wallet gate in character creation flow"
```

---

## Task 5: Gateway — wallet_address Required + Engine Passthrough

**Files:**
- Modify: `gateway/src/gateway/routes/session.py:10-13` (CreateSessionRequest)
- Modify: `gateway/src/gateway/routes/session.py:29` (create_session call)
- Modify: `engine/src/memento/session.py:12` (create_player signature)
- Modify: `engine/src/memento/session.py:53` (chain.register_character call)
- Modify: `engine/tests/test_session.py:22-33` (test_create_player)

- [ ] **Step 1: Write failing test — create_player accepts wallet_address**

Add to `engine/tests/test_session.py`:

```python
def test_create_player_with_wallet():
    mock = _make_mock_client()
    with patch("memento.session.get_client", return_value=mock):
        with patch("memento.session.make_narration_crew") as mock_crew:
            mock_crew.return_value.kickoff.return_value.raw = "Welcome."
            with patch("memento.tools.kg.get_client", return_value=mock):
                with patch("memento.tools.chain.is_enabled", return_value=True):
                    with patch("memento.tools.chain.register_character") as mock_chain:
                        sm = SessionManager()
                        result = sm.create_player("Kael", wallet_address="0xabc123")

    assert result["player_id"] == "player-uuid-123"
    mock_chain.assert_called_once_with("player-uuid-123", "Kael", "0xabc123", 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd memento-mori/engine && python -m pytest tests/test_session.py::test_create_player_with_wallet -v`
Expected: FAIL — `create_player() got an unexpected keyword argument 'wallet_address'`

- [ ] **Step 3: Update create_player signature in session.py**

In `engine/src/memento/session.py`, change `create_player`:

```python
    def create_player(self, player_name: str, wallet_address: str = "") -> dict:
```

And update the chain register call (line 53):

```python
                _chain.register_character(player_uuid, player_name, wallet_address, 1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd memento-mori/engine && python -m pytest tests/test_session.py::test_create_player_with_wallet -v`
Expected: PASS

- [ ] **Step 5: Also run existing tests to confirm no regression**

Run: `cd memento-mori/engine && python -m pytest tests/test_session.py -v`
Expected: All pass (existing `test_create_player` still works due to default `wallet_address=""`)

- [ ] **Step 6: Update gateway session route**

In `gateway/src/gateway/routes/session.py`, make wallet_address required:

```python
class CreateSessionRequest(BaseModel):
    player_name: str
    game_id: str = "default"
    wallet_address: str
```

And pass it to `create_player` (line 29):

```python
        result = await asyncio.to_thread(sm.create_player, req.player_name, wallet_address=req.wallet_address)
```

- [ ] **Step 7: Commit**

```bash
cd memento-mori
git add engine/src/memento/session.py engine/tests/test_session.py gateway/src/gateway/routes/session.py
git commit -m "feat: wallet_address required on session create, passed through to chain"
```

---

## Task 6: Gateway Chain Client

**Files:**
- Create: `gateway/src/gateway/chain_client.py`

- [ ] **Step 1: Create chain_client module**

```python
# gateway/src/gateway/chain_client.py
"""MUD indexer HTTP client. Proxies reads from Redstone via the indexer service."""

import os
import httpx
import logging

logger = logging.getLogger(__name__)

MUD_INDEXER_URL = os.getenv("MUD_INDEXER_URL", "http://localhost:3001")

ALLOWED_TABLES = frozenset({
    "Characters", "Deaths", "Items", "Locations",
    "WorldEvents", "Episodes", "Reputation",
})

# Label → MUD table mapping for canonical verification
LABEL_TABLE_MAP: dict[str, str] = {
    "Character": "Characters",
    "Player": "Characters",
    "Item": "Items",
    "Weapon": "Items",
    "Armor": "Items",
    "Consumable": "Items",
    "Location": "Locations",
    "Room": "Locations",
    "Region": "Locations",
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
```

- [ ] **Step 2: Commit**

```bash
git add gateway/src/gateway/chain_client.py
git commit -m "feat(gateway): MUD indexer HTTP client with canonical verification"
```

---

## Task 7: Gateway Chain Route

**Files:**
- Create: `gateway/src/gateway/routes/chain.py`
- Modify: `gateway/src/gateway/app.py:47-51` (register router)
- Create: `gateway/tests/test_chain_route.py`

- [ ] **Step 1: Write test for chain route**

```python
# gateway/tests/test_chain_route.py
"""Tests for /api/chain/{table}/{id} route."""

from unittest.mock import patch, AsyncMock
import pytest


@pytest.fixture
def client():
    from gateway.app import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_chain_route_valid_table(client):
    mock_data = {"name": "Wanderer", "wallet": "0xabc", "level": 3, "alive": True, "createdAt": 1711929600}
    with patch("gateway.routes.chain.fetch_chain_record", new_callable=AsyncMock, return_value=mock_data):
        resp = client.get("/api/chain/Characters/c800dabf-b1ef-4033-a594-b1d7f80ee316")
    assert resp.status_code == 200
    body = resp.json()
    assert body["table"] == "Characters"
    assert body["data"]["name"] == "Wanderer"


def test_chain_route_invalid_table(client):
    resp = client.get("/api/chain/BadTable/some-id")
    assert resp.status_code == 400


def test_chain_route_not_found(client):
    with patch("gateway.routes.chain.fetch_chain_record", new_callable=AsyncMock, return_value=None):
        resp = client.get("/api/chain/Characters/nonexistent-id")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd memento-mori/gateway && python -m pytest tests/test_chain_route.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gateway.routes.chain'`

- [ ] **Step 3: Create chain route**

```python
# gateway/src/gateway/routes/chain.py
"""Chain routes — proxy reads from MUD indexer."""

from fastapi import APIRouter, Path, HTTPException
from gateway.chain_client import fetch_chain_record, ALLOWED_TABLES

router = APIRouter()


@router.get("/chain/{table}/{entity_id}")
async def get_chain_record(
    table: str = Path(...),
    entity_id: str = Path(...),
):
    """Fetch onchain record from MUD indexer for a given table and entity ID."""
    if table not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail=f"Unknown table: {table}. Allowed: {', '.join(sorted(ALLOWED_TABLES))}")

    data = await fetch_chain_record(table, entity_id)
    if data is None:
        raise HTTPException(status_code=404, detail="No onchain record found")

    return {"table": table, "id": entity_id, "data": data}
```

- [ ] **Step 4: Register chain router in app.py**

In `gateway/src/gateway/app.py`, add the import and router registration after the existing routers:

```python
from gateway.routes import action, session, state, entity, chain
app.include_router(action.router, prefix="/api")
app.include_router(session.router, prefix="/api")
app.include_router(state.router, prefix="/api")
app.include_router(entity.router, prefix="/api")
app.include_router(chain.router, prefix="/api")
```

- [ ] **Step 5: Run tests**

Run: `cd memento-mori/gateway && python -m pytest tests/test_chain_route.py -v`
Expected: All 3 pass

- [ ] **Step 6: Commit**

```bash
cd memento-mori
git add gateway/src/gateway/routes/chain.py gateway/src/gateway/app.py gateway/tests/test_chain_route.py
git commit -m "feat(gateway): /api/chain/{table}/{id} endpoint proxying MUD indexer"
```

---

## Task 8: Canonical Entity Verification

**Files:**
- Modify: `gateway/src/gateway/routes/entity.py:9-55` (get_neighbors)
- Modify: `gateway/src/gateway/routes/entity.py:58-74` (get_entity)
- Modify: `gateway/src/gateway/routes/entity.py:77-95` (search_entity)
- Create: `gateway/tests/test_canonical_filter.py`

- [ ] **Step 1: Write test for canonical filtering**

```python
# gateway/tests/test_canonical_filter.py
"""Tests for canonical entity verification in entity routes."""

from unittest.mock import patch, AsyncMock, MagicMock
import pytest


@pytest.fixture
def client():
    from gateway.app import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def _mock_kg_entity():
    """KG returns a Character entity with neighbors."""
    mock = MagicMock()
    mock.kg.get_entity.return_value = {
        "entity": {
            "uuid": "char-1",
            "name": "Kael",
            "labels": ["Player"],
            "summary": "A warrior",
        }
    }
    mock.kg.search.return_value = {
        "entities": [
            {"uuid": "char-1", "name": "Kael", "labels": ["Player"], "summary": "A warrior"},
            {"uuid": "item-1", "name": "Iron Sword", "labels": ["Item"], "summary": "A sword"},
            {"uuid": "ghost-1", "name": "Phantom NPC", "labels": ["Character"], "summary": "Should be filtered"},
        ],
        "edges": [
            {"source_name": "Kael", "target_name": "Iron Sword", "name": "OWNS", "fact": "Kael owns the sword"},
            {"source_name": "Kael", "target_name": "Phantom NPC", "name": "MET", "fact": "Should be filtered"},
        ],
    }
    return mock


async def _mock_exists(entity_id: str, labels: list[str]) -> bool:
    """char-1 and item-1 exist onchain, ghost-1 does not."""
    return entity_id in ("char-1", "item-1")


def test_neighbors_filters_non_canonical(client):
    mock = _mock_kg_entity()
    with patch("gateway.routes.entity.get_client", return_value=mock):
        with patch("gateway.routes.entity.entity_exists_onchain", side_effect=_mock_exists):
            resp = client.get("/api/entity/char-1/neighbors")

    body = resp.json()
    neighbor_names = [n["name"] for n in body["neighbors"]]
    assert "Iron Sword" in neighbor_names
    assert "Phantom NPC" not in neighbor_names

    edge_targets = [e["target"] for e in body["edges"]]
    assert "Iron Sword" in edge_targets
    assert "Phantom NPC" not in edge_targets
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd memento-mori/gateway && python -m pytest tests/test_canonical_filter.py -v`
Expected: FAIL — `Phantom NPC` is still in neighbors (no filtering yet)

- [ ] **Step 3: Update entity.py with canonical verification**

Replace the entire `gateway/src/gateway/routes/entity.py` file:

```python
"""Entity routes — fetch entity details from KG. Non-canonical entities filtered via MUD indexer."""

import asyncio
from fastapi import APIRouter, Path

from gateway.chain_client import entity_exists_onchain

router = APIRouter()


async def _filter_canonical(entities: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Remove entities not found onchain and edges referencing them."""
    checks = await asyncio.gather(*(
        entity_exists_onchain(str(e.get("uuid", e.get("id", ""))), e.get("labels", []))
        for e in entities
    ))
    canonical_names: set[str] = set()
    filtered_entities = []
    for e, is_canonical in zip(entities, checks):
        if is_canonical:
            filtered_entities.append(e)
            canonical_names.add(e.get("name", ""))

    filtered_edges = [
        edge for edge in edges
        if edge.get("source", edge.get("source_name", "")) in canonical_names
        and edge.get("target", edge.get("target_name", "")) in canonical_names
    ]
    return filtered_entities, filtered_edges


@router.get("/entity/{entity_id}/neighbors")
async def get_neighbors(entity_id: str = Path(...)):
    """Get entity details + connected entities and edges from KG, filtered for canonical entities."""
    try:
        from memento.bonfires_client import get_client
        client = await asyncio.to_thread(get_client)

        entity = await asyncio.to_thread(client.kg.get_entity, entity_id)
        if isinstance(entity, dict) and "entity" in entity:
            entity = entity["entity"]
        name = entity.get("name", "Unknown")
        labels = entity.get("labels", [])

        # Check if primary entity is canonical
        if not await entity_exists_onchain(entity_id, labels):
            return {"entity": {"id": entity_id, "name": "Unknown", "labels": [], "summary": ""}, "neighbors": [], "edges": []}

        result = await asyncio.to_thread(client.kg.search, name, 15)
        raw_entities = result.get("entities", result.get("nodes", []))
        raw_edges = result.get("edges", [])

        # Build neighbor list and edges
        neighbors_raw = [
            {
                "id": str(e.get("uuid", "")),
                "name": e.get("name", ""),
                "labels": e.get("labels", []),
                "summary": e.get("summary", ""),
                "uuid": str(e.get("uuid", "")),
            }
            for e in raw_entities
            if str(e.get("uuid", "")) != entity_id
        ]
        edges_raw = [
            {
                "source": e.get("source_name", ""),
                "target": e.get("target_name", ""),
                "relationship": e.get("relationship", e.get("name", "")),
                "fact": e.get("fact", ""),
            }
            for e in raw_edges
        ]

        # Filter for canonical entities
        neighbors_filtered, edges_filtered = await _filter_canonical(neighbors_raw, edges_raw)

        # Add primary entity name to canonical set for edge filtering
        canonical_names = {n["name"] for n in neighbors_filtered}
        canonical_names.add(name)
        edges_filtered = [e for e in edges_filtered if e["source"] in canonical_names and e["target"] in canonical_names]

        return {
            "entity": {
                "id": entity_id,
                "name": name,
                "labels": labels,
                "summary": entity.get("summary", ""),
            },
            "neighbors": [{k: v for k, v in n.items() if k != "uuid"} for n in neighbors_filtered],
            "edges": edges_filtered,
        }
    except Exception:
        return {"entity": {"id": entity_id, "name": "Unknown", "labels": [], "summary": ""}, "neighbors": [], "edges": []}


@router.get("/entity/{entity_id}")
async def get_entity(entity_id: str = Path(...)):
    """Fetch entity details from KG by UUID, verified canonical."""
    try:
        from memento.bonfires_client import get_client
        client = await asyncio.to_thread(get_client)
        entity = await asyncio.to_thread(client.kg.get_entity, entity_id)
        if isinstance(entity, dict) and "entity" in entity:
            entity = entity["entity"]

        labels = entity.get("labels", [])
        if not await entity_exists_onchain(entity_id, labels):
            return {"id": entity_id, "name": "Unknown", "labels": [], "summary": ""}

        return {
            "id": entity_id,
            "name": entity.get("name", "Unknown"),
            "labels": labels,
            "summary": entity.get("summary", ""),
        }
    except Exception:
        return {"id": entity_id, "name": "Unknown", "labels": [], "summary": ""}


@router.get("/entity/search/{name}")
async def search_entity(name: str = Path(...)):
    """Search for entity by name, verified canonical."""
    try:
        from memento.bonfires_client import get_client
        client = await asyncio.to_thread(get_client)
        result = await asyncio.to_thread(client.kg.search, name, 1)
        entities = result.get("entities", result.get("nodes", []))
        if entities:
            e = entities[0]
            entity_id = str(e.get("uuid", ""))
            labels = e.get("labels", [])
            if not await entity_exists_onchain(entity_id, labels):
                return {"error": "not found"}
            return {
                "id": entity_id,
                "name": e.get("name", ""),
                "labels": labels,
                "summary": e.get("summary", ""),
            }
        return {"error": "not found"}
    except Exception:
        return {"error": "search failed"}
```

- [ ] **Step 4: Run tests**

Run: `cd memento-mori/gateway && python -m pytest tests/test_canonical_filter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd memento-mori
git add gateway/src/gateway/routes/entity.py gateway/tests/test_canonical_filter.py
git commit -m "feat(gateway): canonical entity verification — filter non-onchain entities"
```

---

## Task 9: Wiki Tab System + Chain Data

**Files:**
- Modify: `client/src/ui/wiki.ts`

- [ ] **Step 1: Add chain data types and fetch function**

At the top of `client/src/ui/wiki.ts`, after the existing interfaces, add:

```typescript
const GATEWAY = '';

type ChainTable = 'Characters' | 'Items' | 'Locations' | 'Deaths';

interface ChainResponse {
  table: string;
  id: string;
  data: Record<string, unknown> | Record<string, unknown>[];
}

const LABEL_TABLE_MAP: Record<string, ChainTable[]> = {
  Character: ['Characters', 'Deaths'],
  Player: ['Characters', 'Deaths'],
  Item: ['Items'],
  Weapon: ['Items'],
  Armor: ['Items'],
  Consumable: ['Items'],
  Location: ['Locations'],
  Room: ['Locations'],
  Region: ['Locations'],
};

function tablesForLabels(labels: string[]): ChainTable[] {
  for (const label of labels) {
    if (label in LABEL_TABLE_MAP) return LABEL_TABLE_MAP[label];
  }
  return [];
}

async function fetchChainData(table: string, entityId: string): Promise<ChainResponse | null> {
  try {
    const resp = await fetch(`${GATEWAY}/api/chain/${table}/${entityId}`);
    if (resp.status === 200) return resp.json();
    return null;
  } catch { return null; }
}

function formatTimestamp(ts: number): string {
  if (!ts) return 'Unknown';
  return new Date(ts * 1000).toLocaleDateString();
}

function formatAddr(addr: string): string {
  if (!addr || addr.length < 10 || addr === '0x0000000000000000000000000000000000000000') return 'None';
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}
```

- [ ] **Step 2: Add chain tab rendering functions**

After the helper functions, add:

```typescript
function renderCharacterChain(data: Record<string, unknown>, deaths: Record<string, unknown>[] | null): string {
  let html = '<div class="wiki-page-heading">ONCHAIN RECORD</div>';
  html += `<div class="wiki-chain-row"><span class="wiki-chain-label">Status</span> ${data.alive ? 'Alive' : 'Dead'}</div>`;
  html += `<div class="wiki-chain-row"><span class="wiki-chain-label">Level</span> ${data.level ?? '?'}</div>`;
  html += `<div class="wiki-chain-row"><span class="wiki-chain-label">Wallet</span> ${formatAddr(String(data.wallet || ''))}</div>`;
  html += `<div class="wiki-chain-row"><span class="wiki-chain-label">Created</span> ${formatTimestamp(Number(data.createdAt || 0))}</div>`;
  if (deaths && Array.isArray(deaths) && deaths.length > 0) {
    html += '<div class="wiki-page-heading" style="margin-top:8px">DEATHS</div>';
    for (const d of deaths) {
      html += `<div class="wiki-chain-death">`;
      html += `<div>\u2620 ${esc(String(d.cause || 'Unknown'))}</div>`;
      html += `<div class="wiki-fact">${esc(String(d.location || ''))} \u00B7 Lv${d.level} \u00B7 Tick ${d.tick}</div>`;
      html += `</div>`;
    }
  }
  return html;
}

function renderItemChain(data: Record<string, unknown>): string {
  let html = '<div class="wiki-page-heading">ONCHAIN RECORD</div>';
  html += `<div class="wiki-chain-row"><span class="wiki-chain-label">Rarity</span> ${esc(String(data.rarity || 'Common'))}</div>`;
  html += `<div class="wiki-chain-row"><span class="wiki-chain-label">Owner</span> ${formatAddr(String(data.ownerId || ''))}</div>`;
  html += `<div class="wiki-chain-row"><span class="wiki-chain-label">Location</span> ${formatAddr(String(data.locationId || ''))}</div>`;
  return html;
}

function renderLocationChain(data: Record<string, unknown>): string {
  let html = '<div class="wiki-page-heading">ONCHAIN RECORD</div>';
  html += `<div class="wiki-chain-row"><span class="wiki-chain-label">Region</span> ${esc(String(data.region || 'Unknown'))}</div>`;
  html += `<div class="wiki-chain-row"><span class="wiki-chain-label">Discovered by</span> ${formatAddr(String(data.discoveredBy || ''))}</div>`;
  return html;
}
```

- [ ] **Step 3: Modify createWikiPanel to support tabs**

In the `createWikiPanel()` function, add tab state and chain rendering. The key changes:

1. Add `activeTab` state variable alongside `currentId`, `pages`, `pageIdx`:

```typescript
  let activeTab: 'lore' | 'chain' = 'lore';
```

2. Add a `renderChainTab` async function:

```typescript
  async function renderChainTab(entityId: string, labels: string[]) {
    const tables = tablesForLabels(labels);
    if (!tables.length) {
      el.innerHTML = '<div class="wiki-empty">No onchain data for this entity type</div>';
      return;
    }
    el.innerHTML = '<div class="wiki-loading">Loading chain data\u2026</div>';

    let html = renderTabBar();

    if (tables.includes('Characters')) {
      const charData = await fetchChainData('Characters', entityId);
      const deathData = await fetchChainData('Deaths', entityId);
      if (charData) {
        html += renderCharacterChain(
          charData.data as Record<string, unknown>,
          deathData ? (Array.isArray(deathData.data) ? deathData.data : [deathData.data]) as Record<string, unknown>[] : null,
        );
      } else {
        html += '<div class="wiki-empty">No onchain data</div>';
      }
    } else if (tables.includes('Items')) {
      const itemData = await fetchChainData('Items', entityId);
      html += itemData ? renderItemChain(itemData.data as Record<string, unknown>) : '<div class="wiki-empty">No onchain data</div>';
    } else if (tables.includes('Locations')) {
      const locData = await fetchChainData('Locations', entityId);
      html += locData ? renderLocationChain(locData.data as Record<string, unknown>) : '<div class="wiki-empty">No onchain data</div>';
    }

    el.innerHTML = html;
    wireTabClicks();
  }
```

3. Add tab bar rendering and wiring:

```typescript
  function renderTabBar(): string {
    return `<div class="wiki-tabs">
      <span class="wiki-tab ${activeTab === 'lore' ? 'active' : ''}" data-tab="lore">Lore</span>
      <span class="wiki-tab ${activeTab === 'chain' ? 'active' : ''}" data-tab="chain">Chain</span>
    </div>`;
  }

  let currentLabels: string[] = [];

  function wireTabClicks() {
    el.querySelectorAll('.wiki-tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        const t = (tab as HTMLElement).dataset.tab as 'lore' | 'chain';
        if (t === activeTab) return;
        activeTab = t;
        if (t === 'lore') renderPage();
        else renderChainTab(currentId, currentLabels);
      });
    });
  }
```

4. Modify `renderPage()` to prepend the tab bar (only if entity has chain tables):

At the start of `renderPage()`, after `if (!pages.length) return;`, prepend the tab bar to the HTML if the entity has chain-eligible labels:

```typescript
    // Prepend tab bar if chain data available
    const hasTabs = tablesForLabels(currentLabels).length > 0;
    if (hasTabs) html = renderTabBar() + html;
```

And at the end of `renderPage()`, after setting `el.innerHTML = html;` and before wiring pagination, add:

```typescript
    if (hasTabs) wireTabClicks();
```

5. Update `show()` and `showByName()` to reset tab and store labels:

In `show()`, after `const data = await fetchEntity(entityId);`, add:

```typescript
      activeTab = 'lore';
      currentLabels = data.entity.labels;
```

Same pattern in `showByName()`.

- [ ] **Step 4: Add wiki tab CSS to index.html**

In `client/index.html`, after the `.wiki-page-num` rule, add:

```css
    .wiki-tabs {
      display: flex; gap: 0; margin-bottom: 8px;
      border-bottom: 1px solid var(--border);
    }
    .wiki-tab {
      padding: 2px 10px; font-size: 11px; letter-spacing: 1px;
      color: var(--text-dim); cursor: pointer; text-transform: uppercase;
      border-bottom: 2px solid transparent;
    }
    .wiki-tab:hover { color: var(--text-primary); }
    .wiki-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
    .wiki-chain-row {
      padding: 2px 0; font-size: 13px;
    }
    .wiki-chain-label {
      color: var(--text-dim); display: inline-block; width: 90px; font-size: 11px;
      letter-spacing: 0.5px; text-transform: uppercase;
    }
    .wiki-chain-death {
      padding: 4px 0; border-bottom: 1px solid var(--border);
    }
```

- [ ] **Step 5: Commit**

```bash
cd memento-mori
git add client/src/ui/wiki.ts client/index.html
git commit -m "feat(client): wiki Lore/Chain tab system with onchain data rendering"
```

---

## Task 10: Integration Verification

- [ ] **Step 1: Run all engine tests**

```bash
cd memento-mori/engine && python -m pytest tests/ -v
```

Expected: All pass

- [ ] **Step 2: Run all gateway tests**

```bash
cd memento-mori/gateway && python -m pytest tests/ -v
```

Expected: All pass

- [ ] **Step 3: TypeScript type check**

```bash
cd memento-mori/client && npx tsc --noEmit
```

Expected: No errors

- [ ] **Step 4: Build client**

```bash
cd memento-mori/client && bun build src/app.ts --outdir dist
```

Expected: Build succeeds

- [ ] **Step 5: Manual verification checklist**

1. Start gateway: `cd memento-mori/gateway && uvicorn gateway.app:app --reload --port 8080`
2. Open client in browser with MetaMask installed
3. Verify: "Connect Wallet" button visible, no name input
4. Click "Connect Wallet" → MetaMask popup → approve
5. Verify: wallet address shown with checkmark, name input appears
6. Enter name, click "Enter the World"
7. Verify: session creates successfully, game loads
8. Click an entity in narrative → wiki shows Lore tab
9. Click "Chain" tab → chain data loads (or "No onchain data" if indexer not running)
10. Without MetaMask: verify "A browser wallet is required" message, no connect button

---

## Verification

**Automated:**
- `cd engine && python -m pytest tests/ -v` — all engine tests including `test_create_player_with_wallet`
- `cd gateway && python -m pytest tests/ -v` — chain route + canonical filter tests
- `cd client && npx tsc --noEmit` — type check
- `cd client && bun build src/app.ts --outdir dist` — build check

**Manual:**
- Two-step wallet flow (with wallet, without wallet)
- Wiki Lore/Chain tabs
- Canonical filtering (entities not onchain shouldn't appear)
- Status bar unchanged (already working)
