"""Text generation for procgen scaffolds.

Uses TrimTab (cascading embedding search) when indexed grammars are available,
falls back to Tracery (random expansion) otherwise. TrimTab provides context-aware
selection — the same grammar produces different output depending on the scene context.
"""

import json
import logging
import random
from pathlib import Path

import tracery
from tracery.modifiers import base_english

_GRAMMARS_DIR = Path(__file__).resolve().parents[4] / "assets" / "atlas" / "grammars"
_GRAMMAR_CACHE: dict[str, dict] = {}
_TRIMTAB_CACHE: dict[str, object] = {}

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


def _get_trimtab(name: str):
    """Load a TrimTab indexed grammar if available. Returns None if not indexed."""
    if name in _TRIMTAB_CACHE:
        return _TRIMTAB_CACHE[name]
    sg_path = _GRAMMARS_DIR / f"{name}.sg"
    if not sg_path.exists():
        _TRIMTAB_CACHE[name] = None
        return None
    try:
        from trimtab import SmartGrammar
        sg = SmartGrammar.load(str(sg_path))
        _TRIMTAB_CACHE[name] = sg
        return sg
    except Exception:
        logger.debug("TrimTab not available for %s, using Tracery fallback", name)
        _TRIMTAB_CACHE[name] = None
        return None


def generate_text(
    grammar_name: str,
    overrides: dict | None = None,
    seed: int | None = None,
    context: str = "",
    temperature: float = 0.3,
) -> str:
    """Generate text from a named grammar file.

    Uses TrimTab (embedding-based selection) if an indexed .sg directory exists,
    otherwise falls back to Tracery (random expansion).

    Args:
        grammar_name: Name of the grammar file (without .json).
        overrides: Optional dict of rule overrides (Tracery mode only).
        seed: Random seed for deterministic output.
        context: Context string for TrimTab embedding search.
        temperature: TrimTab temperature (0=deterministic, 1=random).

    Returns:
        Generated text string, or empty string if grammar not found.
    """
    # Try TrimTab first (context-aware)
    if context and not overrides:
        sg = _get_trimtab(grammar_name)
        if sg is not None:
            try:
                return sg.generate(context=context, temperature=temperature, seed=seed)
            except Exception:
                logger.debug("TrimTab generation failed, falling back to Tracery")

    # Fallback: Tracery (random)
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


def generate_narration_scaffold(seed: int | None = None, context: str = "") -> str:
    """Generate an atmospheric narration sentence for scaffold."""
    return generate_text("narration", seed=seed, context=context)


def generate_location_scaffold(seed: int | None = None, context: str = "") -> str:
    """Generate a location description scaffold."""
    return generate_text("location_desc", seed=seed, context=context)


def generate_npc_scaffold(role: str = "", location: str = "", seed: int | None = None) -> str:
    """Generate a full NPC scaffold with name, appearance, and personality."""
    ctx = f"{role}, {location}" if role and location else role or location or ""
    name = generate_text("npc_names", seed=seed, context=ctx)
    base_seed = seed or 0
    appearance = generate_text("npc_appearance", seed=base_seed + 1 if seed else None, context=ctx)
    personality = generate_text("npc_personality", seed=base_seed + 2 if seed else None, context=ctx)

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
