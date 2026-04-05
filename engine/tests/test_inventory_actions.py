"""Unit tests for inventory_actions — mocked Bonfires client + chain."""

import json
from unittest.mock import patch, MagicMock, call

import pytest

from memento.inventory_actions import (
    equip, unequip, drop, use, pickup, InventoryError,
)


def _item_entity(uuid, name, labels=None, **meta):
    return {
        "uuid": uuid,
        "name": name,
        "labels": labels or ["Item"],
        "summary": json.dumps(meta) if meta else "",
    }


def _carries_edge(target_uuid, target_name, expired_at=None, edge_uuid=None):
    edge = {"target": {"uuid": target_uuid, "name": target_name}}
    if expired_at:
        edge["expired_at"] = expired_at
    if edge_uuid:
        edge["uuid"] = edge_uuid
    return edge


def _located_in_edge(target_uuid, target_name, edge_uuid=None):
    edge = {"target": {"uuid": target_uuid, "name": target_name}}
    if edge_uuid:
        edge["uuid"] = edge_uuid
    return edge


def _mock_client_with_inventory(edges, entities, located_edges=None):
    """Build mock client that returns appropriate edges per query."""
    client = MagicMock()

    def get_edges(uuid, direction="outgoing", edge_type=None):
        if edge_type == "CARRIES":
            return edges
        if edge_type == "LOCATED_IN":
            return located_edges or []
        return []

    client.kg.get_edges.side_effect = get_edges
    client.kg.get_entity.side_effect = lambda uid: entities.get(uid, {
        "uuid": uid, "name": "Unknown", "labels": ["Item"], "summary": "",
    })
    client.kg.create_entity.return_value = "new-split-uuid"
    client.kg.create_edge.return_value = {"status": "ok"}
    client.kg.update_entity.return_value = {"status": "ok"}
    client.kg.update_edge.return_value = {"status": "ok"}
    return client


# ── Equip ──


def test_equip_item_to_slot():
    edges = [_carries_edge("sword-1", "Sword")]
    entities = {
        "sword-1": _item_entity("sword-1", "Sword", ["Item", "Weapon"],
                                rarity="rare", slot_type="weapon", equipped=False),
    }
    mock = _mock_client_with_inventory(edges, entities)
    with patch("memento.inventory_actions.get_client", return_value=mock), \
         patch("memento.inventory_manifest.get_client", return_value=mock):
        equip("player-1", "sword-1", "weapon")
    # Should update entity to set equipped=True
    mock.kg.update_entity.assert_called()
    update_call = mock.kg.update_entity.call_args
    # update_entity(uuid, name, labels, summary_json)
    updated_meta = json.loads(update_call[0][3])
    assert updated_meta["equipped"] is True


def test_equip_wrong_slot_type_raises():
    edges = [_carries_edge("sword-1", "Sword")]
    entities = {
        "sword-1": _item_entity("sword-1", "Sword", ["Item", "Weapon"],
                                slot_type="weapon", equipped=False),
    }
    mock = _mock_client_with_inventory(edges, entities)
    with patch("memento.inventory_actions.get_client", return_value=mock), \
         patch("memento.inventory_manifest.get_client", return_value=mock):
        with pytest.raises(InventoryError, match="Cannot equip"):
            equip("player-1", "sword-1", "armor")


def test_equip_invalid_slot_raises():
    with pytest.raises(InventoryError, match="Invalid slot"):
        equip("player-1", "sword-1", "head")


def test_equip_item_not_in_inventory_raises():
    mock = _mock_client_with_inventory([], {})
    with patch("memento.inventory_actions.get_client", return_value=mock), \
         patch("memento.inventory_manifest.get_client", return_value=mock):
        with pytest.raises(InventoryError, match="not in inventory"):
            equip("player-1", "missing-id", "weapon")


# ── Unequip ──


def test_unequip_item():
    edges = [_carries_edge("sword-1", "Sword")]
    entities = {
        "sword-1": _item_entity("sword-1", "Sword", ["Item", "Weapon"],
                                slot_type="weapon", equipped=True),
    }
    mock = _mock_client_with_inventory(edges, entities)
    with patch("memento.inventory_actions.get_client", return_value=mock), \
         patch("memento.inventory_manifest.get_client", return_value=mock):
        unequip("player-1", "weapon")
    mock.kg.update_entity.assert_called()
    update_call = mock.kg.update_entity.call_args
    # update_entity(uuid, name, labels, summary_json)
    updated_meta = json.loads(update_call[0][3])
    assert updated_meta["equipped"] is False


def test_unequip_empty_slot_raises():
    mock = _mock_client_with_inventory([], {})
    with patch("memento.inventory_actions.get_client", return_value=mock), \
         patch("memento.inventory_manifest.get_client", return_value=mock):
        with pytest.raises(InventoryError, match="No item equipped"):
            unequip("player-1", "weapon")


# ── Drop ──


@patch("memento.inventory_actions._chain")
def test_drop_item(mock_chain):
    edges = [_carries_edge("sword-1", "Sword", edge_uuid="edge-1")]
    entities = {
        "sword-1": _item_entity("sword-1", "Sword", ["Item", "Weapon"],
                                slot_type="weapon", equipped=False),
    }
    mock = _mock_client_with_inventory(edges, entities)
    with patch("memento.inventory_actions.get_client", return_value=mock), \
         patch("memento.inventory_manifest.get_client", return_value=mock):
        drop("player-1", "sword-1", "room-1")
    # Chain should be called
    mock_chain.drop_item.assert_called_once_with("sword-1", "room-1")
    # CARRIES edge should be expired
    mock.kg.update_edge.assert_called()
    # LOCATED_IN edge should be created
    mock.kg.create_edge.assert_called()


@patch("memento.inventory_actions._chain")
def test_drop_quest_item_raises(mock_chain):
    edges = [_carries_edge("journal-1", "Journal")]
    entities = {
        "journal-1": _item_entity("journal-1", "Journal", ["Item"],
                                  is_quest_item=True),
    }
    mock = _mock_client_with_inventory(edges, entities)
    with patch("memento.inventory_actions.get_client", return_value=mock), \
         patch("memento.inventory_manifest.get_client", return_value=mock):
        with pytest.raises(InventoryError, match="quest item"):
            drop("player-1", "journal-1", "room-1")
    mock_chain.drop_item.assert_not_called()


# ── Use ──


@patch("memento.inventory_actions._chain")
def test_use_consumable(mock_chain):
    edges = [_carries_edge("potion-1", "Health Potion", edge_uuid="edge-1")]
    entities = {
        "potion-1": _item_entity("potion-1", "Health Potion", ["Item", "Consumable"],
                                 is_consumable=True, effects=["Restores 20 HP"],
                                 quantity=1),
        "player-1": {"uuid": "player-1", "name": "Hero", "labels": ["Player"],
                     "summary": json.dumps({"health": 50, "max_health": 100})},
    }
    mock = _mock_client_with_inventory(edges, entities)
    with patch("memento.inventory_actions.get_client", return_value=mock), \
         patch("memento.inventory_manifest.get_client", return_value=mock):
        use("player-1", "potion-1")
    # Should expire CARRIES (quantity was 1)
    mock.kg.update_edge.assert_called()
    # Should update player health
    player_updates = [c for c in mock.kg.update_entity.call_args_list
                      if c[0][0] == "player-1"]
    assert len(player_updates) > 0
    # update_entity(uuid, name, labels, summary_json)
    healed_meta = json.loads(player_updates[0][0][3])
    assert healed_meta["health"] == 70  # 50 + 20


@patch("memento.inventory_actions._chain")
def test_use_non_consumable_raises(mock_chain):
    edges = [_carries_edge("sword-1", "Sword")]
    entities = {
        "sword-1": _item_entity("sword-1", "Sword", ["Item", "Weapon"],
                                is_consumable=False),
    }
    mock = _mock_client_with_inventory(edges, entities)
    with patch("memento.inventory_actions.get_client", return_value=mock), \
         patch("memento.inventory_manifest.get_client", return_value=mock):
        with pytest.raises(InventoryError, match="not consumable"):
            use("player-1", "sword-1")


@patch("memento.inventory_actions._chain")
def test_use_decrements_stack(mock_chain):
    edges = [_carries_edge("potion-1", "Health Potion")]
    entities = {
        "potion-1": _item_entity("potion-1", "Health Potion", ["Item", "Consumable"],
                                 is_consumable=True, stackable=True, quantity=3),
        "player-1": {"uuid": "player-1", "name": "Hero", "labels": ["Player"],
                     "summary": json.dumps({"health": 100, "max_health": 100})},
    }
    mock = _mock_client_with_inventory(edges, entities)
    with patch("memento.inventory_actions.get_client", return_value=mock), \
         patch("memento.inventory_manifest.get_client", return_value=mock):
        use("player-1", "potion-1")
    # Should NOT expire CARRIES (quantity > 1)
    mock.kg.update_edge.assert_not_called()
    # Should update quantity to 2
    item_updates = [c for c in mock.kg.update_entity.call_args_list
                    if c[0][0] == "potion-1"]
    assert len(item_updates) > 0
    # update_entity(uuid, name, labels, summary_json)
    updated_meta = json.loads(item_updates[0][0][3])
    assert updated_meta["quantity"] == 2


# ── Pickup ──


@patch("memento.inventory_actions._chain")
def test_pickup_item(mock_chain):
    # Player inventory is empty
    player_edges = []
    # Item is on the ground
    located_edges = [_located_in_edge("room-1", "Tavern", edge_uuid="loc-edge-1")]
    entities = {
        "dagger-1": _item_entity("dagger-1", "Dagger", ["Item", "Weapon"],
                                 rarity="common", slot_type="weapon"),
    }
    mock = _mock_client_with_inventory(player_edges, entities, located_edges)
    with patch("memento.inventory_actions.get_client", return_value=mock), \
         patch("memento.inventory_manifest.get_client", return_value=mock):
        pickup("player-1", "dagger-1", "room-1")
    mock_chain.transfer_item.assert_called_once_with("dagger-1", "player-1")
    # LOCATED_IN edge expired
    mock.kg.update_edge.assert_called()
    # CARRIES edge created
    mock.kg.create_edge.assert_called()


@patch("memento.inventory_actions._chain")
def test_pickup_succeeds_when_entity_exists(mock_chain):
    """Pickup proceeds if KG entity exists, even without a matching LOCATED_IN edge."""
    located_edges = [_located_in_edge("other-room", "Other")]
    entities = {
        "dagger-1": _item_entity("dagger-1", "Dagger", ["Item"]),
    }
    mock = _mock_client_with_inventory([], entities, located_edges)
    with patch("memento.inventory_actions.get_client", return_value=mock), \
         patch("memento.inventory_manifest.get_client", return_value=mock):
        pickup("player-1", "dagger-1", "room-1")
    mock_chain.transfer_item.assert_called_once_with("dagger-1", "player-1")
    mock.kg.create_edge.assert_called()


@patch("memento.inventory_actions._chain")
def test_pickup_full_inventory_raises(mock_chain):
    # Fill inventory to capacity (10 items)
    player_edges = [_carries_edge(f"item-{i}", f"Item {i}") for i in range(10)]
    located_edges = [_located_in_edge("room-1", "Tavern")]
    entities = {
        f"item-{i}": _item_entity(f"item-{i}", f"Item {i}", ["Item"])
        for i in range(10)
    }
    entities["new-item"] = _item_entity("new-item", "New Item", ["Item"])
    mock = _mock_client_with_inventory(player_edges, entities, located_edges)
    with patch("memento.inventory_actions.get_client", return_value=mock), \
         patch("memento.inventory_manifest.get_client", return_value=mock):
        with pytest.raises(InventoryError, match="Inventory full"):
            pickup("player-1", "new-item", "room-1")


@patch("memento.inventory_actions._chain")
def test_pickup_stack_merge(mock_chain):
    """Picking up a stackable item that matches existing stack should merge."""
    player_edges = [_carries_edge("potion-existing", "Health Potion")]
    located_edges = [_located_in_edge("room-1", "Tavern", edge_uuid="loc-edge-1")]
    entities = {
        "potion-existing": _item_entity("potion-existing", "Health Potion",
                                        ["Item", "Consumable"],
                                        rarity="common", stackable=True,
                                        is_consumable=True, quantity=2),
        "potion-ground": _item_entity("potion-ground", "Health Potion",
                                      ["Item", "Consumable"],
                                      rarity="common", stackable=True,
                                      is_consumable=True, quantity=1),
    }
    mock = _mock_client_with_inventory(player_edges, entities, located_edges)
    with patch("memento.inventory_actions.get_client", return_value=mock), \
         patch("memento.inventory_manifest.get_client", return_value=mock):
        pickup("player-1", "potion-ground", "room-1")
    # Should update existing stack quantity (2 + 1 = 3)
    potion_updates = [c for c in mock.kg.update_entity.call_args_list
                      if c[0][0] == "potion-existing"]
    assert len(potion_updates) > 0
    # update_entity(uuid, name, labels, summary_json)
    updated_meta = json.loads(potion_updates[0][0][3])
    assert updated_meta["quantity"] == 3
    # LOCATED_IN edge should be expired
    mock.kg.update_edge.assert_called()
