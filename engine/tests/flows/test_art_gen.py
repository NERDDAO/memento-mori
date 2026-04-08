"""Tests for the art generation dispatcher."""
import pytest
from unittest.mock import patch, MagicMock

from memento.flows.art_gen import generate_entity_art, _parse_scene_art, _parse_sprite_result


def test_parse_scene_art_extracts_lines():
    raw = "###\n...\n###"
    art, w, h = _parse_scene_art(raw, expected_w=3, expected_h=3)
    assert art == "###\n...\n###"
    assert w == 3
    assert h == 3


def test_parse_scene_art_strips_commentary():
    raw = "Here is the art:\n```\n###\n...\n###\n```\nHope you like it!"
    art, w, h = _parse_scene_art(raw, expected_w=3, expected_h=3)
    assert art == "###\n...\n###"
    assert h == 3


def test_parse_sprite_result_extracts_json():
    raw = '{"sprite_b64": "abc123", "width": 16, "height": 16}'
    result = _parse_sprite_result(raw)
    assert result["sprite_b64"] == "abc123"
    assert result["width"] == 16


def test_parse_sprite_result_from_commentary():
    raw = 'Here is the result:\n{"sprite_b64": "abc123", "width": 32, "height": 32}\nDone!'
    result = _parse_sprite_result(raw)
    assert result["sprite_b64"] == "abc123"


@patch("memento.flows.art_gen._get_kg_client")
@patch("memento.flows.art_gen.make_cartographer_crew")
def test_generate_entity_art_location(mock_crew_fn, mock_kg):
    mock_crew = MagicMock()
    art = "\n".join(["#" * 35] + ["#" + "." * 33 + "#"] * 18 + ["#" * 35])
    mock_crew.kickoff.return_value = MagicMock(raw=art)
    mock_crew_fn.return_value = mock_crew
    mock_client = MagicMock()
    mock_kg.return_value = mock_client

    generate_entity_art(
        entity_uid="test-uuid",
        name="Test Room",
        entity_type="location",
        description="A test room",
        labels=["Location"],
        biome="default",
    )

    mock_crew_fn.assert_called_once()
    mock_client.kg.update_entity.assert_called_once()
    call_args = mock_client.kg.update_entity.call_args
    assert "scene_art" in str(call_args)


@patch("memento.flows.art_gen._get_kg_client")
@patch("memento.flows.art_gen.make_portraitist_crew")
def test_generate_entity_art_npc(mock_crew_fn, mock_kg):
    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = MagicMock(
        raw='{"sprite_b64": "abc123", "width": 32, "height": 32}'
    )
    mock_crew_fn.return_value = mock_crew
    mock_client = MagicMock()
    mock_kg.return_value = mock_client

    generate_entity_art(
        entity_uid="test-uuid",
        name="Test NPC",
        entity_type="npc",
        description="A test character",
        labels=["NPC"],
        biome="crypt",
    )

    mock_crew_fn.assert_called_once()
    mock_client.kg.update_entity.assert_called_once()
    call_args = mock_client.kg.update_entity.call_args
    assert "portrait_sprite" in str(call_args)
