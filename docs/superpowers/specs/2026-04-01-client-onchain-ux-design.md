# Plan C: Client Onchain UX

## Overview

Add mandatory wallet connection, onchain data in the wiki panel, and gateway-proxied MUD indexer reads to the Memento Mori client. The status bar chain phases are already complete and require no changes.

Every player must connect a browser wallet (MetaMask or compatible injected provider) before entering the world. No fallback — wallet is required because the game uses x402 for payments.

## Wallet Gate

### Character Creation Flow

The character creation overlay becomes two-step:

**Step 1 — Connect Wallet**

- Full-screen overlay: "MEMENTO MORI" title, "Connect your wallet to enter" subtitle
- Single "Connect Wallet" button
- On click: `window.ethereum.request({ method: 'eth_requestAccounts' })`
- On success: show truncated address (`0x1a2b...3c4d`) with checkmark, reveal step 2
- If no `window.ethereum`: show "A browser wallet is required to play Memento Mori." — no button, no fallback, hard block

**Step 2 — Name Character**

- Existing name input + "Enter the World" button
- `enterWorld()` sends wallet address alongside player name via `initSession()`

### Client State

`Session` interface gains `walletAddress: string`. Stored in `localStorage` alongside `mm_player_id` and `mm_player_name`.

### Gateway Plumbing

`CreateSessionRequest` gains `wallet_address: str` (required). Passed through to `SessionManager.create_player()` which forwards to `chain.register_character()`.

## Wiki Onchain Tab

### Tab System

The wiki panel gains a tab bar at the top of page 1: **Lore** (existing KG data) and **Chain** (onchain data from MUD indexer via gateway).

- Lore tab: existing content (entity overview, edges, neighbors) — no changes
- Chain tab: structured onchain fields fetched from gateway
- Tab state is per-entity — switching entities resets to Lore tab

### Chain Tab Content by Entity Type

**Characters:**
| Field | Source |
|-------|--------|
| Alive/Dead | `Characters.alive` |
| Level | `Characters.level` |
| Wallet | `Characters.wallet` (truncated) |
| Created | `Characters.createdAt` (formatted timestamp) |

**Items:**
| Field | Source |
|-------|--------|
| Rarity | `Items.rarity` |
| Owner | `Items.ownerId` → resolve to character name |
| Location | `Items.locationId` → resolve to location name (if unowned) |

**Locations:**
| Field | Source |
|-------|--------|
| Discovered by | `Locations.discoveredBy` (truncated address) |
| Region | `Locations.region` |

**Deaths** (shown on character chain tab as sub-list):
| Field | Source |
|-------|--------|
| Cause | `Deaths.cause` |
| Location | `Deaths.location` |
| Level | `Deaths.level` |
| Tick | `Deaths.tick` |

If the entity has no onchain record (e.g., not yet synced), the chain tab shows "No onchain data" in dim italic — same style as the existing "No knowledge graph data available" fallback.

### Entity Type Detection

The wiki already receives `entity.labels` from the KG. Map labels to MUD tables:
- Labels containing `Character` or `Player` → query `Characters` + `Deaths`
- Labels containing `Item`, `Weapon`, `Armor`, `Consumable` → query `Items`
- Labels containing `Location`, `Room`, `Region` → query `Locations`
- No matching label → hide the Chain tab entirely

## Gateway Chain Endpoint

### New Route: `/api/chain/{table}/{entity_id}`

Proxies the MUD indexer. Returns the row(s) from the specified MUD table for the given entity ID.

**Request:**
```
GET /api/chain/Characters/c800dabf-b1ef-4033-a594-b1d7f80ee316
```

**Response:**
```json
{
  "table": "Characters",
  "id": "c800dabf-b1ef-4033-a594-b1d7f80ee316",
  "data": {
    "name": "Wanderer",
    "wallet": "0x1a2b3c4d5e6f...",
    "level": 3,
    "alive": true,
    "createdAt": 1711929600
  }
}
```

For tables with multiple rows per entity (Deaths by characterId):
```
GET /api/chain/Deaths/c800dabf-b1ef-4033-a594-b1d7f80ee316
```

Returns:
```json
{
  "table": "Deaths",
  "id": "c800dabf-b1ef-4033-a594-b1d7f80ee316",
  "data": [
    { "cause": "Eaten by wolves", "location": "The Fog Road", "level": 3, "tick": 42, "timestamp": 1711930000 }
  ]
}
```

**Allowed tables:** `Characters`, `Deaths`, `Items`, `Locations`, `WorldEvents`, `Episodes`, `Reputation`. The gateway validates the table name and rejects unknown tables with 400.

**ID conversion:** The gateway converts the UUID string to bytes32 before querying the MUD indexer (same `_uuid_to_bytes32` logic as `engine/src/memento/tools/chain.py`).

### MUD Indexer Setup

The gateway runs `@latticexyz/store-sync` with a SQLite or Postgres backend, pointed at the Redstone RPC and the deployed World contract address. The indexer syncs MUD table state automatically.

Environment variables (gateway):
```bash
MUD_INDEXER_URL=http://localhost:3001   # if running separate indexer service
# OR
MUD_WORLD_CONTRACT=0x...               # if gateway runs embedded indexer
REDSTONE_RPC=https://rpc.redstone.xyz
```

## Status Bar

Already complete. `client/src/ui/status.ts` has `setPhase()`, `setChain()`, `setTick()` wired to WebSocket status messages. No changes needed.

## Architecture

```
Browser (mandatory wallet via window.ethereum)
  |
  +-- Connect wallet --> get address
  |
  +-- initSession(name, walletAddress) --> POST /api/session/create
  |                                            |
  |                                            v
  |                                     Gateway (FastAPI)
  |                                       |
  |                                       +-- SessionManager.create_player(name, wallet)
  |                                       |     |
  |                                       |     +-- chain.register_character(uuid, name, wallet, level)
  |                                       |
  +-- Wiki Lore tab --> GET /api/entity/{id}/neighbors (existing, KG)
  |
  +-- Wiki Chain tab --> GET /api/chain/{table}/{id} (new, MUD indexer)
  |                          |
  |                          v
  |                    Gateway chain route
  |                      |
  |                      +-- MUD indexer (store-sync) --> Redstone L2
  |
  +-- WebSocket <-- status messages { phase, tick, chain } (existing)
```

## Files Changed

### New
- `client/src/chain/wallet.ts` — wallet connection: `connectWallet(): Promise<string>`, `getAddress(): string | null`, `hasProvider(): boolean`, `formatAddress(addr: string): string`
- `gateway/src/gateway/routes/chain.py` — `/api/chain/{table}/{id}` endpoint

### Modified
- `client/index.html` — two-step char creation overlay (wallet connect step + name step), wallet-related CSS
- `client/src/app.ts` — wallet gate in `enterWorld()`, pass wallet to `initSession()`
- `client/src/state/session.ts` — `Session.walletAddress`, `initSession(name, wallet)` sends `wallet_address` in POST body, persist to localStorage
- `client/src/ui/wiki.ts` — tab bar (Lore/Chain), `fetchChainData(table, id)`, chain tab render logic per entity type
- `gateway/src/gateway/routes/session.py` — `wallet_address: str` on `CreateSessionRequest` (required field)

### Unchanged
- `client/src/ui/status.ts` — already complete
- All engine code — Plan B handles chain writes
- All contracts — Plan A already deployed

## Dependencies

### Client
- No new npm dependencies. `window.ethereum` is the injected provider API (EIP-1193), no library needed.

### Gateway
- MUD indexer integration. Either:
  - Run `@latticexyz/store-indexer` as a sidecar service and proxy to it
  - Or use a hosted indexer if available for Redstone
- `uuid` to bytes32 conversion (reuse logic from `engine/src/memento/tools/chain.py`)

## Out of Scope

- Client-side transaction submission (engine is sole writer)
- Wallet switching mid-session
- ENS resolution for addresses
- Multiple wallets per player
- Chain tab for WorldEvents or Episodes (can add later)
