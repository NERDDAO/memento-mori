"""Tracery-based text generation for procgen scaffolds.

Loads JSON grammar files and generates text using the Tracery library.
Each grammar file defines expansion rules for a specific domain
(narration, NPC names, item names, etc).
"""

import json
import logging
import random
from pathlib import Path

import tracery
from tracery.modifiers import base_english

_GRAMMARS_DIR = Path(__file__).resolve().parents[4] / "assets" / "atlas" / "grammars"
_GRAMMAR_CACHE: dict[str, dict] = {}

logger = logging.getLogger(__name__)


def _load_grammar(name: str) -> dict | None:
    """Load a grammar file by name. Returns None if not found."""
    if name in _GRAMMAR_CACHE:
        return _GRAMMAR_CACHE[name]
    path = _GRAMMARS_DIR / f"{name}.json"
    if not path.exists():
        logger.warning("Grammar file not found: %s", path)
        return None
    data = json.loads(path.read_text())
    _GRAMMAR_CACHE[name] = data
    return data


def generate_text(grammar_name: str, overrides: dict | None = None, seed: int | None = None) -> str:
    """Generate text from a named grammar file.

    Args:
        grammar_name: Name of the grammar file (without .json).
        overrides: Optional dict of rule overrides to merge into the grammar.
        seed: Random seed for deterministic output.

    Returns:
        Generated text string, or empty string if grammar not found.
    """
    rules = _load_grammar(grammar_name)
    if rules is None:
        return ""

    merged = dict(rules)
    if overrides:
        merged.update(overrides)

    if seed is not None:
        random.seed(seed)

    grammar = tracery.Grammar(merged)
    grammar.add_modifiers(base_english)
    result = grammar.flatten("#origin#")

    if seed is not None:
        random.seed()

    return result


def generate_npc_name(seed: int | None = None) -> str:
    """Generate a fantasy NPC name."""
    return generate_text("npc_names", seed=seed)


def generate_narration_scaffold(seed: int | None = None) -> str:
    """Generate an atmospheric narration sentence for scaffold."""
    return generate_text("narration", seed=seed)


def generate_location_scaffold(seed: int | None = None) -> str:
    """Generate a location description scaffold."""
    return generate_text("location_desc", seed=seed)


def generate_npc_scaffold(role: str = "", location: str = "", seed: int | None = None) -> str:
    """Generate a full NPC scaffold with name, appearance, and personality."""
    name = generate_text("npc_names", seed=seed)
    base_seed = seed or 0
    appearance = generate_text("npc_appearance", seed=base_seed + 1 if seed else None)
    personality = generate_text("npc_personality", seed=base_seed + 2 if seed else None)

    parts = []
    if role:
        parts.append(f"Role: {role}")
    if location:
        parts.append(f"Location: {location}")
    parts.extend([
        f"Name: {name}",
        f"Appearance: {appearance}",
        f"Personality: {personality}",
    ])

    return "\n".join(parts)


def generate_item_name(slot: str = "weapon", rarity: str = "common", seed: int | None = None) -> str:
    """Generate an item name appropriate for the given slot and rarity."""
    prefix_key = f"{rarity}_prefix"
    base_key = f"{slot}_base" if slot in ("weapon", "armor", "accessory", "ring", "consumable") else "weapon_base"
    suffix_key = f"{slot}_suffix" if slot in ("weapon", "armor", "accessory", "ring") else ""

    overrides: dict[str, list[str]] = {
        "prefix": [f"#{prefix_key}#"],
        "base": [f"#{base_key}#"],
    }

    if rarity in ("rare", "epic", "legendary") and suffix_key:
        overrides["origin"] = [f"#prefix# #base# #suffix#"]
        overrides["suffix"] = [f"#{suffix_key}#"]
    else:
        overrides["origin"] = ["#prefix# #base#"]

    return generate_text("item_names", overrides=overrides, seed=seed)
