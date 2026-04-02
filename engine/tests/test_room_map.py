"""Tests for room map extraction."""

from memento.room_map import extract_room_map, generate_fallback_map, _validate_room_map


def test_extract_from_json_code_block():
    output = '''
Here is the location design...

```json
{
  "width": 10,
  "height": 10,
  "tiles": ["#", ".", ".", ".", ".", ".", ".", ".", ".", "#",
            "#", ".", ".", ".", ".", ".", ".", ".", ".", "#",
            "#", ".", ".", ".", ".", ".", ".", ".", ".", "#",
            "#", ".", ".", ".", ".", ".", ".", ".", ".", "#",
            "#", ".", ".", ".", ".", ".", ".", ".", ".", "#",
            "#", ".", ".", ".", ".", ".", ".", ".", ".", "#",
            "#", ".", ".", ".", ".", ".", ".", ".", ".", "#",
            "#", ".", ".", ".", ".", ".", ".", ".", ".", "#",
            "#", ".", ".", ".", ".", ".", ".", ".", ".", "#",
            "#", ".", ".", ".", ".", ".", ".", ".", ".", "#"],
  "npcs": [{"x": 5, "y": 3, "ch": "K", "name": "Barkeeper"}],
  "items": [],
  "exits": [{"x": 9, "y": 5, "ch": "+", "direction": "east", "target": "Forest"}],
  "spawn": {"x": 5, "y": 8}
}
```

That concludes the design.
'''
    result = extract_room_map(output, "Test Location")
    assert result is not None
    assert result["width"] == 10
    assert result["height"] == 10
    assert len(result["tiles"]) == 100
    assert len(result["npcs"]) == 1
    assert result["npcs"][0]["name"] == "Barkeeper"


def test_extract_sets_location_name():
    output = '```json\n{"width": 10, "height": 10, "tiles": ' + '["." for _ in range(100)]'.replace('for _ in range(100)', ', '.join(['"."'] * 100)) + ', "npcs": [], "items": [], "exits": [], "spawn": {"x": 5, "y": 5}}\n```'
    # Build valid JSON properly
    tiles = ', '.join(['"."'] * 100)
    output = f'```json\n{{"width": 10, "height": 10, "tiles": [{tiles}], "npcs": [], "items": [], "exits": [], "spawn": {{"x": 5, "y": 5}}}}\n```'
    result = extract_room_map(output, "My Location")
    assert result is not None
    assert result["name"] == "My Location"


def test_extract_returns_none_for_invalid():
    result = extract_room_map("No JSON here at all", "Test")
    assert result is None


def test_extract_returns_none_for_invalid_json():
    result = extract_room_map('```json\n{"not": "a room map"}\n```', "Test")
    assert result is None


def test_generate_fallback_map():
    m = generate_fallback_map("Fallback Room", width=20, height=10)
    assert m["name"] == "Fallback Room"
    assert m["width"] == 20
    assert m["height"] == 10
    assert len(m["tiles"]) == 200
    # Perimeter should be walls
    assert m["tiles"][0] == "#"
    assert m["tiles"][19] == "#"
    # Interior should be floor
    assert m["tiles"][21] == "."
    # Should have exits
    assert len(m["exits"]) == 4
    # Should have spawn
    assert "x" in m["spawn"]


def test_validate_room_map():
    assert _validate_room_map({"tiles": ["." for _ in range(200)], "width": 20, "height": 10})
    assert not _validate_room_map({"tiles": ["." for _ in range(5)], "width": 5, "height": 1})
    assert not _validate_room_map({"no_tiles": True})
    assert not _validate_room_map("not a dict")
