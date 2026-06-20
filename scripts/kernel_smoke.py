"""Smoke-test the graph-memory (kernel) service.

Usage::

    python scripts/kernel_smoke.py

Reads ``KERNEL_BASE_URL`` and ``GM_INTERNAL_TOKEN`` from the environment (or
``.env``).  POSTs a tiny index document for the fixture bonfire, then issues a
search, prints both HTTP status codes, and exits non-zero on any non-2xx
response.

All network I/O is guarded behind ``if __name__ == "__main__":`` so that
``import scripts.kernel_smoke`` and ``python -m py_compile`` are fully
side-effect-free.
"""

import os
import sys


def _build_headers(token: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _check(resp, label: str) -> None:
    """Print status and exit non-zero if not 2xx."""
    print(f"{label}: HTTP {resp.status_code}")
    if not (200 <= resp.status_code < 300):
        print(f"ERROR: {label} returned {resp.status_code}", file=sys.stderr)
        sys.exit(1)


def run_smoke() -> None:
    import httpx  # local import — keeps module importable without httpx

    base_url = os.environ.get("KERNEL_BASE_URL", "http://localhost:8001").rstrip("/")
    token = os.environ.get("GM_INTERNAL_TOKEN", "")
    bonfire_id = "6650000000000000000000f1"  # mm-world-v1 fixture bonfire

    headers = _build_headers(token)

    # --- kernel/index ---
    index_payload = {
        "bonfire_id": bonfire_id,
        "document": {
            "id": "smoke-doc-1",
            "text": "Smoke test document for kernel health check.",
        },
    }
    with httpx.Client(timeout=15) as client:
        resp_index = client.post(
            f"{base_url}/kernel/index",
            json=index_payload,
            headers=headers,
        )
        _check(resp_index, "kernel/index")

        # --- kernel/search ---
        search_payload = {
            "bonfire_id": bonfire_id,
            "query": "smoke test",
            "top_k": 3,
        }
        resp_search = client.post(
            f"{base_url}/kernel/search",
            json=search_payload,
            headers=headers,
        )
        _check(resp_search, "kernel/search")

    print("Smoke OK")


if __name__ == "__main__":
    run_smoke()
