"""End-to-end smoke test for the art department pipeline.

Tests the full flow: procgen → crew construction → output parsing.
Does NOT run actual LLM calls — mocks the crew kickoff.
"""
import base64
import io
from unittest.mock import patch, MagicMock

from PIL import Image

from memento.flows.art_gen import generate_entity_art
from memento.tools.procgen.wfc import generate_terrain_scaffold
from memento.tools.procgen.sprite_gen import generate_sprite
from memento.tools.procgen.palette import select_palette
from memento.tools.procgen.templates import select_template


def test_full_terrain_pipeline():
    """WFC scaffold → palette → dimensions correct."""
    scaffold = generate_terrain_scaffold("crypt", width=20, height=10, seed=42)
    lines = scaffold.split("\n")
    assert len(lines) == 10
    assert all(len(line) == 20 for line in lines)

    palette = select_palette("crypt", "dark")
    assert len(palette.primary) == 3


def test_full_sprite_pipeline():
    """Template → palette → sprite gen produces valid base64."""
    template = select_template(["NPC"])
    palette = select_palette("crypt")
    sprite_b64 = generate_sprite(template, palette, seed=42)

    img_bytes = base64.b64decode(sprite_b64)
    img = Image.open(io.BytesIO(img_bytes))
    assert img.size == (template.size, template.size)
    assert img.mode == "RGBA"


def test_item_sprite_pipeline():
    """Item template → small icon sprite."""
    template = select_template(["Weapon", "Item"])
    assert template.size == 8
    palette = select_palette("default")
    sprite_b64 = generate_sprite(template, palette, seed=42)

    img = Image.open(io.BytesIO(base64.b64decode(sprite_b64)))
    assert img.size == (8, 8)


@patch("memento.flows.art_gen._get_kg_client")
@patch("memento.flows.art_gen.make_cartographer_crew")
def test_dispatcher_location_e2e(mock_crew_fn, mock_kg):
    """Dispatcher routes location to cartographer and persists."""
    mock_crew = MagicMock()
    art = "\n".join(["#" * 35] + ["#" + "." * 33 + "#"] * 18 + ["#" * 35])
    mock_crew.kickoff.return_value = MagicMock(raw=art)
    mock_crew_fn.return_value = mock_crew
    mock_client = MagicMock()
    mock_kg.return_value = mock_client

    generate_entity_art("uuid-1", "Dark Crypt", "location", "A dark crypt.", ["Location"], "crypt", "dark")

    mock_crew_fn.assert_called_once()
    assert mock_client.kg.update_entity.called
    call_args = mock_client.kg.update_entity.call_args
    assert "scene_art" in str(call_args)


@patch("memento.flows.art_gen._get_kg_client")
@patch("memento.flows.art_gen.make_portraitist_crew")
def test_dispatcher_npc_e2e(mock_crew_fn, mock_kg):
    """Dispatcher routes NPC to portraitist and persists."""
    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = MagicMock(
        raw='{"sprite_b64": "iVBORtest", "width": 32, "height": 32}'
    )
    mock_crew_fn.return_value = mock_crew
    mock_client = MagicMock()
    mock_kg.return_value = mock_client

    generate_entity_art("uuid-2", "Skeleton Guard", "npc", "A skeletal warrior.", ["NPC"], "crypt", "dark")

    mock_crew_fn.assert_called_once()
    assert mock_client.kg.update_entity.called
    call_args = mock_client.kg.update_entity.call_args
    assert "portrait_sprite" in str(call_args)


@patch("memento.flows.art_gen._get_kg_client")
@patch("memento.flows.art_gen.make_portraitist_crew")
def test_dispatcher_item_e2e(mock_crew_fn, mock_kg):
    """Dispatcher routes item to portraitist in icon mode and persists."""
    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = MagicMock(
        raw='{"sprite_b64": "iVBORtest", "width": 8, "height": 8}'
    )
    mock_crew_fn.return_value = mock_crew
    mock_client = MagicMock()
    mock_kg.return_value = mock_client

    generate_entity_art("uuid-3", "Iron Sword", "item", "A rusty blade.", ["Weapon", "Item"], "default", "dark")

    mock_crew_fn.assert_called_once()
    # Verify icon_mode=True was passed
    call_kwargs = mock_crew_fn.call_args
    assert call_kwargs[1].get("icon_mode") is True or (len(call_kwargs[0]) > 6 and call_kwargs[0][6] is True)
    assert mock_client.kg.update_entity.called
    assert "icon_sprite" in str(mock_client.kg.update_entity.call_args)
