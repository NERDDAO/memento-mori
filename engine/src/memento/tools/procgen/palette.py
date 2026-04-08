"""Per-biome color palette system for the art department."""

import json
import random
from dataclasses import dataclass
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
