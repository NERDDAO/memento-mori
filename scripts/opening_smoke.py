"""Smoke-test the opening arc endpoints against a running gateway.

Usage::

    GATEWAY_URL=http://localhost:8090 python scripts/opening_smoke.py

Reads ``GATEWAY_URL`` from the environment (or ``.env``).  If the gateway is
not reachable (env var absent or health probe fails), exits cleanly with a SKIP
message — this is expected in CI and local environments without the full stack.

When the gateway IS reachable the script drives the canonical opening-arc beats
over HTTP:

  1. POST /api/opening/start  — create player, get room manifest + epigraph.
  2. POST /api/opening/act    — "look around"  → status "narrated" + narration.
  3. POST /api/opening/act    — "take the iron blade" → status "executed" (not error).
  4. POST /api/opening/act    — "go on"        → won == True.

All network I/O is guarded behind ``if __name__ == "__main__":`` so that
``import scripts.opening_smoke`` is fully side-effect-free.

COMPREHENSION CAVEAT
--------------------
The live path calls the real comprehension client (HttpComprehensionClient when
KERNEL_BASE_URL + GM_INTERNAL_TOKEN are set, else NullComprehensionClient).
The script uses the canonical beat utterances that map deterministically in the
test suite.  If the live comprehension client returns "clarify" for any beat,
the script reports that clearly (FAIL with the actual status) rather than
hanging.  Adjust the utterances or configure the comprehension env-vars if the
live stack phrases things differently.
"""

import os
import sys


# ---------------------------------------------------------------------------
# Reachability probe — no network I/O, just env check + fast HTTP HEAD
# ---------------------------------------------------------------------------


def _gateway_reachable() -> tuple[bool, str]:
    """Return (reachable, reason).

    Reachable when GATEWAY_URL is set AND a GET probe returns 2xx within 5 s.
    """
    base_url = os.environ.get("GATEWAY_URL", "")
    if not base_url:
        return False, "GATEWAY_URL not set"

    try:
        import httpx  # noqa: PLC0415

        with httpx.Client(timeout=5.0) as c:
            # Probe the root; most FastAPI apps return 200 or 404 (still reachable).
            resp = c.get(f"{base_url.rstrip('/')}/")
        if resp.status_code < 500:
            return True, base_url
        return False, f"gateway health probe returned {resp.status_code}"
    except Exception as exc:
        return False, f"gateway not reachable: {exc}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check(ok: bool, label: str, detail: str = "") -> None:
    if ok:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}{': ' + detail if detail else ''}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Smoke runner — all network I/O lives here
# ---------------------------------------------------------------------------


def run_smoke() -> None:
    reachable, reason = _gateway_reachable()
    if not reachable:
        print(f"SKIP: {reason}")
        print("      Set GATEWAY_URL to run the full opening-arc smoke test.")
        return

    import httpx  # noqa: PLC0415

    base_url = os.environ["GATEWAY_URL"].rstrip("/")
    print(f"Opening-arc smoke: gateway @ {base_url}")

    client = httpx.Client(base_url=base_url, timeout=30.0)

    try:
        # ------------------------------------------------------------------
        # Beat 1 — start the opening arc
        # ------------------------------------------------------------------
        print("  POST /api/opening/start ...")
        start_resp = client.post(
            "/api/opening/start",
            json={
                "player_name": "SmokeHero",
                "wallet_address": "0xDeAdBeEfDeAdBeEfDeAdBeEfDeAdBeEfDeAdBeEf",
                "archetype": "wanderer",
            },
        )
        _check(
            start_resp.status_code == 200,
            "start returns 200",
            f"got {start_resp.status_code}: {start_resp.text[:200]}",
        )

        data = start_resp.json()
        player_id = data.get("player_id", "")
        _check(bool(player_id), "start response has player_id")

        epigraph = data.get("epigraph", "")
        _check(bool(epigraph), "start response has epigraph (opening quote)")

        location_name = data.get("location_name", "")
        description = data.get("description", "")
        _check(
            bool(location_name) and bool(description),
            "start response has location_name + description",
            f"location_name={location_name!r} description={description[:60]!r}",
        )
        print(f"    player_id : {player_id}")
        print(f"    location  : {location_name}")
        print(f"    epigraph  : {epigraph[:80]}")

        # ------------------------------------------------------------------
        # Beat 2 — "look around" → narrated
        # ------------------------------------------------------------------
        print("  POST /api/opening/act  [look around] ...")
        look_resp = client.post(
            "/api/opening/act",
            json={"player_id": player_id, "text": "look around"},
        )
        _check(
            look_resp.status_code == 200,
            "act/look returns 200",
            f"got {look_resp.status_code}: {look_resp.text[:200]}",
        )
        look_data = look_resp.json()
        look_status = look_data.get("status", "")
        _check(
            look_status == "narrated",
            "look → status == 'narrated'",
            f"got status={look_status!r} (comprehension may need KERNEL_BASE_URL set)",
        )
        narration = look_data.get("narration") or ""
        _check(
            bool(narration),
            "look → non-empty narration",
            f"narration={narration!r}",
        )
        print(f"    narration : {narration[:80]}")

        # ------------------------------------------------------------------
        # Beat 3 — "take the iron blade" → executed (not error/clarify)
        # ------------------------------------------------------------------
        print("  POST /api/opening/act  [take the iron blade] ...")
        take_resp = client.post(
            "/api/opening/act",
            json={"player_id": player_id, "text": "take the iron blade"},
        )
        _check(
            take_resp.status_code == 200,
            "act/take returns 200",
            f"got {take_resp.status_code}: {take_resp.text[:200]}",
        )
        take_data = take_resp.json()
        take_status = take_data.get("status", "")
        # The TAKE beat must not return an error or clarify; "executed" is the
        # canonical status.  If the live comprehension returns "clarify", the
        # failure message names it explicitly so the operator knows to configure
        # KERNEL_BASE_URL / GM_INTERNAL_TOKEN.
        _check(
            take_status == "executed",
            "take → status == 'executed'",
            f"got status={take_status!r} (if 'clarify': comprehension may not be wired; "
            "set KERNEL_BASE_URL + GM_INTERNAL_TOKEN)",
        )
        print(f"    take status : {take_status}")

        # ------------------------------------------------------------------
        # Beat 4 — "go on" → won == True
        # ------------------------------------------------------------------
        print("  POST /api/opening/act  [go on] ...")
        go_resp = client.post(
            "/api/opening/act",
            json={"player_id": player_id, "text": "go on"},
        )
        _check(
            go_resp.status_code == 200,
            "act/go returns 200",
            f"got {go_resp.status_code}: {go_resp.text[:200]}",
        )
        go_data = go_resp.json()
        go_status = go_data.get("status", "")
        won = go_data.get("won", False)
        _check(
            won is True,
            "go → won == True",
            f"got status={go_status!r} won={won!r}",
        )
        print(f"    go status : {go_status}  won={won}")

        # ------------------------------------------------------------------
        # Post-win — session must be gone from registry (404 on next act)
        # ------------------------------------------------------------------
        probe_resp = client.post(
            "/api/opening/act",
            json={"player_id": player_id, "text": "look around"},
        )
        _check(
            probe_resp.status_code == 404,
            "post-win act returns 404 (registry dropped)",
            f"got {probe_resp.status_code}",
        )

    finally:
        client.close()

    print("Smoke OK")


if __name__ == "__main__":
    # Load .env if present (mirrors gm_room_smoke.py dotenv pattern)
    _dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(_dotenv_path):
        try:
            from dotenv import load_dotenv  # type: ignore[import]

            load_dotenv(_dotenv_path)
        except ImportError:
            pass  # dotenv optional

    # Ensure engine + gateway packages are importable when invoked directly
    _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for _pkg_src in (
        os.path.join(_repo_root, "gateway", "src"),
        os.path.join(_repo_root, "engine", "src"),
    ):
        if _pkg_src not in sys.path:
            sys.path.insert(0, _pkg_src)

    run_smoke()
