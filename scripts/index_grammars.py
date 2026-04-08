#!/usr/bin/env python3
"""Bootstrap script: index all Tracery grammars with TrimTab for embedding search.

Run once after cloning or when grammar files change significantly.
After this, individual updates via update_grammar tool keep indices current.

Usage:
    python scripts/index_grammars.py
"""

import sys
from pathlib import Path

GRAMMARS_DIR = Path(__file__).resolve().parents[1] / "engine" / "assets" / "atlas" / "grammars"


def main():
    try:
        from trimtab import SmartGrammar
    except ImportError:
        print("TrimTab not installed. Run: pip install trimtab")
        sys.exit(1)

    grammar_files = sorted(GRAMMARS_DIR.glob("*.json"))
    if not grammar_files:
        print(f"No grammar files found in {GRAMMARS_DIR}")
        sys.exit(1)

    print(f"Indexing {len(grammar_files)} grammars in {GRAMMARS_DIR}")

    for path in grammar_files:
        sg_dir = path.with_suffix(".sg")
        name = path.stem
        try:
            sg = SmartGrammar.from_file(str(path))
            sg.index()
            sg.save(str(sg_dir))
            rule_count = len(sg._index.grammar.rule_names())
            print(f"  {name}: {rule_count} rules indexed -> {sg_dir.name}/")
        except Exception as e:
            print(f"  {name}: FAILED ({e})")

    print("Done.")


if __name__ == "__main__":
    main()
