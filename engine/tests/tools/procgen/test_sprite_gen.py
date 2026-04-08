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
