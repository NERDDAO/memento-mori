"""Pinata IPFS pinning for episode content.

Uploads JSON blobs to Pinata and returns (CID, keccak256_hash).
The keccak256 hash is stored onchain; the CID is stored in Pinata pin metadata
for reverse lookup during verification.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import requests
from eth_hash.auto import keccak

from memento.config.chain import PINATA_JWT

logger = logging.getLogger(__name__)

PINATA_PIN_URL = "https://api.pinata.cloud/pinning/pinJSONToIPFS"


def _hash_json(data: dict) -> bytes:
    """Compute keccak256 of canonical JSON (sorted keys, compact separators)."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return keccak(canonical)


def pin_json(data: dict) -> tuple[Optional[str], Optional[bytes]]:
    """Pin JSON to Pinata IPFS.

    Returns:
        (cid, keccak256_hash) on success, (None, None) on failure or if disabled.
    """
    if not PINATA_JWT:
        logger.debug("IPFS disabled — PINATA_JWT not set")
        return None, None

    content_hash = _hash_json(data)

    body = {
        "pinataContent": data,
        "pinataMetadata": {
            "name": f"memento-episode-{data.get('episodeId', 'unknown')}",
            "keyvalues": {
                "keccak256": "0x" + content_hash.hex(),
            },
        },
    }

    try:
        resp = requests.post(
            PINATA_PIN_URL,
            json=body,
            headers={
                "Authorization": f"Bearer {PINATA_JWT}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        cid = resp.json()["IpfsHash"]
        logger.info(f"Pinned episode to IPFS: {cid} (hash: 0x{content_hash.hex()[:16]}...)")
        return cid, content_hash
    except Exception as e:
        logger.warning(f"Pinata upload failed: {e}")
        return None, None
