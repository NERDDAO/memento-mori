"""Unit tests for inventory_manifest — mocked Bonfires client."""

from unittest.mock import patch, MagicMock

from memento.inventory_manifest import (
    get_inventory_manifest,
    get_inventory_as_state_update,
    reconcile_with_chain,
    EQUIPMENT_SLOTS,
)


def _make_mock_client(edges=None, entities=None):
    """Build a mock Bonfires client with configurable edges and entities."""
    client = MagicMock()
    client.kg.get_edges.return_value = edges or []
    _entities = entities or {}
    client.kg.get_entity.side_effect = lambda uuid: _entities.get(uuid, {
        "uuid": uuid, "name": "Unknown", "labels": ["Item"], "summary": "",
    })
    return client


def _item_entity(uuid, name, labels=None, **meta):
    """Build a mock KG item entity."""
    import json
    summary = json.dumps(meta) if meta else ""
    return {
        "uuid": uuid,
        "name": name,
        "labels": labels or ["Item"],
        "summary": summary,
    }


def _carries_edge(target_uuid, target_name, expired_at=None):
    """Build a mock CARRIES edge."""
    edge = {
        "target": {"uuid": target_uuid, "name": target_name},
    }
    if expired_at:
        edge["expired_at"] = expired_at
    return edge


# ── get_inventory_manifest ──


def test_empty_inventory():
    mock = _make_mock_client(edges=[])
    with patch("memento.inventory_manifest.get_client", return_value=mock):
        result = get_inventory_manifest("player-1")
    assert result["count"] == 0
    assert result["backpack"] == []
    assert all(v is None for v in result["equipped"].values())


def test_single_unequipped_item():
    edges = [_carries_edge("sword-1", "Iron Sword")]
    entities = {
        "sword-1": _item_entity("sword-1", "Iron Sword", ["Item", "Weapon"],
                                rarity="rare", slot_type="weapon", equipped=False),
    }
    mock = _make_mock_client(edges=edges, entities=entities)
    with patch("memento.inventory_manifest.get_client", return_value=mock):
        result = get_inventory_manifest("player-1")
    assert len(result["backpack"]) == 1
    assert result["backpack"][0]["name"] == "Iron Sword"
    assert result["backpack"][0]["rarity"] == "rare"
    assert result["equipped"]["weapon"] is None


def test_equipped_item_goes_to_slot():
    edges = [_carries_edge("sword-1", "Iron Sword")]
    entities = {
        "sword-1": _item_entity("sword-1", "Iron Sword", ["Item", "Weapon"],
                                rarity="rare", slot_type="weapon", equipped=True),
    }
    mock = _make_mock_client(edges=edges, entities=entities)
    with patch("memento.inventory_manifest.get_client", return_value=mock):
        result = get_inventory_manifest("player-1")
    assert result["equipped"]["weapon"] is not None
    assert result["equipped"]["weapon"]["name"] == "Iron Sword"
    assert len(result["backpack"]) == 0


def test_expired_edges_filtered():
    edges = [
        _carries_edge("old-sword", "Old Sword", expired_at="2026-01-01T00:00:00Z"),
        _carries_edge("new-sword", "New Sword"),
    ]
    entities = {
        "old-sword": _item_entity("old-sword", "Old Sword", ["Item", "Weapon"],
                                  slot_type="weapon"),
        "new-sword": _item_entity("new-sword", "New Sword", ["Item", "Weapon"],
                                  slot_type="weapon"),
    }
    mock = _make_mock_client(edges=edges, entities=entities)
    with patch("memento.inventory_manifest.get_client", return_value=mock):
        result = get_inventory_manifest("player-1")
    # Only the unexpired edge should appear
    all_items = result["backpack"] + [v for v in result["equipped"].values() if v]
    assert len(all_items) == 1
    assert all_items[0]["name"] == "New Sword"


def test_invalid_at_also_filters():
    edges = [{"target": {"uuid": "x", "name": "X"}, "invalid_at": "2026-01-01T00:00:00Z"}]
    entities = {"x": _item_entity("x", "X", ["Item"])}
    mock = _make_mock_client(edges=edges, entities=entities)
    with patch("memento.inventory_manifest.get_client", return_value=mock):
        result = get_inventory_manifest("player-1")
    assert result["count"] == 0


def test_mixed_equipped_and_backpack():
    edges = [
        _carries_edge("sword-1", "Sword"),
        _carries_edge("armor-1", "Plate"),
        _carries_edge("potion-1", "Health Potion"),
    ]
    entities = {
        "sword-1": _item_entity("sword-1", "Sword", ["Item", "Weapon"],
                                slot_type="weapon", equipped=True, rarity="rare"),
        "armor-1": _item_entity("armor-1", "Plate", ["Item", "Armor"],
                                slot_type="armor", equipped=True, rarity="uncommon"),
        "potion-1": _item_entity("potion-1", "Health Potion", ["Item", "Consumable"],
                                 is_consumable=True, stackable=True),
    }
    mock = _make_mock_client(edges=edges, entities=entities)
    with patch("memento.inventory_manifest.get_client", return_value=mock):
        result = get_inventory_manifest("player-1")
    assert result["equipped"]["weapon"]["name"] == "Sword"
    assert result["equipped"]["armor"]["name"] == "Plate"
    assert result["equipped"]["accessory"] is None
    assert result["equipped"]["ring"] is None
    assert len(result["backpack"]) == 1
    assert result["backpack"][0]["is_consumable"] is True
    assert result["backpack"][0]["stackable"] is True
    assert result["count"] == 3


def test_effects_parsed_from_string():
    edges = [_carries_edge("ring-1", "Ring of Fire")]
    entities = {
        "ring-1": _item_entity("ring-1", "Ring of Fire", ["Item"],
                               slot_type="ring", effects='["+1 fire resistance"]'),
    }
    mock = _make_mock_client(edges=edges, entities=entities)
    with patch("memento.inventory_manifest.get_client", return_value=mock):
        result = get_inventory_manifest("player-1")
    item = result["backpack"][0]
    assert item["effects"] == ["+1 fire resistance"]


def test_kg_failure_returns_empty():
    mock = _make_mock_client()
    mock.kg.get_edges.side_effect = Exception("KG down")
    with patch("memento.inventory_manifest.get_client", return_value=mock):
        result = get_inventory_manifest("player-1")
    assert result["count"] == 0
    assert result["backpack"] == []


# ── get_inventory_as_state_update ──


def test_state_update_format():
    edges = [
        _carries_edge("sword-1", "Sword"),
        _carries_edge("potion-1", "Potion"),
    ]
    entities = {
        "sword-1": _item_entity("sword-1", "Sword", ["Item", "Weapon"],
                                slot_type="weapon", equipped=True, rarity="rare"),
        "potion-1": _item_entity("potion-1", "Potion", ["Item", "Consumable"],
                                 is_consumable=True),
    }
    mock = _make_mock_client(edges=edges, entities=entities)
    with patch("memento.inventory_manifest.get_client", return_value=mock):
        items = get_inventory_as_state_update("player-1")
    assert len(items) == 2
    sword = next(i for i in items if i["name"] == "Sword")
    assert sword["equipped"] is True
    assert sword["id"] == "sword-1"
    assert sword["slot_type"] == "weapon"
    potion = next(i for i in items if i["name"] == "Potion")
    assert potion["equipped"] is False
    assert potion["is_consumable"] is True


# ── reconcile_with_chain ──


def test_reconcile_creates_missing_edges():
    """Chain has item, KG doesn't → create CARRIES edge."""
    mock = _make_mock_client(edges=[])  # KG has nothing
    chain_items = [{"id": "sword-1", "name": "Sword", "rarity": "common"}]
    with patch("memento.inventory_manifest.get_client", return_value=mock):
        reconcile_with_chain("player-1", chain_items)
    mock.kg.create_edge.assert_called_once()
    call_args = mock.kg.create_edge.call_args
    assert call_args[0][0] == "player-1"
    assert call_args[0][1] == "sword-1"
    assert call_args[0][2] == "CARRIES"


def test_reconcile_expires_orphaned_edges():
    """KG has item, chain doesn't → expire CARRIES edge."""
    edges = [_carries_edge("old-item", "Old Item")]
    edges[0]["uuid"] = "edge-uuid-1"
    entities = {
        "old-item": _item_entity("old-item", "Old Item", ["Item"]),
    }
    mock = _make_mock_client(edges=edges, entities=entities)
    chain_items = []  # Chain has nothing

    with patch("memento.inventory_manifest.get_client", return_value=mock):
        kg_manifest = get_inventory_manifest("player-1")
        reconcile_with_chain("player-1", chain_items, kg_manifest)

    mock.kg.update_edge.assert_called_once()
    call_args = mock.kg.update_edge.call_args
    assert call_args[0][0] == "edge-uuid-1"
    assert "expired_at" in call_args[0][1]


def test_reconcile_noop_when_in_sync():
    """Chain and KG match → no changes."""
    edges = [_carries_edge("sword-1", "Sword")]
    entities = {
        "sword-1": _item_entity("sword-1", "Sword", ["Item", "Weapon"]),
    }
    mock = _make_mock_client(edges=edges, entities=entities)
    chain_items = [{"id": "sword-1", "name": "Sword"}]

    with patch("memento.inventory_manifest.get_client", return_value=mock):
        kg_manifest = get_inventory_manifest("player-1")
        reconcile_with_chain("player-1", chain_items, kg_manifest)

    mock.kg.create_edge.assert_not_called()
    mock.kg.update_edge.assert_not_called()
