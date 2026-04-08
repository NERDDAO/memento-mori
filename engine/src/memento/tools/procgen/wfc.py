"""Wave Function Collapse terrain scaffold generator.

Generates structural ASCII grids from tile adjacency rules. The output is
a scaffold -- wall/floor/door positions that an LLM artist can then detail
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
            if 0 <= ny < height and 0 <= nx < width:
                cell = possible[ny][nx]
                if cell is not None:
                    allowed = set(adj.get(direction, []))
                    possible[ny][nx] = cell & allowed

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
        cell = possible[cy][cx]
        assert cell is not None  # guaranteed by candidate selection
        grid[cy][cx] = _collapse_cell(cell, tileset, rng)
        possible[cy][cx] = None
        propagate(cy, cx)

    # Fill any remaining uncollapsed cells (contradiction fallback)
    for y in range(height):
        for x in range(width):
            if grid[y][x] is None:
                cell = possible[y][x]
                if cell is not None and len(cell) > 0:
                    grid[y][x] = _collapse_cell(cell, tileset, rng)
                else:
                    grid[y][x] = "."  # safe fallback

    # Build output string — all cells are now resolved
    resolved: list[list[str]] = [
        [c if c is not None else "." for c in row] for row in grid
    ]
    lines = ["".join(row) for row in resolved]
    return "\n".join(lines)
