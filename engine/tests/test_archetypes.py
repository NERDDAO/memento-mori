"""Tests for archetype configuration."""

from memento.config.archetypes import load_archetypes, get_archetype, list_archetypes


def test_load_archetypes():
    archetypes = load_archetypes()
    assert isinstance(archetypes, dict)
    assert len(archetypes) >= 4
    assert "warrior" in archetypes
    assert "rogue" in archetypes
    assert "mage" in archetypes
    assert "ranger" in archetypes


def test_warrior_archetype():
    arch = get_archetype("warrior")
    assert arch["stats"]["health"] == 120
    assert "swordsmanship" in arch["skills"]
    assert arch["skills"]["swordsmanship"] == 2
    assert len(arch["starting_items"]) >= 2


def test_mage_archetype():
    arch = get_archetype("mage")
    assert arch["stats"]["health"] == 60
    assert "spellcraft" in arch["skills"]
    assert arch["skills"]["spellcraft"] == 3


def test_unknown_archetype():
    arch = get_archetype("druid")
    assert arch == {}


def test_list_archetypes():
    archetypes = list_archetypes()
    assert len(archetypes) >= 4
    names = [a["name"] for a in archetypes]
    assert "warrior" in names
    assert "ranger" in names


def test_archetype_has_starting_items():
    for arch in list_archetypes():
        assert "starting_items" in arch, f"{arch['name']} missing starting_items"
        for item in arch["starting_items"]:
            assert "name" in item, f"Item in {arch['name']} missing name"
            assert "labels" in item, f"Item in {arch['name']} missing labels"
