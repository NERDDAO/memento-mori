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
