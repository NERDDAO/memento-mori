"""Terrain packing/unpacking for onchain storage."""

TILE_CHAR_TO_TYPE: dict[str, int] = {
    " ": 0, "#": 2, ".": 1, "+": 3, "~": 4,
    "T": 5, "B": 5, "C": 5, "S": 5,
    "@": 1, "*": 1, "^": 1, ":": 1, "-": 1,
}

TILE_TYPE_TO_CHAR: dict[int, str] = {
    0: " ", 1: ".", 2: "#", 3: "+", 4: "~", 5: "T",
}


def pack_terrain(tiles: list[str], width: int, height: int) -> bytes:
    """Pack ASCII tile grid into bytes for onchain storage.

    Args:
        tiles: Flat row-major array of single-char tile strings.
        width: Grid width.
        height: Grid height.

    Returns:
        Packed bytes of length width*height.
    """
    expected = width * height
    data = bytearray(expected)
    for i in range(expected):
        ch = tiles[i] if i < len(tiles) else " "
        data[i] = TILE_CHAR_TO_TYPE.get(ch, 1)
    return bytes(data)


def unpack_terrain(data: bytes, width: int, height: int) -> list[str]:
    """Unpack onchain terrain bytes to ASCII tile characters."""
    return [TILE_TYPE_TO_CHAR.get(b, ".") for b in data]
