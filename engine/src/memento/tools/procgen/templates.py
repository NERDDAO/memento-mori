# engine/src/memento/tools/procgen/templates.py
"""Sprite mask templates for cellular automata generation."""

from dataclasses import dataclass
import numpy as np
from numpy.typing import NDArray


@dataclass
class SpriteMask:
    """A template mask for sprite generation."""
    name: str
    size: int  # output size in pixels (square)
    mask: NDArray  # 2D array: 0=empty, 1=body, 2=detail
    symmetric: bool = True  # bilateral symmetry


# --- 16px templates ---

HUMANOID_16 = SpriteMask(
    name="humanoid_16",
    size=16,
    symmetric=True,
    mask=np.array([
        [0,0,0,1,1,1,1,0],
        [0,0,1,1,1,1,1,0],
        [0,0,0,1,1,1,0,0],
        [0,0,1,1,1,1,1,0],
        [0,1,1,2,2,2,1,1],
        [0,1,1,2,2,2,1,0],
        [0,0,1,1,1,1,1,0],
        [0,0,1,1,1,1,0,0],
        [0,0,1,1,1,1,0,0],
        [0,0,1,1,1,1,0,0],
        [0,0,1,1,0,1,1,0],
        [0,0,1,1,0,1,1,0],
        [0,0,1,1,0,1,1,0],
        [0,1,1,0,0,0,1,1],
        [0,1,1,0,0,0,1,1],
        [0,1,1,0,0,0,1,1],
    ], dtype=np.int8),
)

BEAST_16 = SpriteMask(
    name="beast_16",
    size=16,
    symmetric=True,
    mask=np.array([
        [0,0,1,1,0,0,0,0],
        [0,1,1,1,1,0,0,0],
        [0,1,1,1,1,1,0,0],
        [0,0,1,2,2,1,1,0],
        [0,1,2,2,2,2,1,1],
        [1,1,2,2,2,2,1,1],
        [1,1,2,2,2,2,1,0],
        [1,1,1,1,1,1,1,0],
        [0,1,1,1,1,1,1,0],
        [0,1,1,1,1,1,0,0],
        [0,1,1,0,0,1,1,0],
        [0,1,1,0,0,1,1,0],
        [0,1,0,0,0,0,1,0],
        [0,1,0,0,0,0,1,0],
        [1,1,0,0,0,0,1,1],
        [1,1,0,0,0,0,1,1],
    ], dtype=np.int8),
)

ITEM_WEAPON_8 = SpriteMask(
    name="item_weapon_8",
    size=8,
    symmetric=True,
    mask=np.array([
        [0,0,1,1],
        [0,1,1,1],
        [0,1,2,1],
        [0,1,2,0],
        [0,1,2,0],
        [0,1,1,0],
        [1,2,1,0],
        [1,1,0,0],
    ], dtype=np.int8),
)

ITEM_POTION_8 = SpriteMask(
    name="item_potion_8",
    size=8,
    symmetric=True,
    mask=np.array([
        [0,0,1,1],
        [0,0,1,1],
        [0,1,1,1],
        [0,1,2,2],
        [1,2,2,2],
        [1,2,2,2],
        [0,1,2,2],
        [0,1,1,1],
    ], dtype=np.int8),
)

ITEM_ARMOR_8 = SpriteMask(
    name="item_armor_8",
    size=8,
    symmetric=True,
    mask=np.array([
        [0,1,1,1],
        [1,1,2,2],
        [1,2,2,2],
        [1,2,2,2],
        [1,2,2,2],
        [0,1,2,2],
        [0,1,1,1],
        [0,0,1,0],
    ], dtype=np.int8),
)

# --- 32px templates ---

HUMANOID_32 = SpriteMask(
    name="humanoid_32",
    size=32,
    symmetric=True,
    mask=np.array([
        [0,0,0,0,0,0,1,1,1,1,1,0,0,0,0,0],
        [0,0,0,0,0,1,1,1,1,1,1,0,0,0,0,0],
        [0,0,0,0,1,1,1,1,1,1,1,0,0,0,0,0],
        [0,0,0,0,1,1,1,1,1,1,1,0,0,0,0,0],
        [0,0,0,0,0,1,1,1,1,1,0,0,0,0,0,0],
        [0,0,0,0,0,0,1,1,1,0,0,0,0,0,0,0],
        [0,0,0,0,1,1,1,1,1,1,1,0,0,0,0,0],
        [0,0,0,1,1,2,2,2,2,2,1,1,0,0,0,0],
        [0,0,1,1,1,2,2,2,2,2,1,1,1,0,0,0],
        [0,1,1,1,1,2,2,2,2,2,1,1,1,1,0,0],
        [0,1,1,0,1,2,2,2,2,2,1,0,1,1,0,0],
        [0,1,1,0,1,1,2,2,2,1,1,0,1,1,0,0],
        [0,1,1,0,0,1,1,1,1,1,0,0,1,1,0,0],
        [0,0,0,0,0,1,1,1,1,1,0,0,0,0,0,0],
        [0,0,0,0,0,1,1,1,1,1,0,0,0,0,0,0],
        [0,0,0,0,1,1,1,1,1,1,0,0,0,0,0,0],
        [0,0,0,0,1,1,1,1,1,1,0,0,0,0,0,0],
        [0,0,0,0,1,1,1,1,1,1,0,0,0,0,0,0],
        [0,0,0,0,1,1,0,0,1,1,0,0,0,0,0,0],
        [0,0,0,0,1,1,0,0,1,1,0,0,0,0,0,0],
        [0,0,0,0,1,1,0,0,1,1,0,0,0,0,0,0],
        [0,0,0,0,1,1,0,0,1,1,0,0,0,0,0,0],
        [0,0,0,1,1,1,0,0,1,1,0,0,0,0,0,0],
        [0,0,0,1,1,1,0,0,1,1,1,0,0,0,0,0],
        [0,0,0,1,1,0,0,0,0,1,1,0,0,0,0,0],
        [0,0,0,1,1,0,0,0,0,1,1,0,0,0,0,0],
        [0,0,1,1,1,0,0,0,0,1,1,1,0,0,0,0],
        [0,0,1,1,1,0,0,0,0,1,1,1,0,0,0,0],
        [0,0,1,1,0,0,0,0,0,0,1,1,0,0,0,0],
        [0,0,1,1,0,0,0,0,0,0,1,1,0,0,0,0],
        [0,1,1,1,0,0,0,0,0,0,1,1,1,0,0,0],
        [0,1,1,1,0,0,0,0,0,0,1,1,1,0,0,0],
    ], dtype=np.int8),
)


# Registry: label -> template lookup
TEMPLATE_REGISTRY: dict[str, SpriteMask] = {
    "humanoid_16": HUMANOID_16,
    "humanoid_32": HUMANOID_32,
    "beast_16": BEAST_16,
    "item_weapon_8": ITEM_WEAPON_8,
    "item_potion_8": ITEM_POTION_8,
    "item_armor_8": ITEM_ARMOR_8,
}

# Entity label -> template name mapping
LABEL_TO_TEMPLATE: dict[str, str] = {
    "NPC": "humanoid_32",
    "Player": "humanoid_32",
    "Beast": "beast_16",
    "Creature": "beast_16",
    "Weapon": "item_weapon_8",
    "Potion": "item_potion_8",
    "Armor": "item_armor_8",
    "Item": "item_weapon_8",  # fallback for generic items
}


def select_template(labels: list[str], size: int | None = None) -> SpriteMask:
    """Select a sprite template based on entity labels.

    Tries labels in order, returns first match. Falls back to humanoid_16.
    If size is specified, overrides the default size for the label.
    """
    for label in labels:
        template_name = LABEL_TO_TEMPLATE.get(label)
        if template_name:
            if size and f"{label.lower()}_{size}" in TEMPLATE_REGISTRY:
                return TEMPLATE_REGISTRY[f"{label.lower()}_{size}"]
            return TEMPLATE_REGISTRY[template_name]
    return HUMANOID_16
