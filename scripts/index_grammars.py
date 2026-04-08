#!/usr/bin/env python3
"""Bootstrap: upload all local grammar JSONs to delve via the Bonfires SDK.

Runs through every ``*.json`` file in ``engine/assets/atlas/grammars/``
and POSTs each one to delve as a TrimTab grammar. Delve's
TrimtabGrammarController embeds the expansions, stores them in the
in-memory ``TrimTabDB`` for cascading search, and persists them to
MongoDB so the next ``delve`` startup rehydrates them automatically.

Usage:
    python scripts/index_grammars.py

Requires the Bonfires SDK env vars to be set (``BONFIRES_API_URL``,
``BONFIRES_API_KEY``, ``BONFIRE_ID``) — same config the rest of mmori
reads via ``memento.bonfires_client.get_client()``.

After running:
- Every grammar is searchable via ``client.trimtab.search(grammar=...)``
  (cascaded or scoped).
- Future edits via the ``update_grammar`` crewai tool will push
  expansion deltas to delve automatically.
- On delve restart, the grammars are rehydrated from Mongo by
  ``TrimtabGrammarController.hydrate_from_mongo``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_GRAMMARS_DIR = (
    Path(__file__).resolve().parents[1] / "engine" / "assets" / "atlas" / "grammars"
)


def main() -> None:
    try:
        from memento.bonfires_client import get_client
    except ImportError as e:
        print(f"Bonfires SDK not importable: {e}", file=sys.stderr)
        print("Make sure mmori's engine env is active.", file=sys.stderr)
        sys.exit(1)

    grammar_files = sorted(_GRAMMARS_DIR.glob("*.json"))
    if not grammar_files:
        print(f"No grammar files found in {_GRAMMARS_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"Uploading {len(grammar_files)} grammars from {_GRAMMARS_DIR} to delve")

    client = get_client()
    ok = 0
    failed = 0

    for path in grammar_files:
        name = path.stem
        try:
            rules = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            print(f"  {name}: SKIP (invalid JSON: {e})")
            failed += 1
            continue

        if not isinstance(rules, dict):
            print(f"  {name}: SKIP (top level must be an object)")
            failed += 1
            continue

        try:
            result = client.trimtab.create(grammar=name, rules=rules)
            total = result.get("total_expansions", 0)
            rule_count = result.get("rules_count", len(rules))
            print(f"  {name}: OK ({rule_count} rules, {total} expansions)")
            ok += 1
        except Exception as e:
            print(f"  {name}: FAILED ({e})")
            failed += 1

    print(f"\nDone. {ok} uploaded, {failed} failed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
