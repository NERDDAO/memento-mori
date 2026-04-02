# IPFS Episode Storage Design

## Context

The memento-mori engine records game episodes to MUD tables on an EVM chain (currently targeting Base instead of Redstone). The current `Episodes` table stores full episode content onchain: `name`, `summary`, `entities`, and `edges` as Solidity strings. This is gas-expensive (~300-500K gas per episode) and unnecessary — Neo4j (Bonfires KG) is the source of truth for gameplay, and the chain serves only as a provenance ledger.

This design replaces inline string storage with a content hash pointing to IPFS (Pinata). The chain becomes a minimal append-only log of timestamped hashes. Full episode content lives on IPFS for durable, verifiable persistence.

## Architecture

```
Engine (Python)
  │
  ├─ EpisodicMemoryFlow.consolidate()
  │    → produces episode JSON (name, summary, entities, edges)
  │
  ├─ ipfs.pin_json(episode_data)
  │    → uploads to Pinata → returns (cid, keccak256_hash)
  │
  └─ chain.record_episode(id, tick, content_hash)
       → writes hash to MUD Episodes table onchain
```

**Data lives in three places:**

| Layer | What it stores | Purpose |
|-------|---------------|---------|
| Neo4j (Bonfires KG) | Full episode graph, entities, edges | Gameplay source of truth |
| IPFS (Pinata) | Episode JSON blob | Durable persistence, player-downloadable |
| Chain (MUD table) | `(id, tick, timestamp, contentHash)` | Provenance, timestamped receipts |

## Onchain Schema Change

### Before

```typescript
Episodes: {
  schema: {
    id: "bytes32",
    tick: "uint256",
    timestamp: "uint256",
    name: "string",
    summary: "string",
    entities: "string",
    edges: "string",
  },
  key: ["id"],
}
```

### After

```typescript
Episodes: {
  schema: {
    id: "bytes32",
    tick: "uint256",
    timestamp: "uint256",
    contentHash: "bytes32",
  },
  key: ["id"],
}
```

Gas reduction: ~300-500K → ~80-100K per episode.

## Contract Change

### Before

```solidity
function recordEpisode(
  bytes32 id, string memory name, string memory summary,
  string memory entities, string memory edges, uint256 tick
) public {
  Episodes.set(id, tick, block.timestamp, name, summary, entities, edges);
}
```

### After

```solidity
function recordEpisode(
  bytes32 id, bytes32 contentHash, uint256 tick
) public {
  Episodes.set(id, tick, block.timestamp, contentHash);
}
```

## IPFS JSON Blob Format

```json
{
  "version": 1,
  "episodeId": "abc123...",
  "tick": 42,
  "name": "The Fall of Ashwick",
  "summary": "Kael discovered the hidden vault beneath the ruins...",
  "entities": [
    {"name": "Kael", "type": "Character"},
    {"name": "Hidden Vault", "type": "Location"}
  ],
  "edges": [
    {"source": "Kael", "target": "Hidden Vault", "relation": "discovered"}
  ]
}
```

The `version` field allows future schema evolution without breaking existing pins.

## Engine Changes

### New module: `engine/src/memento/tools/ipfs.py`

Thin wrapper around Pinata's REST API. Follows the same pattern as `chain.py` — lazy-init, fire-and-forget with logging on failure.

```python
def pin_json(data: dict) -> tuple[str, bytes]:
    """Pin JSON to Pinata. Returns (cid, keccak256_hash).
    
    The keccak256 hash is stored in Pinata pin metadata for reverse lookup.
    """
```

- Uses Pinata's `pinJSONToIPFS` endpoint
- Auth via `PINATA_JWT` env var
- Computes `keccak256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode())` for deterministic hashing
- Stores hash in pin metadata: `{"keyvalues": {"keccak256": "0xabc..."}}`
- Returns `(cid, hash_bytes)` — caller passes hash to chain, can log CID

### Modified: `engine/src/memento/tools/chain.py`

Update `record_episode()` signature:

```python
def record_episode(uuid: str, content_hash: bytes, tick: int) -> None:
    """Record an episode content hash onchain."""
    _send_tx("recordEpisode", _uuid_to_bytes32(uuid), content_hash, tick)
```

### Modified: `engine/src/memento/flows/episodic_memory.py`

Add a new flow step after `consolidate()`:

```
consolidate() → pin_and_record()
```

`pin_and_record()`:
1. Build episode JSON from consolidation output + flow state
2. Call `ipfs.pin_json(episode_data)` → get `(cid, content_hash)`
3. Call `chain.record_episode(episode_id, content_hash, tick)`
4. Log CID for debugging

### Modified: `engine/src/memento/config/chain.py`

Add:

```python
PINATA_JWT = os.getenv("PINATA_JWT", "")
IPFS_ENABLED = bool(PINATA_JWT)
```

### Modified: `.env` and `example.env`

Add `PINATA_JWT=` entry.

## Verification Flow

For a player reconstructing the episode chain:

1. Read all `(episodeId, tick, timestamp, contentHash)` rows from MUD indexer
2. For each hash, query Pinata API: find pin where `metadata.keyvalues.keccak256 == contentHash`
3. Fetch JSON from IPFS gateway (`https://gateway.pinata.cloud/ipfs/{cid}`)
4. Verify: `keccak256(json_bytes) == contentHash`
5. Reconstruct graph from verified episode entities + edges

## Error Handling

Both IPFS and chain writes are non-blocking (fire-and-forget on background threads). Failures are logged but never block gameplay. This matches the existing pattern in `chain.py`.

**Failure modes:**

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Pinata upload fails | No CID, no onchain record | Episode still exists in Neo4j. Retry on next consolidation cycle or log for manual retry. |
| Pinata succeeds, chain write fails | Content pinned but no onchain receipt | CID logged, can be re-submitted manually. |
| Both fail | No IPFS or chain record | Neo4j is the source of truth — gameplay unaffected. |

**Ordering constraint:** IPFS pin must succeed before chain write, since the chain needs the content hash. If pin fails, skip the chain write entirely.

## Files Modified

| File | Change |
|------|--------|
| `contracts/packages/contracts/mud.config.ts` | Episodes schema: drop string fields, add `contentHash: bytes32` |
| `contracts/packages/contracts/src/systems/EpisodeSystem.sol` | New signature: `recordEpisode(bytes32 id, bytes32 contentHash, uint256 tick)` |
| `contracts/packages/contracts/test/EpisodeSystem.t.sol` | Update test to use new signature |
| `engine/src/memento/tools/ipfs.py` | **New** — Pinata upload module |
| `engine/src/memento/tools/chain.py` | Update `record_episode()` to accept `content_hash: bytes` |
| `engine/src/memento/flows/episodic_memory.py` | Add `pin_and_record()` step after consolidation |
| `engine/src/memento/config/chain.py` | Add `PINATA_JWT`, `IPFS_ENABLED` |
| `.env` / `example.env` | Add `PINATA_JWT` |

## Testing

1. **Contract tests (Foundry):** Update `EpisodeSystem.t.sol` to call `recordEpisode(id, contentHash, tick)` and verify table storage
2. **IPFS module:** Unit test `pin_json()` with mocked Pinata API response
3. **Integration:** Run `EpisodicMemoryFlow` end-to-end with Pinata test API key, verify CID is returned and hash matches
4. **Verification:** Fetch pinned content via gateway, keccak256 it, compare to onchain hash
