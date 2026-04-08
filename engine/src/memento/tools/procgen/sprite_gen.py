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


def _colorize_symmetric(
    filled: np.ndarray,
    mask: np.ndarray,
    palette: Palette,
    rng: random.Random,
    full_w: int,
) -> np.ndarray:
    """Convert a filled mask into an RGBA pixel array with bilateral symmetry.

    Colorizes only the left half (x < half_w), then mirrors pixel colors to the
    right half to guarantee perfect bilateral symmetry.

    Body regions (1) get primary colors, detail regions (2) get accent colors.
    Edges get slightly darker shading for depth.
    """
    h, w = filled.shape
    half_w = full_w // 2
    pixels = np.zeros((h, full_w, 4), dtype=np.uint8)

    # Pick base colors for this sprite
    body_rgb = hex_to_rgb(rng.choice(palette.primary))
    detail_rgb = hex_to_rgb(rng.choice(palette.accent))
    highlight_rgb = hex_to_rgb(rng.choice(palette.light))

    # Colorize only x < half_w, then mirror
    for y in range(h):
        for x in range(half_w):
            if filled[y, x] == 0:
                # transparent — mirror side also transparent (already zero)
                continue

            # Choose base color by cell type
            if filled[y, x] == 2:
                base = detail_rgb
            else:
                base = body_rgb

            # Edge darkening: if adjacent to empty in the full symmetric grid,
            # darken by 20%. Check filled array (left half only, mirrored).
            is_edge = False
            mirror_x = full_w - 1 - x
            for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                ny, nx = y + dy, x + dx
                if ny < 0 or ny >= h or nx < 0 or nx >= full_w:
                    is_edge = True
                    break
                # For neighbor pixels in the full grid: left half uses filled[ny, nx],
                # right half mirrors filled[ny, full_w-1-nx]
                if nx < half_w:
                    neighbor_val = filled[ny, nx] if nx >= 0 else 0
                else:
                    mirror_nx = full_w - 1 - nx
                    neighbor_val = filled[ny, mirror_nx] if mirror_nx >= 0 and mirror_nx < w else 0
                if neighbor_val == 0:
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

            color = [r, g, b, 255]
            pixels[y, x] = color
            # Mirror to right half
            pixels[y, mirror_x] = color

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

    # Apply CA noise to the half-mask (left half for symmetric templates)
    filled_half = _apply_ca_noise(template.mask, rng)

    if template.symmetric:
        full_w = template.size
        half_w = full_w // 2

        # Build symmetric full filled array for reference
        full_filled = np.zeros((template.size, full_w), dtype=np.int8)
        full_filled[:filled_half.shape[0], :filled_half.shape[1]] = filled_half
        for y in range(filled_half.shape[0]):
            for x in range(filled_half.shape[1]):
                mirror_x = full_w - 1 - x
                full_filled[y, mirror_x] = filled_half[y, x]

        # Build symmetric mask for colorization reference
        full_mask = np.zeros((template.size, full_w), dtype=np.int8)
        full_mask[:template.mask.shape[0], :template.mask.shape[1]] = template.mask
        for y in range(template.mask.shape[0]):
            for x in range(template.mask.shape[1]):
                mirror_x = full_w - 1 - x
                full_mask[y, mirror_x] = template.mask[y, x]

        # Colorize with symmetry guarantee: colorize left half, mirror colors right
        pixels = _colorize_symmetric(filled_half, full_mask, palette, rng, full_w)
    else:
        full_filled = filled_half
        full_mask = template.mask
        # Non-symmetric: colorize normally
        h, w = full_filled.shape
        pixels = np.zeros((h, w, 4), dtype=np.uint8)
        body_rgb = hex_to_rgb(rng.choice(palette.primary))
        detail_rgb = hex_to_rgb(rng.choice(palette.accent))
        highlight_rgb = hex_to_rgb(rng.choice(palette.light))
        for y in range(h):
            for x in range(w):
                if full_filled[y, x] == 0:
                    continue
                base = detail_rgb if full_filled[y, x] == 2 else body_rgb
                is_edge = False
                for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    ny, nx = y + dy, x + dx
                    if ny < 0 or ny >= h or nx < 0 or nx >= w or full_filled[ny, nx] == 0:
                        is_edge = True
                        break
                if is_edge:
                    r = max(0, int(base[0] * 0.7))
                    g = max(0, int(base[1] * 0.7))
                    b = max(0, int(base[2] * 0.7))
                else:
                    if rng.random() < 0.1:
                        r, g, b = highlight_rgb
                    else:
                        r, g, b = base
                pixels[y, x] = [r, g, b, 255]

    # Convert to PIL Image
    img = Image.fromarray(pixels, mode="RGBA")

    # Encode to base64 PNG
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")
