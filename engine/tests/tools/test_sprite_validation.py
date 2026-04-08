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
