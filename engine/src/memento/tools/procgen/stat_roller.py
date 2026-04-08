"""NPC stat roller and item loot roller from JSON table configs.

Generates deterministic stat blocks and loot drops from archetype
templates and rarity-weighted tables. Designed to provide scaffolds
for LLM crews — the LLM refines what the tables produce.
"""

import json
import random
from pathlib import Path

_TABLES_DIR = Path(__file__).resolve().parents[4] / "assets" / "atlas" / "tables"

_ARCHETYPES: dict = {}
_LOOT_TABLES: dict = {}
_AFFIXES: dict = {}


def _ensure_loaded() -> None:
    if _ARCHETYPES:
        return
    _ARCHETYPES.update(json.loads((_TABLES_DIR / "npc_archetypes.json").read_text()))
    _LOOT_TABLES.update(json.loads((_TABLES_DIR / "loot_tables.json").read_text()))
    _AFFIXES.update(json.loads((_TABLES_DIR / "item_affixes.json").read_text()))


def load_archetypes() -> dict:
    """Load and return NPC archetype data."""
    _ensure_loaded()
    return dict(_ARCHETYPES)


def load_loot_tables() -> dict:
    """Load and return loot table data."""
    _ensure_loaded()
    return dict(_LOOT_TABLES)


def roll_npc_stats(archetype: str, seed: int | None = None) -> dict:
    """Roll a stat block from an archetype template.

    Args:
        archetype: Archetype name (warrior, scholar, merchant, etc).
                   Falls back to 'default' if not found.
        seed: Random seed for deterministic output.

    Returns:
        Dict with STR, DEX, CON, INT, WIS, CHA, skills, abilities.
    """
    _ensure_loaded()
    rng = random.Random(seed)

    arch = _ARCHETYPES.get(archetype, _ARCHETYPES["default"])
    stat_range = arch["stat_range"]
    priority = arch["stat_priority"]

    stats: dict[str, int] = {}
    for i, stat_name in enumerate(priority):
        if i < 2:
            lo, hi = stat_range["primary"]
        elif i < 4:
            lo, hi = stat_range["secondary"]
        else:
            lo, hi = stat_range["dump"]
        stats[stat_name] = rng.randint(lo, hi)

    num_abilities = rng.randint(1, min(3, len(arch["ability_pool"])))
    abilities = rng.sample(arch["ability_pool"], num_abilities)

    return {
        **stats,
        "skills": list(arch["skills"]),
        "abilities": abilities,
    }


def _roll_rarity(budget: str, rng: random.Random) -> str:
    """Roll a rarity tier from the budget's weight table."""
    _ensure_loaded()
    weights = _LOOT_TABLES["rarity_weights"].get(budget, _LOOT_TABLES["rarity_weights"]["common"])
    rarities = list(weights.keys())
    weight_values = list(weights.values())
    return rng.choices(rarities, weights=weight_values, k=1)[0]


def _roll_slot(rng: random.Random) -> str:
    """Roll an item slot from slot weights."""
    _ensure_loaded()
    slots = list(_LOOT_TABLES["slot_weights"].keys())
    weights = list(_LOOT_TABLES["slot_weights"].values())
    return rng.choices(slots, weights=weights, k=1)[0]


def _roll_item_stats(slot: str, rarity: str, rng: random.Random) -> dict:
    """Roll base stats for an item given its slot and rarity."""
    _ensure_loaded()
    base = _LOOT_TABLES["base_stats"][slot]
    budget = _LOOT_TABLES["stat_budgets"].get(rarity, _LOOT_TABLES["stat_budgets"]["common"])

    def _roll_range(val):
        if isinstance(val, list):
            return rng.randint(val[0], val[1])
        return val

    damage = _roll_range(base["damage"])
    defense = _roll_range(base["defense"])
    weight = _roll_range(base["weight"])

    rarity_mult = {"common": 1.0, "uncommon": 1.5, "rare": 2.0, "epic": 3.0, "legendary": 4.0}
    mult = rarity_mult.get(rarity, 1.0)
    damage = int(damage * mult)
    defense = int(defense * mult)

    max_single = budget["max_single"]
    damage = min(damage, max_single)
    defense = min(defense, max_single)

    return {"damage": damage, "defense": defense, "weight": weight}


def _generate_item_name(slot: str, rarity: str, rng: random.Random) -> str:
    """Generate an item name from affixes."""
    _ensure_loaded()
    prefixes = _AFFIXES["prefixes"].get(rarity, _AFFIXES["prefixes"]["common"])
    suffixes = _AFFIXES["suffixes"].get(slot, [])

    prefix = rng.choice(prefixes)

    bases = {
        "weapon": ["Sword", "Axe", "Dagger", "Mace", "Spear", "Bow", "Staff"],
        "armor": ["Shield", "Helm", "Breastplate", "Greaves", "Chainmail"],
        "accessory": ["Amulet", "Cloak", "Belt", "Boots", "Bracers"],
        "ring": ["Ring", "Band", "Signet"],
        "consumable": ["Potion", "Elixir", "Salve", "Tonic"],
    }
    base = rng.choice(bases.get(slot, bases["weapon"]))

    name = f"{prefix} {base}"
    if rarity in ("rare", "epic", "legendary") and suffixes:
        suffix = rng.choice(suffixes)
        name = f"{name} {suffix}"

    return name


def roll_loot(
    rarity_budget: str,
    num_items: int = 3,
    seed: int | None = None,
) -> list[dict]:
    """Roll items from loot tables.

    Args:
        rarity_budget: Budget tier (common, uncommon, rare).
        num_items: Number of items to generate.
        seed: Random seed for deterministic output.

    Returns:
        List of item dicts with name, rarity, slot, damage, defense, weight.
    """
    rng = random.Random(seed)
    items: list[dict] = []

    for _ in range(num_items):
        rarity = _roll_rarity(rarity_budget, rng)
        slot = _roll_slot(rng)
        stats = _roll_item_stats(slot, rarity, rng)
        name = _generate_item_name(slot, rarity, rng)

        items.append({
            "name": name,
            "rarity": rarity,
            "slot": slot,
            **stats,
        })

    return items
