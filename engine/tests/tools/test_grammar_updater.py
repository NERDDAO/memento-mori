"""Tests for the generalizable grammar/table updater tool."""
import json
import os
import pytest
import shutil
from pathlib import Path

from memento.tools.grammar_updater import update_grammar, _resolve_path, _get_nested, _set_nested


@pytest.fixture
def tmp_grammar_dir(tmp_path):
    """Create a temporary grammar dir with test files."""
    grammars = tmp_path / "grammars"
    grammars.mkdir()
    tables = tmp_path / "tables"
    tables.mkdir()

    # Write a test grammar
    (grammars / "test_names.json").write_text(json.dumps({
        "first": ["Alice", "Bob"],
        "last": ["Smith", "Jones"],
    }))

    # Write a test table
    (tables / "test_affixes.json").write_text(json.dumps({
        "prefixes": {
            "common": ["Worn", "Old"],
            "rare": ["Enchanted"],
        }
    }))

    return tmp_path


def test_resolve_path(tmp_grammar_dir):
    path = _resolve_path("grammars/test_names", base_dir=tmp_grammar_dir)
    assert path.exists()
    assert path.name == "test_names.json"


def test_get_nested():
    data = {"a": {"b": ["x", "y"]}}
    assert _get_nested(data, "a.b") == ["x", "y"]
    assert _get_nested(data, "a") == {"b": ["x", "y"]}


def test_set_nested_append_to_list():
    data = {"a": {"b": ["x"]}}
    _set_nested(data, "a.b", "z", mode="append")
    assert data["a"]["b"] == ["x", "z"]


def test_set_nested_set_key():
    data = {"a": {}}
    _set_nested(data, "a.new_key", {"foo": "bar"}, mode="set")
    assert data["a"]["new_key"] == {"foo": "bar"}


def test_update_grammar_appends_to_array(tmp_grammar_dir):
    result = update_grammar.run(
        file_path="grammars/test_names",
        key_path="first",
        value="Charlie",
        _base_dir=str(tmp_grammar_dir),
    )
    assert "added" in result.lower() or "updated" in result.lower()

    # Verify file was updated
    data = json.loads((tmp_grammar_dir / "grammars" / "test_names.json").read_text())
    assert "Charlie" in data["first"]
    # Original values preserved
    assert "Alice" in data["first"]
    assert "Bob" in data["first"]


def test_update_grammar_no_duplicates(tmp_grammar_dir):
    update_grammar.run(
        file_path="grammars/test_names",
        key_path="first",
        value="Alice",  # already exists
        _base_dir=str(tmp_grammar_dir),
    )
    data = json.loads((tmp_grammar_dir / "grammars" / "test_names.json").read_text())
    assert data["first"].count("Alice") == 1


def test_update_grammar_nested_key(tmp_grammar_dir):
    result = update_grammar.run(
        file_path="tables/test_affixes",
        key_path="prefixes.rare",
        value="Hollowed",
        _base_dir=str(tmp_grammar_dir),
    )
    data = json.loads((tmp_grammar_dir / "tables" / "test_affixes.json").read_text())
    assert "Hollowed" in data["prefixes"]["rare"]


def test_update_grammar_set_new_key(tmp_grammar_dir):
    result = update_grammar.run(
        file_path="tables/test_affixes",
        key_path="prefixes.legendary",
        value=json.dumps(["Godslayer", "Eternal"]),
        mode="set",
        _base_dir=str(tmp_grammar_dir),
    )
    data = json.loads((tmp_grammar_dir / "tables" / "test_affixes.json").read_text())
    assert data["prefixes"]["legendary"] == ["Godslayer", "Eternal"]
