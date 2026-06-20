"""Pure deterministic arithmetic for the construction effect path.

No RNG. No imports beyond stdlib. No CrewAI tools.
See spec §3.5.
"""
from __future__ import annotations


def damage(weapon: int, strength: int, armor: int) -> int:
    """ATTACK damage formula. No random roll on Day 1. Pure, total, int-only.

    Returns max(0, weapon + strength - armor).
    """
    return max(0, weapon + strength - armor)


def clamp_hp(current: int, dmg: int) -> int:
    """Clamp HP after taking damage. Returns max(0, current - dmg)."""
    return max(0, current - dmg)
