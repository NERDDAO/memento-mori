# Art Department Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the blank-canvas LLM art pipeline with procgen-scaffolded crews that produce ASCII terrain and pixel sprites, integrated as entity attributes.

**Architecture:** A procgen toolkit (WFC terrain engine, cellular automata sprite generator, palette system) provides structural scaffolds to LLM crews. A Cartographer crew handles ASCII scene art for locations. A Portraitist crew handles pixel sprites for NPCs/items. A shared dispatcher (`art_gen.py`) routes art requests from NPC, item, and world gen flows via daemon threads. Art is stored as flat attributes on KG entity nodes.

**Tech Stack:** Python 3.10+, CrewAI, Pillow, NumPy, TypeScript (pretext canvas)

**Spec:** `docs/superpowers/specs/2026-04-07-art-department-design.md`

---

## File Map

### New Files (Engine)

| File | Responsibility |
|------|---------------|
| `engine/src/memento/tools/procgen/__init__.py` | Package init |
| `engine/src/memento/tools/procgen/wfc.py` | WFC terrain scaffold generator |
| `engine/src/memento/tools/procgen/sprite_gen.py` | Cellular automata pixel sprite generator |
| `engine/src/memento/tools/procgen/palette.py` | Per-biome color palette system |
| `engine/src/memento/tools/procgen/templates.py` | Sprite mask template definitions |
| `engine/src/memento/tools/sprite_validation.py` | Sprite dimension/palette validation tool |
| `engine/src/memento/crews/cartographer/crew.py` | Cartographer crew (ASCII terrain with WFC scaffold) |
| `engine/src/memento/crews/portraitist/crew.py` | Portraitist crew (pixel sprites with CA silhouettes) |
| `engine/src/memento/flows/art_gen.py` | Shared art dispatcher — routes entity type to correct crew |
| `engine/assets/atlas/palettes/dark_fantasy.json` | Default palette definitions |
| `engine/assets/atlas/tiles/` | WFC tile rule files per biome |
| `engine/assets/atlas/templates/` | Sprite mask template JSON files |
| `scripts/generate_atlas.py` | Build-time asset generation script |

### New Files (Client)

| File | Responsibility |
|------|---------------|
| `client/src/ui/sprite-renderer.ts` | Pixel sprite decoding + canvas rendering with nearest-neighbor scaling |

### New Files (Tests)

| File | Tests |
|------|-------|
| `engine/tests/tools/procgen/test_wfc.py` | WFC terrain generation with fixed seeds |
| `engine/tests/tools/procgen/test_sprite_gen.py` | Cellular automata sprite generation |
| `engine/tests/tools/procgen/test_palette.py` | Palette selection and validation |
| `engine/tests/tools/test_sprite_validation.py` | Sprite validation tool |
| `engine/tests/crews/test_cartographer.py` | Cartographer crew integration |
| `engine/tests/crews/test_portraitist.py` | Portraitist crew integration |
| `engine/tests/flows/test_art_gen.py` | Art dispatcher routing + KG persistence |

### Modified Files

| File | Change |
|------|--------|
| `engine/pyproject.toml` | Add Pillow, numpy deps |
| `engine/src/memento/flows/enrichment.py` | Route to new art dispatcher, extended `needs_art` |
| `engine/src/memento/flows/npc_gen.py` | Route art thread to new dispatcher |
| `engine/src/memento/flows/item_gen.py` | Add background art thread after balance_check |
| `engine/src/memento/flows/world_gen.py` | Add background art thread after location persistence |
| `client/src/state/game-state.ts` | Add sprite attribute fields to LocationEntity |
| `client/src/map/card-renderer.ts` | Render portrait sprite in entity cards |

---

## Task 1: Add Pillow and NumPy Dependencies

**Files:**
- Modify: `engine/pyproject.toml:10-17`

- [ ] **Step 1: Add dependencies to pyproject.toml**

In `engine/pyproject.toml`, add `Pillow` and `numpy` to the dependencies list:

```toml
dependencies = [
    "crewai[tools]",
    "bonfires",
    "pydantic>=2.0",
    "pyyaml",
    "web3",
    "requests",
    "Pillow>=10.0",
    "numpy>=1.24",
]
```

- [ ] **Step 2: Install dependencies**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && pip install -e .
```

Expected: Successfully installed Pillow and numpy (or already satisfied).

- [ ] **Step 3: Verify imports work**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -c "from PIL import Image; import numpy; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/pyproject.toml
git commit -m "feat(art): add Pillow and numpy dependencies for sprite generation"
```

---

## Task 2: Palette System

**Files:**
- Create: `engine/src/memento/tools/procgen/__init__.py`
- Create: `engine/src/memento/tools/procgen/palette.py`
- Create: `engine/assets/atlas/palettes/dark_fantasy.json`
- Test: `engine/tests/tools/procgen/test_palette.py`

- [ ] **Step 1: Create procgen package**

Create the empty package init:

```python
# engine/src/memento/tools/procgen/__init__.py
"""Procedural generation toolkit for the art department."""
```

- [ ] **Step 2: Create palette JSON**

Create directory structure and palette file:

```bash
mkdir -p /home/at0x/Vaults/Bonfires/memento-mori/engine/assets/atlas/palettes
```

```json
{
  "biomes": {
    "crypt": {
      "primary": ["#2d2d3f", "#4a4a5e", "#3a3a4d"],
      "accent": ["#8b0000", "#556b2f", "#4a0e0e"],
      "light": ["#daa520", "#cd853f", "#b8860b"],
      "wall": "#4a4a5e",
      "floor": "#2d2d3f",
      "water": "#1a1a4e"
    },
    "forest": {
      "primary": ["#1a3d1a", "#2d5a2d", "#3a6b3a"],
      "accent": ["#8b4513", "#556b2f", "#6b4423"],
      "light": ["#90ee90", "#98fb98", "#7ccd7c"],
      "wall": "#2d5a2d",
      "floor": "#1a3d1a",
      "water": "#1a4a6e"
    },
    "village": {
      "primary": ["#5a4a3a", "#6b5a4a", "#7c6b5a"],
      "accent": ["#8b4513", "#a0522d", "#cd853f"],
      "light": ["#deb887", "#d2b48c", "#f5deb3"],
      "wall": "#6b5a4a",
      "floor": "#5a4a3a",
      "water": "#4a7a9e"
    },
    "ruins": {
      "primary": ["#3a3a3a", "#4a4a4a", "#5a5a5a"],
      "accent": ["#6b8e23", "#556b2f", "#8b8b00"],
      "light": ["#b0b0b0", "#c0c0c0", "#d0d0d0"],
      "wall": "#5a5a5a",
      "floor": "#3a3a3a",
      "water": "#2a4a5a"
    },
    "default": {
      "primary": ["#2d2d3f", "#3a3a4d", "#4a4a5e"],
      "accent": ["#8b0000", "#556b2f", "#8b4513"],
      "light": ["#daa520", "#cd853f", "#b8860b"],
      "wall": "#4a4a5e",
      "floor": "#2d2d3f",
      "water": "#1a1a4e"
    }
  },
  "mood_modifiers": {
    "dark": {"brightness": -0.2},
    "eerie": {"brightness": -0.1, "saturation": -0.2},
    "peaceful": {"brightness": 0.1, "saturation": 0.1},
    "hostile": {"brightness": -0.1, "saturation": 0.2}
  }
}
```

- [ ] **Step 3: Write failing tests for palette**

```python
# engine/tests/tools/procgen/test_palette.py
"""Tests for the palette system."""
import pytest
from memento.tools.procgen.palette import (
    load_palettes,
    select_palette,
    Palette,
    hex_to_rgb,
    apply_mood,
)


def test_hex_to_rgb():
    assert hex_to_rgb("#ff0000") == (255, 0, 0)
    assert hex_to_rgb("#00ff00") == (0, 255, 0)
    assert hex_to_rgb("#2d2d3f") == (45, 45, 63)


def test_load_palettes_returns_biomes():
    palettes = load_palettes()
    assert "crypt" in palettes
    assert "forest" in palettes
    assert "default" in palettes


def test_select_palette_known_biome():
    palette = select_palette("crypt")
    assert isinstance(palette, Palette)
    assert len(palette.primary) == 3
    assert len(palette.accent) == 3
    assert palette.wall.startswith("#")
    assert palette.floor.startswith("#")


def test_select_palette_unknown_biome_falls_back():
    palette = select_palette("nonexistent_biome")
    default = select_palette("default")
    assert palette.primary == default.primary


def test_apply_mood_dark_reduces_brightness():
    base = (100, 100, 100)
    darkened = apply_mood(base, "dark")
    assert all(d < b for d, b in zip(darkened, base))


def test_apply_mood_unknown_mood_returns_unchanged():
    base = (100, 100, 100)
    result = apply_mood(base, "unknown_mood")
    assert result == base


def test_palette_random_primary():
    palette = select_palette("crypt")
    color = palette.random_primary()
    assert color in palette.primary
```

- [ ] **Step 4: Run tests to verify they fail**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/tools/procgen/test_palette.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'memento.tools.procgen.palette'`

- [ ] **Step 5: Implement palette.py**

```python
# engine/src/memento/tools/procgen/palette.py
"""Per-biome color palette system for the art department."""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

_PALETTE_FILE = Path(__file__).resolve().parents[4] / "assets" / "atlas" / "palettes" / "dark_fantasy.json"

_MOOD_MODIFIERS: dict[str, dict] = {}
_BIOME_PALETTES: dict[str, dict] = {}


def _ensure_loaded() -> None:
    if _BIOME_PALETTES:
        return
    data = json.loads(_PALETTE_FILE.read_text())
    _BIOME_PALETTES.update(data["biomes"])
    _MOOD_MODIFIERS.update(data["mood_modifiers"])


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert '#rrggbb' to (r, g, b) tuple."""
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert (r, g, b) to '#rrggbb'."""
    return f"#{r:02x}{g:02x}{b:02x}"


def apply_mood(rgb: tuple[int, int, int], mood: str) -> tuple[int, int, int]:
    """Apply mood brightness/saturation modifier to an RGB color."""
    _ensure_loaded()
    mod = _MOOD_MODIFIERS.get(mood)
    if not mod:
        return rgb
    r, g, b = rgb
    brightness = mod.get("brightness", 0.0)
    r = max(0, min(255, int(r + brightness * 255)))
    g = max(0, min(255, int(g + brightness * 255)))
    b = max(0, min(255, int(b + brightness * 255)))
    return (r, g, b)


@dataclass
class Palette:
    """A resolved color palette for a specific biome."""
    primary: list[str]
    accent: list[str]
    light: list[str]
    wall: str
    floor: str
    water: str

    def random_primary(self) -> str:
        return random.choice(self.primary)

    def random_accent(self) -> str:
        return random.choice(self.accent)

    def random_light(self) -> str:
        return random.choice(self.light)


def load_palettes() -> dict[str, dict]:
    """Load and return raw biome palette data."""
    _ensure_loaded()
    return dict(_BIOME_PALETTES)


def select_palette(biome: str, mood: str = "") -> Palette:
    """Select a palette for the given biome, with optional mood adjustment."""
    _ensure_loaded()
    data = _BIOME_PALETTES.get(biome, _BIOME_PALETTES["default"])
    primary = list(data["primary"])
    accent = list(data["accent"])
    light = list(data["light"])

    if mood:
        primary = [rgb_to_hex(*apply_mood(hex_to_rgb(c), mood)) for c in primary]
        accent = [rgb_to_hex(*apply_mood(hex_to_rgb(c), mood)) for c in accent]
        light = [rgb_to_hex(*apply_mood(hex_to_rgb(c), mood)) for c in light]

    return Palette(
        primary=primary,
        accent=accent,
        light=light,
        wall=data["wall"],
        floor=data["floor"],
        water=data["water"],
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/tools/procgen/test_palette.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 7: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/tools/procgen/__init__.py engine/src/memento/tools/procgen/palette.py engine/assets/atlas/palettes/dark_fantasy.json engine/tests/tools/procgen/test_palette.py
git commit -m "feat(art): add palette system with per-biome colors and mood modifiers"
```

---

## Task 3: Sprite Template Masks

**Files:**
- Create: `engine/src/memento/tools/procgen/templates.py`
- Test: `engine/tests/tools/procgen/test_templates.py` (included in sprite_gen tests in Task 4)

- [ ] **Step 1: Write templates module**

Template masks are 2D arrays where 0=empty, 1=body, 2=detail region. Bilateral symmetry is applied at generation time, so masks only define the left half + center.

```python
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


# Registry: label → template lookup
TEMPLATE_REGISTRY: dict[str, SpriteMask] = {
    "humanoid_16": HUMANOID_16,
    "humanoid_32": HUMANOID_32,
    "beast_16": BEAST_16,
    "item_weapon_8": ITEM_WEAPON_8,
    "item_potion_8": ITEM_POTION_8,
    "item_armor_8": ITEM_ARMOR_8,
}

# Entity label → template name mapping
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
```

- [ ] **Step 2: Run a quick import check**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -c "from memento.tools.procgen.templates import select_template, HUMANOID_16; print(f'Mask shape: {HUMANOID_16.mask.shape}, size: {HUMANOID_16.size}')"
```

Expected: `Mask shape: (16, 8), size: 16`

- [ ] **Step 3: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/tools/procgen/templates.py
git commit -m "feat(art): add sprite mask templates for humanoid, beast, and item types"
```

---

## Task 4: Cellular Automata Sprite Generator

**Files:**
- Create: `engine/src/memento/tools/procgen/sprite_gen.py`
- Test: `engine/tests/tools/procgen/test_sprite_gen.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/tools/procgen/test_sprite_gen.py
"""Tests for cellular automata sprite generation."""
import base64
import pytest
from PIL import Image
import io

from memento.tools.procgen.sprite_gen import generate_sprite
from memento.tools.procgen.templates import HUMANOID_16, BEAST_16, ITEM_WEAPON_8, HUMANOID_32
from memento.tools.procgen.palette import select_palette


@pytest.fixture
def palette():
    return select_palette("crypt")


def test_generate_sprite_returns_base64_png(palette):
    result = generate_sprite(HUMANOID_16, palette, seed=42)
    assert result.startswith("iVBOR") or result.startswith("/9j/")  # PNG or JPEG b64 header
    # Decode and verify it's a valid image
    img_bytes = base64.b64decode(result)
    img = Image.open(io.BytesIO(img_bytes))
    assert img.format == "PNG"


def test_generate_sprite_16x16_dimensions(palette):
    result = generate_sprite(HUMANOID_16, palette, seed=42)
    img_bytes = base64.b64decode(result)
    img = Image.open(io.BytesIO(img_bytes))
    assert img.size == (16, 16)


def test_generate_sprite_32x32_dimensions(palette):
    result = generate_sprite(HUMANOID_32, palette, seed=42)
    img_bytes = base64.b64decode(result)
    img = Image.open(io.BytesIO(img_bytes))
    assert img.size == (32, 32)


def test_generate_sprite_8x8_item(palette):
    result = generate_sprite(ITEM_WEAPON_8, palette, seed=42)
    img_bytes = base64.b64decode(result)
    img = Image.open(io.BytesIO(img_bytes))
    assert img.size == (8, 8)


def test_generate_sprite_has_transparency(palette):
    result = generate_sprite(HUMANOID_16, palette, seed=42)
    img_bytes = base64.b64decode(result)
    img = Image.open(io.BytesIO(img_bytes))
    assert img.mode == "RGBA"
    # Check that at least some pixels are transparent (mask=0 regions)
    pixels = list(img.getdata())
    transparent = [p for p in pixels if p[3] == 0]
    assert len(transparent) > 0


def test_generate_sprite_deterministic_with_seed(palette):
    result1 = generate_sprite(HUMANOID_16, palette, seed=42)
    result2 = generate_sprite(HUMANOID_16, palette, seed=42)
    assert result1 == result2


def test_generate_sprite_different_seeds_differ(palette):
    result1 = generate_sprite(HUMANOID_16, palette, seed=42)
    result2 = generate_sprite(HUMANOID_16, palette, seed=99)
    assert result1 != result2


def test_generate_sprite_bilateral_symmetry(palette):
    result = generate_sprite(HUMANOID_16, palette, seed=42)
    img_bytes = base64.b64decode(result)
    img = Image.open(io.BytesIO(img_bytes))
    pixels = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w // 2):
            left = pixels[x, y]
            right = pixels[w - 1 - x, y]
            assert left == right, f"Asymmetry at ({x},{y}): {left} != {right}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/tools/procgen/test_sprite_gen.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'memento.tools.procgen.sprite_gen'`

- [ ] **Step 3: Implement sprite_gen.py**

```python
# engine/src/memento/tools/procgen/sprite_gen.py
"""Cellular automata sprite generator.

Generates pixel sprite silhouettes from template masks using randomized
cellular automata with bilateral symmetry. Based on the approach from
soulfir/sprite-generator (cellular automata + mirror symmetry).
"""

import base64
import io
import random

import numpy as np
from PIL import Image

from memento.tools.procgen.palette import Palette, hex_to_rgb
from memento.tools.procgen.templates import SpriteMask


def _apply_ca_noise(mask: np.ndarray, rng: random.Random) -> np.ndarray:
    """Apply cellular automata-style noise to body regions.

    For each cell in the mask that is body (1) or detail (2), randomly
    decide whether to fill or leave empty based on neighboring cells.
    This creates organic-looking silhouettes.
    """
    h, w = mask.shape
    result = np.zeros_like(mask)

    for y in range(h):
        for x in range(w):
            if mask[y, x] == 0:
                continue
            # Body cells: ~70% fill chance, detail cells: ~50% fill chance
            threshold = 0.7 if mask[y, x] == 1 else 0.5
            if rng.random() < threshold:
                result[y, x] = mask[y, x]

    # One CA smoothing pass: fill isolated holes, remove isolated pixels
    smoothed = result.copy()
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            neighbors = int(result[y-1, x] > 0) + int(result[y+1, x] > 0) + \
                        int(result[y, x-1] > 0) + int(result[y, x+1] > 0)
            if result[y, x] == 0 and mask[y, x] > 0 and neighbors >= 3:
                smoothed[y, x] = mask[y, x]  # fill hole
            elif result[y, x] > 0 and neighbors <= 1:
                smoothed[y, x] = 0  # remove isolated

    return smoothed


def _colorize(
    filled: np.ndarray,
    mask: np.ndarray,
    palette: Palette,
    rng: random.Random,
) -> np.ndarray:
    """Convert a filled mask into an RGBA pixel array.

    Body regions (1) get primary colors, detail regions (2) get accent colors.
    Edges get slightly darker shading for depth.
    """
    h, w = filled.shape
    pixels = np.zeros((h, w, 4), dtype=np.uint8)

    # Pick base colors for this sprite
    body_rgb = hex_to_rgb(rng.choice(palette.primary))
    detail_rgb = hex_to_rgb(rng.choice(palette.accent))
    highlight_rgb = hex_to_rgb(rng.choice(palette.light))

    for y in range(h):
        for x in range(w):
            if filled[y, x] == 0:
                continue  # transparent

            # Choose base color
            if filled[y, x] == 2:
                base = detail_rgb
            else:
                base = body_rgb

            # Edge darkening: if adjacent to empty, darken by 20%
            is_edge = False
            for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                ny, nx = y + dy, x + dx
                if ny < 0 or ny >= h or nx < 0 or nx >= w or filled[ny, nx] == 0:
                    is_edge = True
                    break

            if is_edge:
                r = max(0, int(base[0] * 0.7))
                g = max(0, int(base[1] * 0.7))
                b = max(0, int(base[2] * 0.7))
            else:
                # Occasional highlight pixel
                if rng.random() < 0.1:
                    r, g, b = highlight_rgb
                else:
                    r, g, b = base

            pixels[y, x] = [r, g, b, 255]

    return pixels


def generate_sprite(
    template: SpriteMask,
    palette: Palette,
    seed: int | None = None,
) -> str:
    """Generate a pixel sprite from a template mask.

    Args:
        template: Sprite mask defining body regions.
        palette: Color palette for the sprite.
        seed: Random seed for deterministic output.

    Returns:
        Base64-encoded PNG string.
    """
    rng = random.Random(seed)

    # Apply CA noise to the half-mask
    filled_half = _apply_ca_noise(template.mask, rng)

    # Mirror for bilateral symmetry
    if template.symmetric:
        half_w = filled_half.shape[1]
        full_w = template.size
        # Left half = filled_half, right half = flipped
        full = np.zeros((template.size, full_w), dtype=np.int8)
        # Place left half
        full[:filled_half.shape[0], :half_w] = filled_half
        # Mirror to right half
        for y in range(filled_half.shape[0]):
            for x in range(half_w):
                mirror_x = full_w - 1 - x
                full[y, mirror_x] = filled_half[y, x]
    else:
        full = filled_half

    # Also mirror the original mask for colorization reference
    if template.symmetric:
        full_mask = np.zeros((template.size, template.size), dtype=np.int8)
        full_mask[:template.mask.shape[0], :template.mask.shape[1]] = template.mask
        for y in range(template.mask.shape[0]):
            for x in range(template.mask.shape[1]):
                mirror_x = template.size - 1 - x
                full_mask[y, mirror_x] = template.mask[y, x]
    else:
        full_mask = template.mask

    # Colorize
    pixels = _colorize(full, full_mask, palette, rng)

    # Convert to PIL Image
    img = Image.fromarray(pixels, mode="RGBA")

    # Encode to base64 PNG
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/tools/procgen/test_sprite_gen.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/tools/procgen/sprite_gen.py engine/tests/tools/procgen/test_sprite_gen.py
git commit -m "feat(art): add cellular automata sprite generator with bilateral symmetry"
```

---

## Task 5: WFC Terrain Scaffold Generator

**Files:**
- Create: `engine/src/memento/tools/procgen/wfc.py`
- Create: `engine/assets/atlas/tiles/crypt.json`
- Create: `engine/assets/atlas/tiles/forest.json`
- Create: `engine/assets/atlas/tiles/village.json`
- Create: `engine/assets/atlas/tiles/default.json`
- Test: `engine/tests/tools/procgen/test_wfc.py`

- [ ] **Step 1: Create tile rule files**

```bash
mkdir -p /home/at0x/Vaults/Bonfires/memento-mori/engine/assets/atlas/tiles
```

Each tile ruleset defines tiles and which tiles can be adjacent to each other (up/down/left/right).

```json
// engine/assets/atlas/tiles/default.json
{
  "tiles": {
    "#": {"name": "wall", "weight": 3},
    ".": {"name": "floor", "weight": 5},
    " ": {"name": "empty", "weight": 2},
    "~": {"name": "water", "weight": 1},
    ":": {"name": "path", "weight": 2},
    "+": {"name": "door", "weight": 0.5}
  },
  "adjacency": {
    "#": {"right": ["#", ".", "+"], "down": ["#", ".", "+"], "left": ["#", ".", "+"], "up": ["#", ".", "+"]},
    ".": {"right": [".", "#", ":", "+", " "], "down": [".", "#", ":", "+", " "], "left": [".", "#", ":", "+", " "], "up": [".", "#", ":", "+", " "]},
    " ": {"right": [" ", ".", "#"], "down": [" ", ".", "#"], "left": [" ", ".", "#"], "up": [" ", ".", "#"]},
    "~": {"right": ["~", "."], "down": ["~", "."], "left": ["~", "."], "up": ["~", "."]},
    ":": {"right": [":", "."], "down": [":", "."], "left": [":", "."], "up": [":", "."]},
    "+": {"right": [".", "#"], "down": [".", "#"], "left": [".", "#"], "up": [".", "#"]}
  },
  "border": "#"
}
```

```json
// engine/assets/atlas/tiles/crypt.json
{
  "tiles": {
    "#": {"name": "stone_wall", "weight": 4},
    ".": {"name": "stone_floor", "weight": 5},
    " ": {"name": "darkness", "weight": 1},
    "~": {"name": "stagnant_water", "weight": 1},
    ":": {"name": "rubble_path", "weight": 2},
    "+": {"name": "iron_door", "weight": 0.3},
    "▓": {"name": "crumbling_wall", "weight": 1}
  },
  "adjacency": {
    "#": {"right": ["#", ".", "+", "▓"], "down": ["#", ".", "+", "▓"], "left": ["#", ".", "+", "▓"], "up": ["#", ".", "+", "▓"]},
    ".": {"right": [".", "#", ":", "+", " ", "▓"], "down": [".", "#", ":", "+", " "], "left": [".", "#", ":", "+", " ", "▓"], "up": [".", "#", ":", "+", " "]},
    " ": {"right": [" ", "."], "down": [" ", "."], "left": [" ", "."], "up": [" ", "."]},
    "~": {"right": ["~", "."], "down": ["~", "."], "left": ["~", "."], "up": ["~", "."]},
    ":": {"right": [":", "."], "down": [":", "."], "left": [":", "."], "up": [":", "."]},
    "+": {"right": [".", "#"], "down": [".", "#"], "left": [".", "#"], "up": [".", "#"]},
    "▓": {"right": ["▓", "#", "."], "down": ["▓", "#", "."], "left": ["▓", "#", "."], "up": ["▓", "#", "."]}
  },
  "border": "#"
}
```

```json
// engine/assets/atlas/tiles/forest.json
{
  "tiles": {
    "T": {"name": "tree", "weight": 3},
    ".": {"name": "grass", "weight": 5},
    " ": {"name": "clearing", "weight": 2},
    "~": {"name": "stream", "weight": 1},
    ":": {"name": "trail", "weight": 2},
    "^": {"name": "bush", "weight": 2}
  },
  "adjacency": {
    "T": {"right": ["T", ".", "^"], "down": ["T", ".", "^"], "left": ["T", ".", "^"], "up": ["T", ".", "^"]},
    ".": {"right": [".", "T", ":", " ", "~", "^"], "down": [".", "T", ":", " ", "~", "^"], "left": [".", "T", ":", " ", "~", "^"], "up": [".", "T", ":", " ", "~", "^"]},
    " ": {"right": [" ", ".", "T"], "down": [" ", ".", "T"], "left": [" ", ".", "T"], "up": [" ", ".", "T"]},
    "~": {"right": ["~", "."], "down": ["~", "."], "left": ["~", "."], "up": ["~", "."]},
    ":": {"right": [":", "."], "down": [":", "."], "left": [":", "."], "up": [":", "."]},
    "^": {"right": ["^", ".", "T"], "down": ["^", ".", "T"], "left": ["^", ".", "T"], "up": ["^", ".", "T"]}
  },
  "border": "T"
}
```

```json
// engine/assets/atlas/tiles/village.json
{
  "tiles": {
    "#": {"name": "building_wall", "weight": 3},
    ".": {"name": "cobblestone", "weight": 5},
    " ": {"name": "open_ground", "weight": 2},
    ":": {"name": "road", "weight": 3},
    "+": {"name": "wooden_door", "weight": 0.5},
    "=": {"name": "fence", "weight": 1}
  },
  "adjacency": {
    "#": {"right": ["#", ".", "+"], "down": ["#", ".", "+"], "left": ["#", ".", "+"], "up": ["#", ".", "+"]},
    ".": {"right": [".", "#", ":", "+", " ", "="], "down": [".", "#", ":", "+", " ", "="], "left": [".", "#", ":", "+", " ", "="], "up": [".", "#", ":", "+", " ", "="]},
    " ": {"right": [" ", ".", "="], "down": [" ", ".", "="], "left": [" ", ".", "="], "up": [" ", ".", "="]},
    ":": {"right": [":", ".", "#"], "down": [":", ".", "#"], "left": [":", ".", "#"], "up": [":", ".", "#"]},
    "+": {"right": [".", "#"], "down": [".", "#"], "left": [".", "#"], "up": [".", "#"]},
    "=": {"right": ["=", ".", " "], "down": ["=", ".", " "], "left": ["=", ".", " "], "up": ["=", ".", " "]}
  },
  "border": "="
}
```

- [ ] **Step 2: Write failing tests**

```python
# engine/tests/tools/procgen/test_wfc.py
"""Tests for WFC terrain scaffold generation."""
import pytest
from memento.tools.procgen.wfc import generate_terrain_scaffold, load_tileset


def test_load_tileset_default():
    tileset = load_tileset("default")
    assert "#" in tileset.tiles
    assert "." in tileset.tiles
    assert tileset.border == "#"


def test_load_tileset_crypt():
    tileset = load_tileset("crypt")
    assert "▓" in tileset.tiles


def test_load_tileset_unknown_falls_back():
    tileset = load_tileset("nonexistent")
    default = load_tileset("default")
    assert tileset.tiles.keys() == default.tiles.keys()


def test_scaffold_correct_dimensions():
    result = generate_terrain_scaffold("default", width=35, height=20, seed=42)
    lines = result.strip().split("\n")
    assert len(lines) == 20
    for line in lines:
        assert len(line) == 35, f"Line width {len(line)} != 35: '{line}'"


def test_scaffold_has_border():
    result = generate_terrain_scaffold("default", width=35, height=20, seed=42)
    lines = result.strip().split("\n")
    # Top and bottom rows should be all wall (border char)
    assert all(c == "#" for c in lines[0])
    assert all(c == "#" for c in lines[-1])
    # Left and right columns should be wall
    for line in lines:
        assert line[0] == "#"
        assert line[-1] == "#"


def test_scaffold_deterministic_with_seed():
    r1 = generate_terrain_scaffold("default", width=20, height=10, seed=42)
    r2 = generate_terrain_scaffold("default", width=20, height=10, seed=42)
    assert r1 == r2


def test_scaffold_different_seeds_differ():
    r1 = generate_terrain_scaffold("default", width=20, height=10, seed=42)
    r2 = generate_terrain_scaffold("default", width=20, height=10, seed=99)
    assert r1 != r2


def test_scaffold_only_uses_tileset_chars():
    tileset = load_tileset("crypt")
    result = generate_terrain_scaffold("crypt", width=20, height=10, seed=42)
    valid_chars = set(tileset.tiles.keys())
    for line in result.strip().split("\n"):
        for ch in line:
            assert ch in valid_chars, f"Invalid char '{ch}' not in tileset"


def test_scaffold_small_grid():
    """Even a small 10x5 grid should work."""
    result = generate_terrain_scaffold("default", width=10, height=5, seed=42)
    lines = result.strip().split("\n")
    assert len(lines) == 5
    assert all(len(l) == 10 for l in lines)
```

- [ ] **Step 3: Run tests to verify they fail**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/tools/procgen/test_wfc.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'memento.tools.procgen.wfc'`

- [ ] **Step 4: Implement wfc.py**

```python
# engine/src/memento/tools/procgen/wfc.py
"""Wave Function Collapse terrain scaffold generator.

Generates structural ASCII grids from tile adjacency rules. The output is
a scaffold — wall/floor/door positions that an LLM artist can then detail
with atmospheric content while preserving the structure.
"""

import json
import random
from dataclasses import dataclass
from pathlib import Path

_TILES_DIR = Path(__file__).resolve().parents[4] / "assets" / "atlas" / "tiles"


@dataclass
class TileInfo:
    name: str
    weight: float


@dataclass
class Tileset:
    tiles: dict[str, TileInfo]
    adjacency: dict[str, dict[str, list[str]]]
    border: str


def load_tileset(biome: str) -> Tileset:
    """Load a tileset from JSON. Falls back to default if biome not found."""
    path = _TILES_DIR / f"{biome}.json"
    if not path.exists():
        path = _TILES_DIR / "default.json"
    data = json.loads(path.read_text())
    tiles = {ch: TileInfo(**info) for ch, info in data["tiles"].items()}
    return Tileset(
        tiles=tiles,
        adjacency=data["adjacency"],
        border=data["border"],
    )


def _collapse_cell(
    possible: set[str],
    tileset: Tileset,
    rng: random.Random,
) -> str:
    """Collapse a cell by choosing from possible tiles weighted by tile weight."""
    if not possible:
        return tileset.border  # fallback if contradiction
    candidates = list(possible)
    weights = [tileset.tiles[c].weight for c in candidates]
    return rng.choices(candidates, weights=weights, k=1)[0]


def generate_terrain_scaffold(
    biome: str,
    width: int = 35,
    height: int = 20,
    seed: int | None = None,
) -> str:
    """Generate an ASCII terrain scaffold using WFC.

    Args:
        biome: Biome name for tileset selection.
        width: Grid width in characters.
        height: Grid height in characters.
        seed: Random seed for deterministic output.

    Returns:
        Multi-line string of ASCII terrain, exactly height lines each width chars.
    """
    rng = random.Random(seed)
    tileset = load_tileset(biome)
    all_tiles = set(tileset.tiles.keys())

    # Initialize grid: each cell has a set of possible tiles
    grid: list[list[str | None]] = [[None] * width for _ in range(height)]

    # Fix border cells
    for x in range(width):
        grid[0][x] = tileset.border
        grid[height - 1][x] = tileset.border
    for y in range(height):
        grid[y][0] = tileset.border
        grid[y][width - 1] = tileset.border

    # Possibilities for interior cells
    possible: list[list[set[str] | None]] = [[None] * width for _ in range(height)]
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            possible[y][x] = set(all_tiles)

    # Propagate constraints from borders
    def propagate(y: int, x: int) -> None:
        """Propagate constraints from a collapsed cell to neighbors."""
        ch = grid[y][x]
        if ch is None:
            return
        adj = tileset.adjacency.get(ch, {})
        for dy, dx, direction in [
            (-1, 0, "up"), (1, 0, "down"), (0, -1, "left"), (0, 1, "right")
        ]:
            ny, nx = y + dy, x + dx
            if 0 <= ny < height and 0 <= nx < width and possible[ny][nx] is not None:
                allowed = set(adj.get(direction, []))
                possible[ny][nx] &= allowed

    # Propagate from all border cells
    for x in range(width):
        propagate(0, x)
        propagate(height - 1, x)
    for y in range(height):
        propagate(y, 0)
        propagate(y, width - 1)

    # WFC collapse loop: pick lowest-entropy cell, collapse, propagate
    max_iterations = width * height * 2  # safety limit
    for _ in range(max_iterations):
        # Find uncollapsed cell with lowest entropy
        min_entropy = float("inf")
        candidates = []
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                if grid[y][x] is not None:
                    continue
                p = possible[y][x]
                if p is None:
                    continue
                entropy = len(p)
                if entropy < min_entropy:
                    min_entropy = entropy
                    candidates = [(y, x)]
                elif entropy == min_entropy:
                    candidates.append((y, x))

        if not candidates:
            break  # all collapsed

        # Pick random among lowest-entropy cells
        cy, cx = rng.choice(candidates)
        grid[cy][cx] = _collapse_cell(possible[cy][cx], tileset, rng)
        possible[cy][cx] = None
        propagate(cy, cx)

    # Fill any remaining uncollapsed cells (contradiction fallback)
    for y in range(height):
        for x in range(width):
            if grid[y][x] is None:
                if possible[y][x]:
                    grid[y][x] = _collapse_cell(possible[y][x], tileset, rng)
                else:
                    grid[y][x] = "."  # safe fallback

    # Build output string
    lines = ["".join(row) for row in grid]
    return "\n".join(lines)
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/tools/procgen/test_wfc.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/tools/procgen/wfc.py engine/assets/atlas/tiles/ engine/tests/tools/procgen/test_wfc.py
git commit -m "feat(art): add WFC terrain scaffold generator with biome tilesets"
```

---

## Task 6: Sprite Validation Tool

**Files:**
- Create: `engine/src/memento/tools/sprite_validation.py`
- Test: `engine/tests/tools/test_sprite_validation.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/tools/test_sprite_validation.py
"""Tests for sprite validation tool."""
import base64
import io
import pytest
from PIL import Image

from memento.tools.sprite_validation import validate_sprite


def _make_sprite(w: int, h: int, mode: str = "RGBA") -> str:
    """Create a valid test sprite as base64."""
    img = Image.new(mode, (w, h), (100, 50, 50, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_valid_sprite_passes():
    sprite = _make_sprite(16, 16)
    result = validate_sprite.run(sprite_b64=sprite, expected_w=16, expected_h=16)
    assert result == "PASS"


def test_wrong_width_fails():
    sprite = _make_sprite(32, 16)
    result = validate_sprite.run(sprite_b64=sprite, expected_w=16, expected_h=16)
    assert "FAIL" in result
    assert "width" in result.lower()


def test_wrong_height_fails():
    sprite = _make_sprite(16, 32)
    result = validate_sprite.run(sprite_b64=sprite, expected_w=16, expected_h=16)
    assert "FAIL" in result
    assert "height" in result.lower()


def test_invalid_base64_fails():
    result = validate_sprite.run(sprite_b64="not_valid_base64!!!", expected_w=16, expected_h=16)
    assert "FAIL" in result


def test_rgb_mode_still_passes():
    sprite = _make_sprite(8, 8, mode="RGB")
    result = validate_sprite.run(sprite_b64=sprite, expected_w=8, expected_h=8)
    assert result == "PASS"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/tools/test_sprite_validation.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'memento.tools.sprite_validation'`

- [ ] **Step 3: Implement sprite_validation.py**

```python
# engine/src/memento/tools/sprite_validation.py
"""Sprite validation tool for CrewAI agents."""

import base64
import io

from crewai.tools import tool
from PIL import Image


@tool("validate_sprite")
def validate_sprite(sprite_b64: str, expected_w: int, expected_h: int) -> str:
    """Validate a base64-encoded PNG sprite's dimensions.

    Args:
        sprite_b64: Base64-encoded PNG image data.
        expected_w: Expected width in pixels.
        expected_h: Expected height in pixels.

    Returns:
        'PASS' or 'FAIL: [specific errors]'
    """
    errors: list[str] = []

    try:
        img_bytes = base64.b64decode(sprite_b64)
        img = Image.open(io.BytesIO(img_bytes))
    except Exception as e:
        return f"FAIL: Could not decode sprite: {e}"

    w, h = img.size
    if w != expected_w:
        errors.append(f"Width mismatch: got {w}, expected {expected_w}")
    if h != expected_h:
        errors.append(f"Height mismatch: got {h}, expected {expected_h}")

    if errors:
        return "FAIL: " + "; ".join(errors)
    return "PASS"
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/tools/test_sprite_validation.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/tools/sprite_validation.py engine/tests/tools/test_sprite_validation.py
git commit -m "feat(art): add sprite validation tool for dimension checks"
```

---

## Task 7: CrewAI Procgen Tools (Crew-Accessible Wrappers)

**Files:**
- Create: `engine/src/memento/tools/art_tools.py`
- Test: `engine/tests/tools/test_art_tools.py`

These wrap the procgen functions as CrewAI `@tool` decorated functions so agents can call them.

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/tools/test_art_tools.py
"""Tests for CrewAI-accessible art tools."""
import json
import pytest

from memento.tools.art_tools import (
    generate_terrain_tool,
    generate_sprite_tool,
    select_palette_tool,
)


def test_generate_terrain_tool_returns_ascii():
    result = generate_terrain_tool.run(biome="default", width=20, height=10, seed=42)
    lines = result.strip().split("\n")
    assert len(lines) == 10
    assert all(len(l) == 20 for l in lines)


def test_generate_sprite_tool_returns_base64():
    result = generate_sprite_tool.run(
        entity_labels='["NPC"]', biome="crypt", seed=42
    )
    parsed = json.loads(result)
    assert "sprite_b64" in parsed
    assert "width" in parsed
    assert "height" in parsed
    assert parsed["width"] in (16, 32)


def test_select_palette_tool_returns_colors():
    result = select_palette_tool.run(biome="forest", mood="dark")
    parsed = json.loads(result)
    assert "primary" in parsed
    assert "accent" in parsed
    assert len(parsed["primary"]) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/tools/test_art_tools.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'memento.tools.art_tools'`

- [ ] **Step 3: Implement art_tools.py**

```python
# engine/src/memento/tools/art_tools.py
"""CrewAI-accessible art generation tools.

These wrap the procgen toolkit as @tool functions that crew agents can invoke.
"""

import json

from crewai.tools import tool

from memento.tools.procgen.wfc import generate_terrain_scaffold
from memento.tools.procgen.sprite_gen import generate_sprite
from memento.tools.procgen.palette import select_palette as _select_palette
from memento.tools.procgen.templates import select_template


@tool("generate_terrain")
def generate_terrain_tool(biome: str, width: int = 35, height: int = 20, seed: int = 0) -> str:
    """Generate an ASCII terrain scaffold using Wave Function Collapse.

    Args:
        biome: Biome name (crypt, forest, village, ruins, default).
        width: Grid width in characters.
        height: Grid height in characters.
        seed: Random seed (0 for random).

    Returns:
        Multi-line ASCII string of the terrain scaffold.
    """
    actual_seed = seed if seed != 0 else None
    return generate_terrain_scaffold(biome, width=width, height=height, seed=actual_seed)


@tool("generate_sprite")
def generate_sprite_tool(entity_labels: str, biome: str = "default", seed: int = 0) -> str:
    """Generate a pixel sprite silhouette for an entity.

    Args:
        entity_labels: JSON array of entity labels, e.g. '["NPC"]' or '["Weapon", "Item"]'.
        biome: Biome name for palette selection.
        seed: Random seed (0 for random).

    Returns:
        JSON with sprite_b64, width, height.
    """
    labels = json.loads(entity_labels)
    template = select_template(labels)
    palette = _select_palette(biome)
    actual_seed = seed if seed != 0 else None
    sprite_b64 = generate_sprite(template, palette, seed=actual_seed)
    return json.dumps({
        "sprite_b64": sprite_b64,
        "width": template.size,
        "height": template.size,
        "template": template.name,
    })


@tool("select_palette")
def select_palette_tool(biome: str, mood: str = "") -> str:
    """Get the color palette for a biome/mood combination.

    Args:
        biome: Biome name (crypt, forest, village, ruins, default).
        mood: Optional mood modifier (dark, eerie, peaceful, hostile).

    Returns:
        JSON with primary, accent, light color arrays and wall/floor/water colors.
    """
    palette = _select_palette(biome, mood)
    return json.dumps({
        "primary": palette.primary,
        "accent": palette.accent,
        "light": palette.light,
        "wall": palette.wall,
        "floor": palette.floor,
        "water": palette.water,
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/tools/test_art_tools.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/tools/art_tools.py engine/tests/tools/test_art_tools.py
git commit -m "feat(art): add CrewAI tool wrappers for procgen toolkit"
```

---

## Task 8: Cartographer Crew

**Files:**
- Create: `engine/src/memento/crews/cartographer/__init__.py`
- Create: `engine/src/memento/crews/cartographer/crew.py`
- Test: `engine/tests/crews/test_cartographer.py`

- [ ] **Step 1: Write failing test**

```python
# engine/tests/crews/test_cartographer.py
"""Tests for the Cartographer crew."""
import pytest
from unittest.mock import patch, MagicMock

from memento.crews.cartographer.crew import make_cartographer_crew


def test_make_cartographer_crew_returns_crew():
    crew = make_cartographer_crew(
        location_name="Ruined Chapel",
        description="A crumbling stone chapel overtaken by dark vines.",
        mood="eerie",
        biome="ruins",
        width=35,
        height=20,
    )
    assert crew is not None
    assert len(crew.agents) == 2  # artist + critic
    assert len(crew.tasks) >= 3  # scaffold → detail → critique → (optional revise)


def test_cartographer_crew_artist_has_scaffold_tool():
    crew = make_cartographer_crew(
        location_name="Dark Forest",
        description="Ancient trees block all light.",
        mood="dark",
        biome="forest",
    )
    artist = crew.agents[0]
    tool_names = [t.name for t in artist.tools]
    assert "generate_terrain" in tool_names
    assert "validate_art" in tool_names


def test_cartographer_crew_uses_biome_in_scaffold_task():
    crew = make_cartographer_crew(
        location_name="Village Square",
        description="A busy market square.",
        mood="peaceful",
        biome="village",
    )
    scaffold_task = crew.tasks[0]
    assert "village" in scaffold_task.description.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/crews/test_cartographer.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'memento.crews.cartographer'`

- [ ] **Step 3: Create package init**

```python
# engine/src/memento/crews/cartographer/__init__.py
```

- [ ] **Step 4: Implement cartographer crew**

```python
# engine/src/memento/crews/cartographer/crew.py
"""Cartographer crew — WFC-scaffolded ASCII terrain art for locations."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.art_validation import validate_art
from memento.tools.art_tools import generate_terrain_tool


def make_cartographer_crew(
    location_name: str,
    description: str,
    mood: str,
    biome: str = "default",
    width: int = 35,
    height: int = 20,
) -> Crew:
    """Build a crew that generates ASCII terrain art from a WFC scaffold.

    The terrain artist receives a procgen scaffold and adds atmospheric
    detail while preserving structural elements. The critic validates
    the result.
    """
    model = get_model_for_crew("ascii_art")

    artist = Agent(
        role="Terrain Artist",
        goal="Add atmospheric detail to ASCII terrain scaffolds for a dark fantasy MUD",
        backstory=(
            f"You receive a {width}x{height} ASCII terrain scaffold generated by a "
            f"Wave Function Collapse algorithm. The scaffold has structural elements "
            f"(walls, floors, doors, water, paths) already placed.\n\n"
            f"YOUR JOB: Add atmospheric detail WITHIN the existing structure.\n\n"
            f"RULES:\n"
            f"- PRESERVE all wall (#/█/▓) and door (+) positions — do not move or remove them\n"
            f"- DETAIL floor (.) and empty ( ) regions with mood-appropriate characters\n"
            f"- Add narrative elements: furniture, debris, vegetation, light sources\n"
            f"- Final output must be exactly {height} lines, each exactly {width} characters\n"
            f"- Use the generate_terrain tool with biome='{biome}' to get the scaffold first\n\n"
            f"CHARACTER PALETTE:\n"
            f"- Standard ASCII: # . : | / \\ - _ ~ ^ * @ ' \" and spaces\n"
            f"- Box-drawing: ═ ║ ╔ ╗ ╚ ╝ ╦ ╩ ╠ ╣ ╬ ─ │ ┌ ┐ └ ┘\n"
            f"- Block elements: ░ ▒ ▓ █ ▄ ▀\n\n"
            f"After detailing, validate with validate_art tool "
            f"(expected_width={width}, expected_height={height})."
        ),
        tools=[generate_terrain_tool, validate_art],
        llm=LLM(model=model),
    )

    critic = Agent(
        role="Terrain Critic",
        goal="Ensure terrain art preserves structure and evokes the right atmosphere",
        backstory=(
            "You evaluate ASCII terrain art for a dark-fantasy MUD. Your criteria:\n\n"
            "1. STRUCTURAL INTEGRITY — walls, doors, and borders from the scaffold are preserved\n"
            "2. ATMOSPHERIC QUALITY — does it evoke the intended mood?\n"
            "3. READABILITY — can you identify rooms, corridors, features at a glance?\n"
            "4. DIMENSIONAL COMPLIANCE — correct width and height, no ragged lines\n"
            "5. PALETTE DISCIPLINE — only approved characters used\n\n"
            "If the art meets all criteria, respond with exactly 'APPROVED'.\n"
            "Otherwise, provide specific feedback with line numbers."
        ),
        tools=[],
        llm=LLM(model=model),
    )

    scaffold_task = Task(
        description=(
            f"Use the generate_terrain tool to create a scaffold for biome '{biome}' "
            f"with width={width}, height={height}. Then add atmospheric detail for "
            f"the location '{location_name}'.\n\n"
            f"Description: {description}\n"
            f"Mood: {mood}\n\n"
            f"Preserve all structural elements from the scaffold. Detail the floor "
            f"and empty spaces with mood-appropriate characters and narrative elements.\n\n"
            f"Output ONLY the final detailed ASCII art — exactly {height} lines, "
            f"each exactly {width} characters."
        ),
        expected_output=f"Exactly {height} lines of detailed ASCII art, each exactly {width} characters wide",
        agent=artist,
    )

    critique_task = Task(
        description=(
            "Evaluate the terrain art. Check that structural elements (walls, doors) "
            "from the scaffold are preserved, atmosphere matches the mood, and "
            "dimensions are correct.\n\n"
            "If it meets all criteria, respond with exactly: APPROVED\n"
            "Otherwise, provide specific feedback with line numbers."
        ),
        expected_output="Either 'APPROVED' or specific revision feedback",
        agent=critic,
        context=[scaffold_task],
    )

    revise_task = Task(
        description=(
            "Revise the terrain art based on the critic's feedback. "
            "If the critique was 'APPROVED', reproduce the art unchanged.\n\n"
            f"Output ONLY the raw ASCII art — exactly {height} lines, "
            f"each exactly {width} characters. No commentary."
        ),
        expected_output=f"Exactly {height} lines of revised ASCII art, each exactly {width} characters wide",
        agent=artist,
        context=[scaffold_task, critique_task],
    )

    validate_task = Task(
        description=(
            "Run the validate_art tool on the revised art with "
            f"expected_width={width} and expected_height={height}. "
            "If validation fails, fix and re-validate. "
            "Output ONLY the final validated ASCII art."
        ),
        expected_output="Final ASCII art that passes dimensional validation",
        agent=artist,
        context=[revise_task],
    )

    return Crew(
        agents=[artist, critic],
        tasks=[scaffold_task, critique_task, revise_task, validate_task],
        process=Process.sequential,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/crews/test_cartographer.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/crews/cartographer/ engine/tests/crews/test_cartographer.py
git commit -m "feat(art): add Cartographer crew with WFC scaffold + LLM detailing"
```

---

## Task 9: Portraitist Crew

**Files:**
- Create: `engine/src/memento/crews/portraitist/__init__.py`
- Create: `engine/src/memento/crews/portraitist/crew.py`
- Test: `engine/tests/crews/test_portraitist.py`

- [ ] **Step 1: Write failing test**

```python
# engine/tests/crews/test_portraitist.py
"""Tests for the Portraitist crew."""
import pytest

from memento.crews.portraitist.crew import make_portraitist_crew


def test_make_portraitist_crew_returns_crew():
    crew = make_portraitist_crew(
        entity_name="Gravekeeper Mord",
        entity_type="npc",
        description="A gaunt figure in tattered robes, carrying a rusted lantern.",
        labels=["NPC"],
        biome="crypt",
    )
    assert crew is not None
    assert len(crew.agents) == 2  # sprite artist + style critic
    assert len(crew.tasks) >= 3


def test_portraitist_crew_artist_has_sprite_tools():
    crew = make_portraitist_crew(
        entity_name="Iron Sword",
        entity_type="item",
        description="A simple iron blade.",
        labels=["Weapon", "Item"],
        biome="default",
    )
    artist = crew.agents[0]
    tool_names = [t.name for t in artist.tools]
    assert "generate_sprite" in tool_names
    assert "validate_sprite" in tool_names


def test_portraitist_crew_icon_mode():
    crew = make_portraitist_crew(
        entity_name="Health Potion",
        entity_type="item",
        description="A small red vial.",
        labels=["Potion", "Item"],
        biome="default",
        icon_mode=True,
    )
    # Icon mode should mention small size in task description
    gen_task = crew.tasks[0]
    assert "8" in gen_task.description or "icon" in gen_task.description.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/crews/test_portraitist.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'memento.crews.portraitist'`

- [ ] **Step 3: Create package init**

```python
# engine/src/memento/crews/portraitist/__init__.py
```

- [ ] **Step 4: Implement portraitist crew**

```python
# engine/src/memento/crews/portraitist/crew.py
"""Portraitist crew — cellular automata pixel sprites for entities."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.art_tools import generate_sprite_tool, select_palette_tool
from memento.tools.sprite_validation import validate_sprite


def make_portraitist_crew(
    entity_name: str,
    entity_type: str,
    description: str,
    labels: list[str],
    biome: str = "default",
    mood: str = "dark",
    icon_mode: bool = False,
) -> Crew:
    """Build a crew that generates pixel sprite art for entities.

    The sprite artist uses cellular automata procgen to create silhouettes,
    then selects the best candidate. The style critic checks palette and
    readability.
    """
    model = get_model_for_crew("ascii_art")
    labels_json = str(labels).replace("'", '"')

    if icon_mode:
        size_desc = "8x8 pixel icon"
        size_px = 8
    elif entity_type == "npc" or "NPC" in labels or "Player" in labels:
        size_desc = "32x32 pixel portrait"
        size_px = 32
    else:
        size_desc = "16x16 pixel sprite"
        size_px = 16

    artist = Agent(
        role="Sprite Artist",
        goal=f"Generate a {size_desc} for a dark fantasy entity",
        backstory=(
            f"You create pixel sprites for a dark-fantasy permadeath MUD.\n\n"
            f"WORKFLOW:\n"
            f"1. Use select_palette tool with biome='{biome}' and mood='{mood}' to get colors\n"
            f"2. Use generate_sprite tool with entity_labels='{labels_json}' and biome='{biome}' "
            f"to generate a sprite candidate\n"
            f"3. Evaluate if the sprite's template and colors fit the entity description\n"
            f"4. If not satisfied, re-generate with a different seed\n"
            f"5. Use validate_sprite tool to check dimensions (expected_w={size_px}, expected_h={size_px})\n"
            f"6. Output the final sprite_b64 string and dimensions\n\n"
            f"Generate up to 4 candidates (seeds 1-4) and pick the best one.\n"
            f"Output format: JSON with keys sprite_b64, width, height"
        ),
        tools=[generate_sprite_tool, select_palette_tool, validate_sprite],
        llm=LLM(model=model),
    )

    critic = Agent(
        role="Style Critic",
        goal="Ensure sprite quality and consistency with entity description",
        backstory=(
            "You evaluate pixel sprites for a dark-fantasy MUD. Your criteria:\n\n"
            "1. DIMENSION COMPLIANCE — correct pixel size\n"
            "2. SILHOUETTE READABILITY — can you tell what the entity is at a glance?\n"
            "3. PALETTE CONSISTENCY — colors match the biome/mood\n"
            "4. DESCRIPTION MATCH — sprite template fits the entity type\n\n"
            "If the sprite meets all criteria, respond with exactly 'APPROVED'.\n"
            "Otherwise, suggest re-generation with different seed or template."
        ),
        tools=[],
        llm=LLM(model=model),
    )

    generate_task = Task(
        description=(
            f"Generate a {size_desc} for '{entity_name}' ({entity_type}).\n\n"
            f"Description: {description}\n"
            f"Labels: {labels_json}\n"
            f"Biome: {biome}\n\n"
            f"Use the generate_sprite tool to create candidates. Pick the best one.\n"
            f"Validate with validate_sprite (expected_w={size_px}, expected_h={size_px}).\n"
            f"Output JSON: {{\"sprite_b64\": \"...\", \"width\": {size_px}, \"height\": {size_px}}}"
        ),
        expected_output=f"JSON with sprite_b64, width={size_px}, height={size_px}",
        agent=artist,
    )

    critique_task = Task(
        description=(
            f"Evaluate the sprite for '{entity_name}'. Check that the template "
            f"choice fits a {entity_type}, the palette matches {biome}/{mood}, "
            f"and the silhouette is readable at {size_px}x{size_px}.\n\n"
            "If it meets all criteria, respond with exactly: APPROVED\n"
            "Otherwise, suggest re-generation with a different seed."
        ),
        expected_output="Either 'APPROVED' or specific feedback",
        agent=critic,
        context=[generate_task],
    )

    revise_task = Task(
        description=(
            "If the critic approved, output the same sprite JSON unchanged.\n"
            "If the critic suggested changes, re-generate with a different seed "
            "and validate again.\n\n"
            f"Output JSON: {{\"sprite_b64\": \"...\", \"width\": {size_px}, \"height\": {size_px}}}"
        ),
        expected_output=f"JSON with sprite_b64, width={size_px}, height={size_px}",
        agent=artist,
        context=[generate_task, critique_task],
    )

    return Crew(
        agents=[artist, critic],
        tasks=[generate_task, critique_task, revise_task],
        process=Process.sequential,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/crews/test_portraitist.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/crews/portraitist/ engine/tests/crews/test_portraitist.py
git commit -m "feat(art): add Portraitist crew with cellular automata sprites + LLM art direction"
```

---

## Task 10: Art Dispatcher Flow

**Files:**
- Create: `engine/src/memento/flows/art_gen.py`
- Test: `engine/tests/flows/test_art_gen.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/flows/test_art_gen.py
"""Tests for the art generation dispatcher."""
import pytest
from unittest.mock import patch, MagicMock

from memento.flows.art_gen import generate_entity_art, _parse_scene_art, _parse_sprite_result


def test_parse_scene_art_extracts_lines():
    raw = "###\n...\n###"
    art, w, h = _parse_scene_art(raw, expected_w=3, expected_h=3)
    assert art == "###\n...\n###"
    assert w == 3
    assert h == 3


def test_parse_scene_art_strips_commentary():
    raw = "Here is the art:\n```\n###\n...\n###\n```\nHope you like it!"
    art, w, h = _parse_scene_art(raw, expected_w=3, expected_h=3)
    assert art == "###\n...\n###"
    assert h == 3


def test_parse_sprite_result_extracts_json():
    raw = '{"sprite_b64": "abc123", "width": 16, "height": 16}'
    result = _parse_sprite_result(raw)
    assert result["sprite_b64"] == "abc123"
    assert result["width"] == 16


def test_parse_sprite_result_from_commentary():
    raw = 'Here is the result:\n{"sprite_b64": "abc123", "width": 32, "height": 32}\nDone!'
    result = _parse_sprite_result(raw)
    assert result["sprite_b64"] == "abc123"


@patch("memento.flows.art_gen._get_kg_client")
@patch("memento.flows.art_gen.make_cartographer_crew")
def test_generate_entity_art_location(mock_crew_fn, mock_kg):
    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = MagicMock(raw="###\n...\n###")
    mock_crew_fn.return_value = mock_crew
    mock_client = MagicMock()
    mock_kg.return_value = mock_client

    generate_entity_art(
        entity_uid="test-uuid",
        name="Test Room",
        entity_type="location",
        description="A test room",
        labels=["Location"],
        biome="default",
    )

    mock_crew_fn.assert_called_once()
    mock_client.kg.update_entity.assert_called_once()
    call_kwargs = mock_client.kg.update_entity.call_args
    # Should have scene_art in the attributes
    attrs = call_kwargs[1].get("attributes") or call_kwargs[0][4] if len(call_kwargs[0]) > 4 else {}
    assert "scene_art" in str(call_kwargs)


@patch("memento.flows.art_gen._get_kg_client")
@patch("memento.flows.art_gen.make_portraitist_crew")
def test_generate_entity_art_npc(mock_crew_fn, mock_kg):
    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = MagicMock(
        raw='{"sprite_b64": "abc123", "width": 32, "height": 32}'
    )
    mock_crew_fn.return_value = mock_crew
    mock_client = MagicMock()
    mock_kg.return_value = mock_client

    generate_entity_art(
        entity_uid="test-uuid",
        name="Test NPC",
        entity_type="npc",
        description="A test character",
        labels=["NPC"],
        biome="crypt",
    )

    mock_crew_fn.assert_called_once()
    mock_client.kg.update_entity.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/flows/test_art_gen.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'memento.flows.art_gen'`

- [ ] **Step 3: Implement art_gen.py**

```python
# engine/src/memento/flows/art_gen.py
"""Art generation dispatcher.

Single entry point for all art generation. Routes to the appropriate crew
(cartographer for locations, portraitist for NPCs/items) and persists
results as entity attributes on the KG.
"""

import json
import logging
import re
from datetime import datetime, timezone

from memento.crews.cartographer.crew import make_cartographer_crew
from memento.crews.portraitist.crew import make_portraitist_crew

logger = logging.getLogger(__name__)


def _get_kg_client():
    """Get the KG client. Separated for test mocking."""
    from memento.client import get_client
    return get_client()


def _parse_scene_art(raw: str, expected_w: int, expected_h: int) -> tuple[str, int, int]:
    """Extract ASCII art from crew output, stripping commentary and fences.

    Returns (art_string, width, height).
    """
    lines = raw.strip().split("\n")

    # Strip markdown fences if present
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]

    # Filter out lines that look like commentary (don't start with art chars)
    art_chars = set("#.:|/\\-_~^*@'\" ═║╔╗╚╝╦╩╠╣╬─│┌┐└┘░▒▓█▄▀+◊†↑♣T=")
    art_lines = []
    for line in lines:
        if not line:
            continue
        if all(c in art_chars for c in line):
            art_lines.append(line)
        elif len(line) >= expected_w * 0.8:
            # Might be art with some unexpected chars — keep it
            art_lines.append(line[:expected_w])

    # Pad/trim to expected dimensions
    while len(art_lines) < expected_h:
        art_lines.append(" " * expected_w)
    art_lines = art_lines[:expected_h]
    art_lines = [l.ljust(expected_w)[:expected_w] for l in art_lines]

    art_str = "\n".join(art_lines)
    return art_str, expected_w, len(art_lines)


def _parse_sprite_result(raw: str) -> dict:
    """Extract sprite JSON from crew output.

    Returns dict with sprite_b64, width, height.
    """
    # Try to find JSON in the output
    match = re.search(r'\{[^}]*"sprite_b64"[^}]*\}', raw, re.DOTALL)
    if match:
        return json.loads(match.group())
    # Fallback: try parsing the whole thing
    return json.loads(raw)


def _biome_for_labels(labels: list[str]) -> str:
    """Infer a biome hint from entity labels. Fallback to 'default'."""
    label_set = set(l.lower() for l in labels)
    if label_set & {"undead", "skeleton", "ghost"}:
        return "crypt"
    if label_set & {"beast", "wolf", "spider"}:
        return "forest"
    return "default"


def generate_entity_art(
    entity_uid: str,
    name: str,
    entity_type: str,
    description: str,
    labels: list[str],
    biome: str = "default",
    mood: str = "dark",
) -> None:
    """Generate all art for an entity and persist to KG.

    Called from NPC/item/world gen flows as a background thread target.

    Args:
        entity_uid: Entity UUID in the KG.
        name: Entity display name.
        entity_type: One of 'location', 'npc', 'item'.
        description: Entity description text.
        labels: Entity KG labels (e.g. ['NPC'], ['Weapon', 'Item']).
        biome: Biome for palette/tileset selection.
        mood: Mood modifier for palette.
    """
    try:
        client = _get_kg_client()
        attrs: dict = {}
        now = datetime.now(timezone.utc).isoformat()

        if entity_type == "location":
            crew = make_cartographer_crew(
                location_name=name,
                description=description,
                mood=mood,
                biome=biome,
                width=35,
                height=20,
            )
            result = crew.kickoff()
            art_str, w, h = _parse_scene_art(result.raw, 35, 20)
            attrs["scene_art"] = art_str
            attrs["scene_art_w"] = w
            attrs["scene_art_h"] = h
            # Also set a tile glyph based on biome
            glyph_map = {
                "crypt": ("†", "#8b0000"),
                "forest": ("♣", "#2d5a2d"),
                "village": ("⌂", "#cd853f"),
                "ruins": ("Ω", "#6b6b6b"),
                "default": ("·", "#4a4a5e"),
            }
            glyph, fg = glyph_map.get(biome, glyph_map["default"])
            attrs["tile_glyph"] = glyph
            attrs["tile_fg"] = fg

        elif entity_type == "npc":
            crew = make_portraitist_crew(
                entity_name=name,
                entity_type="npc",
                description=description,
                labels=labels,
                biome=biome,
                mood=mood,
            )
            result = crew.kickoff()
            sprite_data = _parse_sprite_result(result.raw)
            attrs["portrait_sprite"] = sprite_data["sprite_b64"]
            attrs["portrait_w"] = sprite_data["width"]
            attrs["portrait_h"] = sprite_data["height"]
            attrs["tile_glyph"] = "@"
            attrs["tile_fg"] = "#d4a574"

        elif entity_type == "item":
            crew = make_portraitist_crew(
                entity_name=name,
                entity_type="item",
                description=description,
                labels=labels,
                biome=biome,
                mood=mood,
                icon_mode=True,
            )
            result = crew.kickoff()
            sprite_data = _parse_sprite_result(result.raw)
            attrs["icon_sprite"] = sprite_data["sprite_b64"]
            attrs["icon_w"] = sprite_data["width"]
            attrs["icon_h"] = sprite_data["height"]
            attrs["tile_glyph"] = "!"
            attrs["tile_fg"] = "#daa520"

        else:
            logger.warning(f"Unknown entity_type '{entity_type}' for art generation")
            return

        attrs["art_style"] = "dark_fantasy"
        attrs["art_generated_at"] = now

        client.kg.update_entity(
            entity_uid, name, labels, None,
            attributes=attrs,
        )
        logger.info(f"Art generated for {entity_type} '{name}' ({entity_uid})")

    except Exception:
        logger.exception(f"Art generation failed for {entity_type} '{name}' ({entity_uid})")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/flows/test_art_gen.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/flows/art_gen.py engine/tests/flows/test_art_gen.py
git commit -m "feat(art): add art generation dispatcher with KG persistence"
```

---

## Task 11: Integrate Art into NPC Generation Flow

**Files:**
- Modify: `engine/src/memento/flows/npc_gen.py:113-127`
- Test: `engine/tests/flows/test_art_gen.py` (already covers dispatcher)

- [ ] **Step 1: Read current NPC gen art integration**

Read `engine/src/memento/flows/npc_gen.py` lines 110-130 to confirm the exact threading pattern.

- [ ] **Step 2: Replace enrichment call with art dispatcher**

In `engine/src/memento/flows/npc_gen.py`, replace the existing art thread block (around lines 113-127) that calls `enrich_entity_art` with the new dispatcher:

Old code (approximate):
```python
threading.Thread(
    target=enrich_entity_art,
    args=(_uid, _name, "npc", _desc, {}),
    daemon=True,
).start()
```

New code:
```python
from memento.flows.art_gen import generate_entity_art

threading.Thread(
    target=generate_entity_art,
    args=(_uid, _name, "npc", _desc, _labels, _biome, "dark"),
    daemon=True,
).start()
```

Where `_labels` comes from the NPC's labels (e.g. `["NPC"]`) and `_biome` from the region context. If biome isn't available in context, use `"default"`.

- [ ] **Step 3: Verify import and no syntax errors**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -c "from memento.flows.npc_gen import NPCGenerationFlow; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/flows/npc_gen.py
git commit -m "feat(art): route NPC art generation through new art dispatcher"
```

---

## Task 12: Integrate Art into Item Generation Flow

**Files:**
- Modify: `engine/src/memento/flows/item_gen.py:39-44`

- [ ] **Step 1: Read current item gen flow end**

Read `engine/src/memento/flows/item_gen.py` to confirm the exact structure of `balance_check()` and how item UUIDs are available.

- [ ] **Step 2: Add art generation after balance_check**

Add a new flow step or post-processing in `balance_check` that spawns art threads for each finalized item. The exact code depends on how item UUIDs are structured in `items_final`, but the pattern is:

```python
import threading
import json
import re
from memento.flows.art_gen import generate_entity_art

# After balance crew kickoff, parse items and spawn art threads:
for item_json in self.state.items_final:
    # Extract UUID and metadata from the item output
    item = json.loads(item_json) if isinstance(item_json, str) else item_json
    item_uid = item.get("uuid") or item.get("id")
    if not item_uid:
        continue
    item_name = item.get("name", "Unknown Item")
    item_desc = item.get("description", "")
    item_labels = item.get("labels", ["Item"])
    threading.Thread(
        target=generate_entity_art,
        args=(item_uid, item_name, "item", item_desc, item_labels, "default", "dark"),
        daemon=True,
    ).start()
```

- [ ] **Step 3: Verify import and no syntax errors**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -c "from memento.flows.item_gen import ItemGenerationFlow; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/flows/item_gen.py
git commit -m "feat(art): spawn item art generation after balance check"
```

---

## Task 13: Integrate Art into World Generation Flow

**Files:**
- Modify: `engine/src/memento/flows/world_gen.py` (after location persistence)

- [ ] **Step 1: Read current world gen location persistence**

Read `engine/src/memento/flows/world_gen.py` lines 150-168 to confirm how locations are persisted and what data is available.

- [ ] **Step 2: Add art generation for locations**

After locations are persisted in `persist_room_maps()`, spawn art threads for each location:

```python
import threading
from memento.flows.art_gen import generate_entity_art

# After persisting each location:
for loc_info in self.state.locations:
    threading.Thread(
        target=generate_entity_art,
        args=(
            loc_info.uuid,
            loc_info.name,
            "location",
            loc_info.description,
            ["Location"],
            self.state.biome or "default",
            loc_info.mood or "dark",
        ),
        daemon=True,
    ).start()
```

- [ ] **Step 3: Verify import and no syntax errors**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -c "from memento.flows.world_gen import WorldGenFlow; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/flows/world_gen.py
git commit -m "feat(art): spawn location art generation after world gen persistence"
```

---

## Task 14: Update Enrichment Flow Fallback

**Files:**
- Modify: `engine/src/memento/flows/enrichment.py:144-204`

- [ ] **Step 1: Read current enrichment art flow**

Read `engine/src/memento/flows/enrichment.py` lines 140-250 to confirm exact function signatures and KG update patterns.

- [ ] **Step 2: Update enrich_entity_art to route through dispatcher**

Replace the direct crew calls in `enrich_entity_art()` with calls to the art dispatcher. The enrichment flow becomes a fallback that checks for missing art attributes (not just `ascii_art` but also `portrait_sprite`, `icon_sprite`, `scene_art`):

```python
from memento.flows.art_gen import generate_entity_art

def enrich_entity_art(entity_uuid, entity_name, entity_type, existing_summary, existing_attributes):
    """Fallback art generation for entities that missed art during creation."""
    attrs = existing_attributes or {}

    # Check what art is missing
    if entity_type == "location" and attrs.get("scene_art"):
        return None  # already has art
    if entity_type == "npc" and attrs.get("portrait_sprite"):
        return None
    if entity_type == "item" and attrs.get("icon_sprite"):
        return None

    # Infer labels and biome from existing attributes
    labels = attrs.get("labels", [entity_type.upper()])
    biome = attrs.get("biome", "default")
    mood = attrs.get("mood", "dark")
    description = existing_summary or attrs.get("description", "")

    generate_entity_art(
        entity_uid=entity_uuid,
        name=entity_name,
        entity_type=entity_type,
        description=description,
        labels=labels,
        biome=biome,
        mood=mood,
    )
```

Also update `enrich_room_art()` to check for new attribute names.

- [ ] **Step 3: Verify import and no syntax errors**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -c "from memento.flows.enrichment import enrich_entity_art; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/flows/enrichment.py
git commit -m "feat(art): update enrichment flow to use art dispatcher as fallback"
```

---

## Task 15: Client — Entity State Types for Sprites

**Files:**
- Modify: `client/src/state/game-state.ts:19-26`

- [ ] **Step 1: Read current LocationEntity interface**

Read `client/src/state/game-state.ts` lines 18-26 to confirm the exact interface.

- [ ] **Step 2: Add sprite attribute fields**

Extend `LocationEntity` with the new art attributes:

```typescript
export interface LocationEntity {
  id: string;
  name: string;
  role?: string;
  ascii_art?: string;
  // New art department attributes
  scene_art?: string;
  scene_art_w?: number;
  scene_art_h?: number;
  portrait_sprite?: string;  // base64 PNG
  portrait_w?: number;
  portrait_h?: number;
  icon_sprite?: string;      // base64 PNG
  icon_w?: number;
  icon_h?: number;
  tile_glyph?: string;
  tile_fg?: string;
  x?: number;
  y?: number;
}
```

- [ ] **Step 3: Update state sync to preserve new fields**

In the same file, find where `ascii_art` is preserved during state updates (around lines 138-149, 189-200) and add the new fields to the same spread/preservation logic.

- [ ] **Step 4: Verify build**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/client && npx tsc --noEmit
```

Expected: No type errors.

- [ ] **Step 5: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add client/src/state/game-state.ts
git commit -m "feat(art): add sprite and scene art attributes to LocationEntity type"
```

---

## Task 16: Client — Sprite Renderer

**Files:**
- Create: `client/src/ui/sprite-renderer.ts`

- [ ] **Step 1: Implement sprite renderer**

```typescript
// client/src/ui/sprite-renderer.ts
/**
 * Pixel sprite renderer for canvas contexts.
 * Decodes base64 PNG sprites and draws them with nearest-neighbor scaling
 * for crisp 8-bit aesthetic.
 */

import type { CharSize } from '../renderer/canvas-text';

/** Cache decoded ImageBitmap objects by their base64 hash. */
const spriteCache = new Map<string, HTMLImageElement>();

/**
 * Get or create a cached Image element from a base64 PNG string.
 */
function getOrLoadImage(spriteB64: string): HTMLImageElement | null {
  const cached = spriteCache.get(spriteB64);
  if (cached && cached.complete) return cached;
  if (cached) return null; // still loading

  const img = new Image();
  img.src = `data:image/png;base64,${spriteB64}`;
  spriteCache.set(spriteB64, img);

  // Return null on first call; image will be ready on next paint
  return img.complete ? img : null;
}

/**
 * Draw a pixel sprite onto a canvas context at a given pixel position.
 * Uses nearest-neighbor scaling for crisp pixel art.
 *
 * @param ctx - Canvas rendering context
 * @param x - X position in pixels
 * @param y - Y position in pixels
 * @param spriteB64 - Base64-encoded PNG data
 * @param scale - Scale factor (default 2 for 2x crisp rendering)
 * @returns Height consumed in pixels, or 0 if image not yet loaded
 */
export function drawSprite(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  spriteB64: string,
  scale: number = 2,
): number {
  const img = getOrLoadImage(spriteB64);
  if (!img) return 0;

  const w = img.naturalWidth * scale;
  const h = img.naturalHeight * scale;

  // Nearest-neighbor scaling for pixel art
  const prevSmoothing = ctx.imageSmoothingEnabled;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(img, x, y, w, h);
  ctx.imageSmoothingEnabled = prevSmoothing;

  return h;
}

/**
 * Draw a pixel sprite centered within a given region width.
 */
export function drawSpriteCentered(
  ctx: CanvasRenderingContext2D,
  regionX: number,
  regionWidth: number,
  y: number,
  spriteB64: string,
  scale: number = 2,
): number {
  const img = getOrLoadImage(spriteB64);
  if (!img) return 0;

  const w = img.naturalWidth * scale;
  const h = img.naturalHeight * scale;
  const x = regionX + Math.floor((regionWidth - w) / 2);

  const prevSmoothing = ctx.imageSmoothingEnabled;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(img, x, y, w, h);
  ctx.imageSmoothingEnabled = prevSmoothing;

  return h;
}

/**
 * Clear the sprite cache. Call when navigating away or on memory pressure.
 */
export function clearSpriteCache(): void {
  spriteCache.clear();
}
```

- [ ] **Step 2: Verify build**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/client && npx tsc --noEmit
```

Expected: No type errors.

- [ ] **Step 3: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add client/src/ui/sprite-renderer.ts
git commit -m "feat(art): add sprite renderer with nearest-neighbor pixel scaling"
```

---

## Task 17: Client — Render Portrait Sprites in Entity Cards

**Files:**
- Modify: `client/src/map/card-renderer.ts:58-172`

- [ ] **Step 1: Read current drawCard implementation**

Read `client/src/map/card-renderer.ts` lines 55-175 to understand the full rendering flow and where to add sprite rendering.

- [ ] **Step 2: Add sprite rendering to entity cards**

Import the sprite renderer and add portrait rendering after the entity summary section (around line 128). The exact insertion point depends on the current code structure, but the pattern is:

```typescript
import { drawSpriteCentered } from '../ui/sprite-renderer';

// Inside drawCard, after rendering the summary text:
if (content.portrait_sprite) {
  curY += 4; // small gap
  const spriteH = drawSpriteCentered(
    ctx, x, cardWidth, curY, content.portrait_sprite, 2
  );
  if (spriteH > 0) curY += spriteH + 4;
}
```

Also extend the `CardContent` interface to include the sprite field:

```typescript
portrait_sprite?: string;
```

- [ ] **Step 3: Verify build**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/client && npx tsc --noEmit
```

Expected: No type errors.

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add client/src/map/card-renderer.ts
git commit -m "feat(art): render portrait sprites in entity cards"
```

---

## Task 18: Add Crew Model Config Entry

**Files:**
- Modify: `engine/src/memento/config/config/defaults.yaml` (or equivalent config file)

- [ ] **Step 1: Read current config structure**

Read the config files under `engine/src/memento/config/config/` to see how crew model overrides are structured.

- [ ] **Step 2: Add cartographer and portraitist crew entries**

Ensure the config has entries for the new crews so `get_model_for_crew()` can resolve them. If the config uses a `crews` section, add:

```yaml
crews:
  ascii_art: default    # existing
  cartographer: default # new — falls back to ascii_art model
  portraitist: default  # new
```

The exact format depends on the config structure. If crews not in the config already fall back to the default model, no changes may be needed — but verify.

- [ ] **Step 3: Verify config loads**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -c "from memento.config import get_model_for_crew; print(get_model_for_crew('cartographer')); print(get_model_for_crew('portraitist'))"
```

Expected: Prints model names (or default model) without error.

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/config/
git commit -m "feat(art): add crew model config entries for cartographer and portraitist"
```

---

## Task 19: End-to-End Smoke Test

**Files:**
- Create: `engine/tests/integration/test_art_e2e.py`

- [ ] **Step 1: Write integration smoke test**

```python
# engine/tests/integration/test_art_e2e.py
"""End-to-end smoke test for the art department pipeline.

Tests the full flow: procgen → crew construction → output parsing.
Does NOT run actual LLM calls — mocks the crew kickoff.
"""
import json
import pytest
from unittest.mock import patch, MagicMock

from memento.flows.art_gen import generate_entity_art
from memento.tools.procgen.wfc import generate_terrain_scaffold
from memento.tools.procgen.sprite_gen import generate_sprite
from memento.tools.procgen.palette import select_palette
from memento.tools.procgen.templates import select_template


def test_full_terrain_pipeline():
    """WFC scaffold → palette → cartographer crew builds correctly."""
    scaffold = generate_terrain_scaffold("crypt", width=20, height=10, seed=42)
    lines = scaffold.split("\n")
    assert len(lines) == 10
    assert all(len(l) == 20 for l in lines)

    palette = select_palette("crypt", "dark")
    assert len(palette.primary) == 3


def test_full_sprite_pipeline():
    """Template → palette → sprite gen produces valid base64."""
    template = select_template(["NPC"])
    palette = select_palette("crypt")
    sprite_b64 = generate_sprite(template, palette, seed=42)

    import base64
    from PIL import Image
    import io
    img_bytes = base64.b64decode(sprite_b64)
    img = Image.open(io.BytesIO(img_bytes))
    assert img.size == (template.size, template.size)
    assert img.mode == "RGBA"


def test_item_sprite_pipeline():
    """Item template → small icon sprite."""
    template = select_template(["Weapon", "Item"])
    assert template.size == 8
    palette = select_palette("default")
    sprite_b64 = generate_sprite(template, palette, seed=42)

    import base64
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(base64.b64decode(sprite_b64)))
    assert img.size == (8, 8)


@patch("memento.flows.art_gen._get_kg_client")
@patch("memento.flows.art_gen.make_cartographer_crew")
def test_dispatcher_location_e2e(mock_crew_fn, mock_kg):
    """Dispatcher routes location to cartographer and persists."""
    mock_crew = MagicMock()
    # Simulate crew returning a 35x20 ASCII grid
    art = "\n".join(["#" * 35] + ["#" + "." * 33 + "#"] * 18 + ["#" * 35])
    mock_crew.kickoff.return_value = MagicMock(raw=art)
    mock_crew_fn.return_value = mock_crew
    mock_client = MagicMock()
    mock_kg.return_value = mock_client

    generate_entity_art("uuid-1", "Dark Crypt", "location", "A dark crypt.", ["Location"], "crypt", "dark")

    mock_crew_fn.assert_called_once()
    assert mock_client.kg.update_entity.called
    call_args = mock_client.kg.update_entity.call_args
    assert "scene_art" in str(call_args)


@patch("memento.flows.art_gen._get_kg_client")
@patch("memento.flows.art_gen.make_portraitist_crew")
def test_dispatcher_npc_e2e(mock_crew_fn, mock_kg):
    """Dispatcher routes NPC to portraitist and persists."""
    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = MagicMock(
        raw='{"sprite_b64": "iVBORtest", "width": 32, "height": 32}'
    )
    mock_crew_fn.return_value = mock_crew
    mock_client = MagicMock()
    mock_kg.return_value = mock_client

    generate_entity_art("uuid-2", "Skeleton Guard", "npc", "A skeletal warrior.", ["NPC"], "crypt", "dark")

    mock_crew_fn.assert_called_once()
    assert mock_client.kg.update_entity.called
    call_args = mock_client.kg.update_entity.call_args
    assert "portrait_sprite" in str(call_args)
```

- [ ] **Step 2: Run integration tests**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/integration/test_art_e2e.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 3: Run full test suite**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/ -v --tb=short
```

Expected: All tests pass, no regressions.

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/tests/integration/test_art_e2e.py
git commit -m "test(art): add end-to-end smoke tests for art department pipeline"
```
