"""Generalizable JSON grammar/table updater tool.

Allows crews to write back to Tracery grammar files and stat/loot table files,
making the procgen data layer self-improving over time. Works with any JSON file
under engine/assets/atlas/.
"""

import json
import logging
from pathlib import Path

from crewai.tools import tool

_ATLAS_DIR = Path(__file__).resolve().parents[3] / "assets" / "atlas"

logger = logging.getLogger(__name__)


def _resolve_path(file_path: str, base_dir=None) -> Path:
    """Resolve a file path relative to the atlas directory."""
    base = Path(base_dir) if base_dir else _ATLAS_DIR
    path = base / f"{file_path}.json"
    return path


def _get_nested(data: dict, key_path: str):
    """Get a value from a nested dict using dot-separated path."""
    keys = key_path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def _set_nested(data: dict, key_path: str, value, mode: str = "append") -> None:
    """Set or append a value in a nested dict using dot-separated path.

    mode="append": Append value to existing list (create list if key doesn't exist)
    mode="set": Set the key to the value directly
    """
    keys = key_path.split(".")
    current = data

    # Navigate to parent
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]

    final_key = keys[-1]

    if mode == "set":
        # Parse JSON strings for complex values
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                pass
        current[final_key] = value
    else:  # append
        if final_key not in current:
            current[final_key] = []
        target = current[final_key]
        if isinstance(target, list):
            if value not in target:  # no duplicates
                target.append(value)
        elif isinstance(target, dict):
            # For dicts, merge
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass
            if isinstance(value, dict):
                target.update(value)


@tool("update_grammar")
def update_grammar(
    file_path: str,
    key_path: str,
    value: str,
    mode: str = "append",
    _base_dir: str | None = None,
) -> str:
    """Update a Tracery grammar or JSON table file by adding/setting values.

    This tool allows crews to write back to the procgen data layer,
    making grammars and tables self-improving over time.

    Args:
        file_path: Relative path within assets/atlas/ without .json extension.
                   E.g. "grammars/npc_names" or "tables/item_affixes"
        key_path: Dot-separated path to the key to update.
                  E.g. "first" or "prefixes.rare" or "warrior.ability_pool"
        value: Value to add. For append mode, this is added to the array.
               For set mode, this replaces the key. Complex values should be JSON strings.
        mode: "append" to add to array (default), "set" to replace/create key.

    Returns:
        Confirmation message.
    """
    path = _resolve_path(file_path, base_dir=_base_dir)

    if not path.exists():
        return f"FAIL: File not found: {path}"

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return f"FAIL: Invalid JSON in {path}: {e}"

    _set_nested(data, key_path, value, mode=mode)

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    # Clear grammar cache and update TrimTab index if available
    grammar_name = file_path.split("/")[-1]
    try:
        from memento.tools.procgen.text_gen import _GRAMMAR_CACHE, _TRIMTAB_CACHE
        _GRAMMAR_CACHE.pop(grammar_name, None)
        _TRIMTAB_CACHE.pop(grammar_name, None)
    except ImportError:
        pass

    # If this is a grammar file and has a .sg index, add to TrimTab directly
    if file_path.startswith("grammars/") and mode == "append":
        sg_dir = path.parent / f"{grammar_name}.sg"
        if sg_dir.exists():
            try:
                from trimtab import SmartGrammar
                sg = SmartGrammar.load(str(sg_dir))
                # key_path is the rule name for grammar files
                sg.add(key_path, value)
                sg.save(str(sg_dir))
                logger.info("TrimTab index updated for %s.%s", grammar_name, key_path)
            except Exception:
                logger.debug("TrimTab index update skipped for %s", grammar_name)

    logger.info("Updated %s at key '%s' (mode=%s)", file_path, key_path, mode)
    return f"Updated {file_path} at '{key_path}'"
