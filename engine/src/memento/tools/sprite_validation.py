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
