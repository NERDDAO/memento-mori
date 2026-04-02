"""Deterministic game mechanic tools — pure math, no LLM calls."""

import random
from memento.core import tool


@tool("Roll Skill Check")
def roll_skill_check(skill_level: str, difficulty: str, modifiers: str = "0") -> str:
    """Roll a skill check. Returns PASS or FAIL with the margin."""
    skill = int(skill_level)
    diff = int(difficulty)
    mods = int(modifiers)
    roll = random.randint(1, 20)
    total = roll + skill + mods
    margin = total - diff
    if margin >= 0:
        return f"PASS (rolled {roll} + skill {skill} + mods {mods} = {total} vs difficulty {diff}, margin +{margin})"
    return f"FAIL (rolled {roll} + skill {skill} + mods {mods} = {total} vs difficulty {diff}, margin {margin})"


@tool("Calculate Damage")
def calculate_damage(weapon_damage: str, attacker_strength: str, defender_armor: str) -> str:
    """Calculate final damage. Clamped to minimum 0."""
    wpn = int(weapon_damage)
    str_bonus = int(attacker_strength)
    armor = int(defender_armor)
    raw = wpn + str_bonus
    final = max(0, raw - armor)
    return f"Damage: {final} (weapon {wpn} + strength {str_bonus} = {raw}, minus armor {armor})"


@tool("Check Carry Capacity")
def check_carry_capacity(current_weight: str, max_capacity: str, item_weight: str) -> str:
    """Check if a character can carry an additional item."""
    current = int(current_weight)
    capacity = int(max_capacity)
    item = int(item_weight)
    new_total = current + item
    if new_total <= capacity:
        return f"OK — can carry. Weight: {new_total}/{capacity} (adding {item})"
    return f"Cannot carry — would exceed capacity. Weight: {new_total}/{capacity} (limit exceeded by {new_total - capacity})"


@tool("Apply Status Effect")
def apply_status_effect(effect_name: str, duration_turns: str, is_positive: str = "false") -> str:
    """Apply a status effect to a character."""
    duration = int(duration_turns)
    positive = is_positive.lower() in ("true", "yes", "1")
    kind = "buff" if positive else "debuff"
    return f"Applied {kind}: {effect_name} for {duration} turns"


@tool("Calculate XP")
def calculate_xp(current_xp: str, xp_award: str, level: str) -> str:
    """Award XP and check for level up. Threshold: level * 100."""
    xp = int(current_xp)
    award = int(xp_award)
    lvl = int(level)
    new_xp = xp + award
    threshold = lvl * 100
    if new_xp >= threshold:
        return f"XP: {new_xp}/{threshold} — LEVEL UP! New level: {lvl + 1}. Remaining XP: {new_xp - threshold}"
    return f"XP: {new_xp}/{threshold} (+{award} awarded)"


@tool("Evaluate Disposition")
def evaluate_disposition(current_friendship: str, current_trust: str, interaction_type: str) -> str:
    """Shift NPC disposition. Values clamped to [-1.0, 1.0]. Max shift: 0.05."""
    friendship = float(current_friendship)
    trust = float(current_trust)
    shifts = {
        "friendly_conversation": (0.03, 0.02),
        "hostile_action": (-0.05, -0.05),
        "gift": (0.05, 0.01),
        "betrayal": (-0.05, -0.05),
        "help_in_combat": (0.04, 0.05),
        "theft": (-0.03, -0.05),
        "trade": (0.01, 0.02),
    }
    f_shift, t_shift = shifts.get(interaction_type, (0.01, 0.01))
    new_f = max(-1.0, min(1.0, friendship + f_shift))
    new_t = max(-1.0, min(1.0, trust + t_shift))
    return (
        f"Disposition update — friendship: {friendship:.2f} -> {new_f:.2f} ({f_shift:+.2f}), "
        f"trust: {trust:.2f} -> {new_t:.2f} ({t_shift:+.2f})"
    )


@tool("Roll Loot Table")
def roll_loot_table(rarity_budget: str, num_items: str = "1") -> str:
    """Generate random loot based on rarity budget (common/uncommon/rare/epic/legendary)."""
    count = int(num_items)
    weights = {
        "common": {"common": 70, "uncommon": 25, "rare": 5},
        "uncommon": {"common": 40, "uncommon": 40, "rare": 15, "epic": 5},
        "rare": {"uncommon": 30, "rare": 40, "epic": 25, "legendary": 5},
        "epic": {"rare": 30, "epic": 45, "legendary": 25},
        "legendary": {"epic": 40, "legendary": 60},
    }
    budget_weights = weights.get(rarity_budget, weights["common"])
    rarities = list(budget_weights.keys())
    probs = list(budget_weights.values())
    results = random.choices(rarities, weights=probs, k=count)
    items = [f"  Item {i+1}: {r}" for i, r in enumerate(results)]
    return f"Loot roll ({rarity_budget} budget, {count} items):\n" + "\n".join(items)
