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
    assert "#" in tileset.tiles


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
    result = generate_terrain_scaffold("default", width=10, height=5, seed=42)
    lines = result.strip().split("\n")
    assert len(lines) == 5
    assert all(len(l) == 10 for l in lines)
