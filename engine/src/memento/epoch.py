# engine/src/memento/epoch.py
"""Epoch snapshot + merkle root + IPFS pin + onchain commit.

At epoch boundaries the full KG state is:
  1. Serialised to deterministic canonical JSON
  2. Hashed into a keccak256 merkle root (EVM-compatible)
  3. Pinned to IPFS via Pinata
  4. Committed onchain as a single Epochs table row (stateRoot + CID)

Anyone can reconstruct: fetch snapshot from IPFS → recompute root → compare onchain.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid as _uuid
from typing import Any

from eth_hash.auto import keccak

from memento.bonfires_client import get_client
from memento.tools.ipfs import pin_json

logger = logging.getLogger(__name__)


# ── Snapshot ──

def snapshot_state() -> dict[str, Any]:
    """Query KG for all game entities and return a deterministic snapshot.

    Returns dict with keys: characters, items, locations, factions, quests, npcs, edges.
    Each value is a sorted list of entity dicts.
    """
    client = get_client()

    entity_types = ["Character", "Player", "NPC", "Item", "Location", "Region", "Faction", "Quest"]
    all_entities: dict[str, list[dict]] = {}

    for etype in entity_types:
        try:
            result = client.kg.search(etype, num_results=500)
            entities = result.get("entities", result.get("nodes", []))
            # Filter to only entities with matching label
            matching = [
                _normalize_entity(e) for e in entities
                if etype in e.get("labels", [])
            ]
            all_entities[etype.lower()] = sorted(matching, key=lambda e: e.get("uuid", ""))
        except Exception:
            all_entities[etype.lower()] = []

    # Collect edges
    edges: list[dict] = []
    try:
        result = client.kg.search("", num_results=500)
        raw_edges = result.get("edges", [])
        edges = sorted(
            [_normalize_edge(e) for e in raw_edges],
            key=lambda e: (e.get("source", ""), e.get("target", ""), e.get("relationship", "")),
        )
    except Exception:
        pass

    return {
        "version": 1,
        "entities": all_entities,
        "edges": edges,
    }


def _normalize_entity(e: dict) -> dict:
    """Extract a stable subset of entity fields for hashing."""
    return {
        "uuid": str(e.get("uuid", "")),
        "name": e.get("name", ""),
        "labels": sorted(e.get("labels", [])),
        "summary": e.get("summary", ""),
    }


def _normalize_edge(e: dict) -> dict:
    """Extract a stable subset of edge fields for hashing."""
    return {
        "source": e.get("source_name", e.get("source", "")),
        "target": e.get("target_name", e.get("target", "")),
        "relationship": e.get("relationship", e.get("name", "")),
        "fact": e.get("fact", ""),
    }


# ── Merkle root ──

def compute_merkle_root(snapshot: dict) -> bytes:
    """Compute a keccak256 merkle root over the snapshot.

    Leaf nodes are keccak256 hashes of each entity's canonical JSON.
    The tree is built bottom-up with sorted pair hashing for determinism.
    """
    leaves: list[bytes] = []

    # Hash each entity across all types
    for _etype, entities in sorted(snapshot.get("entities", {}).items()):
        for entity in entities:
            canonical = json.dumps(entity, sort_keys=True, separators=(",", ":")).encode()
            leaves.append(keccak(canonical))

    # Hash each edge
    for edge in snapshot.get("edges", []):
        canonical = json.dumps(edge, sort_keys=True, separators=(",", ":")).encode()
        leaves.append(keccak(canonical))

    if not leaves:
        return b"\x00" * 32

    # Build merkle tree bottom-up
    while len(leaves) > 1:
        next_level: list[bytes] = []
        for i in range(0, len(leaves), 2):
            if i + 1 < len(leaves):
                # Sort pair for determinism
                pair = sorted([leaves[i], leaves[i + 1]])
                next_level.append(keccak(pair[0] + pair[1]))
            else:
                next_level.append(leaves[i])
        leaves = next_level

    return leaves[0]


# ── IPFS pin ──

def pin_snapshot(snapshot: dict) -> tuple[str | None, bytes | None]:
    """Pin the full snapshot to IPFS via Pinata.

    Returns (cid, content_hash) or (None, None) if disabled/failed.
    """
    return pin_json(snapshot)


# ── Onchain commit ──

def _commit_onchain(epoch_id: bytes, state_root: bytes, ipfs_cid: str, tick: int, entity_count: int, metadata: str) -> None:
    """Submit epoch commitment to the MUD World contract. Fire-and-forget."""
    from memento.tools.chain import _get_web3, _get_abi

    def _do():
        try:
            w3, account, world_addr = _get_web3()
            if not w3 or not account or not world_addr:
                return

            contract = w3.eth.contract(address=world_addr, abi=_get_abi())
            fn = contract.functions.memento__commitEpoch(
                epoch_id, state_root, ipfs_cid, tick, entity_count, metadata,
            )
            tx = fn.build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 500_000,
                "gasPrice": w3.eth.gas_price,
            })
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            logger.info(f"Epoch committed onchain: {tx_hash.hex()}")
        except Exception as e:
            logger.warning(f"Epoch onchain commit failed: {e}")

    threading.Thread(target=_do, daemon=True).start()


# ── Orchestrator ──

def run_epoch(tick: int = 0) -> dict[str, Any]:
    """Run a full epoch: snapshot → merkle root → IPFS pin → onchain commit.

    Returns epoch metadata dict.
    """
    from memento.tools.chain import is_enabled

    logger.info("Starting epoch...")

    # 1. Snapshot
    snapshot = snapshot_state()
    entity_count = sum(len(ents) for ents in snapshot.get("entities", {}).values())

    # 2. Merkle root
    state_root = compute_merkle_root(snapshot)
    logger.info(f"Epoch state root: 0x{state_root.hex()[:16]}... ({entity_count} entities)")

    # 3. Pin to IPFS
    ipfs_cid, _content_hash = pin_snapshot(snapshot)

    # 4. Commit onchain
    epoch_id_str = _uuid.uuid4().hex
    epoch_id = bytes.fromhex(epoch_id_str.ljust(64, "0")[:64])
    metadata = json.dumps({"entity_count": entity_count, "tick": tick}, sort_keys=True)

    if is_enabled() and ipfs_cid:
        _commit_onchain(epoch_id, state_root, ipfs_cid, tick, entity_count, metadata)
    elif not is_enabled():
        logger.info("Epoch: chain disabled, skipping onchain commit")
    elif not ipfs_cid:
        logger.warning("Epoch: IPFS pin failed, skipping onchain commit")

    result = {
        "epoch_id": epoch_id_str,
        "state_root": "0x" + state_root.hex(),
        "ipfs_cid": ipfs_cid,
        "entity_count": entity_count,
        "tick": tick,
    }
    logger.info(f"Epoch complete: {result}")
    return result
