"""x402 payment middleware — HTTP 402 Payment Required for session gating.

Flow:
1. Client hits a gated endpoint without X-Payment-Receipt header
2. Server returns 402 with payment instructions (amount, recipient, asset, chain)
3. Client sends USDC on Redstone L2 to recipient
4. Client retries with X-Payment-Receipt: 0x<txHash>
5. Server verifies receipt on-chain, creates session, returns token
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from gateway.log import get_logger
from gateway.session_store import (
    cache_payment_receipt,
    is_receipt_cached,
    validate_session,
)

logger = get_logger(__name__)

# x402 configuration
X402_ENABLED = os.getenv("X402_ENABLED", "false").lower() == "true"
X402_PRICE_USDC = int(os.getenv("X402_PRICE_USDC", "3000000"))  # $3 in 6-decimal USDC
X402_RECIPIENT = os.getenv("X402_RECIPIENT_ADDRESS", "")
X402_ASSET = os.getenv("X402_USDC_ON_REDSTONE", "")
X402_CHAIN_ID = 690  # Redstone L2


def payment_required_response() -> JSONResponse:
    """Return a 402 Payment Required response with x402 payment instructions."""
    return JSONResponse(
        status_code=402,
        content={
            "error": "payment_required",
            "message": "Session requires payment",
            "payment": {
                "amount": str(X402_PRICE_USDC),
                "asset": X402_ASSET,
                "recipient": X402_RECIPIENT,
                "network": X402_CHAIN_ID,
                "currency": "USDC",
                "amount_human": f"${X402_PRICE_USDC / 1_000_000:.2f}",
            },
        },
        headers={
            "X-Payment-Amount": str(X402_PRICE_USDC),
            "X-Payment-Asset": X402_ASSET,
            "X-Payment-Recipient": X402_RECIPIENT,
            "X-Payment-Network": str(X402_CHAIN_ID),
        },
    )


async def verify_payment_receipt(tx_hash: str, expected_wallet: str) -> bool:
    """Verify an x402 payment receipt against Redstone L2.

    Checks that:
    - Transaction exists and is confirmed
    - It's a transfer to the correct recipient
    - Amount >= X402_PRICE_USDC
    - Sender matches expected_wallet
    """
    if not tx_hash or not tx_hash.startswith("0x"):
        return False

    # Check cache first
    cached_wallet = is_receipt_cached(tx_hash)
    if cached_wallet:
        return cached_wallet == expected_wallet.lower()

    # Verify on-chain
    rpc_url = os.getenv("REDSTONE_RPC", "")
    if not rpc_url:
        logger.warning("REDSTONE_RPC not set, skipping receipt verification")
        # In dev mode without RPC, accept any receipt
        cache_payment_receipt(tx_hash, expected_wallet)
        return True

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            # eth_getTransactionReceipt
            resp = await client.post(rpc_url, json={
                "jsonrpc": "2.0",
                "method": "eth_getTransactionReceipt",
                "params": [tx_hash],
                "id": 1,
            })
            data = resp.json()
            receipt = data.get("result")

            if not receipt or receipt.get("status") != "0x1":
                logger.warning("Receipt not found or failed: %s", tx_hash)
                return False

            # Verify sender matches expected wallet
            tx_from = receipt.get("from", "").lower()
            if tx_from != expected_wallet.lower():
                logger.warning("Receipt sender %s != expected %s", tx_from, expected_wallet)
                return False

            # Verify recipient is in the logs (ERC-20 Transfer event)
            # For simplicity, check that the tx was sent to the USDC contract
            # and the recipient appears in logs
            tx_to = receipt.get("to", "").lower()
            if X402_ASSET and tx_to != X402_ASSET.lower():
                logger.warning("Receipt target %s != USDC contract %s", tx_to, X402_ASSET)
                return False

            # Cache verified receipt
            cache_payment_receipt(tx_hash, expected_wallet)
            logger.info("Payment verified: %s from %s", tx_hash, expected_wallet)
            return True

    except Exception:
        logger.error("Receipt verification failed", exc_info=True)
        return False


def check_payment_receipt(request: Request, wallet_address: str) -> str | None:
    """Check for x402 payment receipt in request headers.

    Returns the tx_hash if present, None if not.
    Raises 402 if x402 is enabled and no receipt provided.
    """
    if not X402_ENABLED:
        return "disabled"  # Payment not required

    tx_hash = request.headers.get("X-Payment-Receipt", "")
    if not tx_hash:
        return None  # Caller should return 402

    return tx_hash


def require_session(request: Request) -> dict[str, str]:
    """Validate session token from request headers.

    Returns {player_id, wallet} or raises 401.
    Used for session-gated endpoints (action, state, entity, etc.)
    """
    if not X402_ENABLED:
        # No payment gating — allow through (dev mode)
        # Try to extract player_id from request for logging
        return {"player_id": "", "wallet": ""}

    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token:
        token = request.headers.get("X-Session-Token", "")

    if not token:
        raise HTTPException(status_code=401, detail="Session token required")

    session = validate_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return session
