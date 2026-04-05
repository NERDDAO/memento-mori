// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { MudTest } from "@latticexyz/world/test/MudTest.t.sol";
import { IWorld } from "../src/codegen/world/IWorld.sol";
import {
  Characters,
  Deaths,
  Items,
  Position,
  PositionData,
  EntitiesAtPosition,
  Terrain
} from "../src/codegen/index.sol";
import { EntityType } from "../src/codegen/common.sol";

contract MementoTest is MudTest {
  IWorld world;

  function setUp() public override {
    super.setUp();
    world = IWorld(worldAddress);
  }

  // ---------------------------------------------------------------------------
  // CharacterSystem
  // ---------------------------------------------------------------------------

  function testRegisterCharacter() public {
    bytes32 id = bytes32(uint256(1));
    world.memento__registerCharacter(id, "Kael", address(0xBEEF), EntityType.Character);

    assertEq(Characters.getName(id), "Kael");
    assertTrue(Characters.getAlive(id));
    assertEq(Characters.getLevel(id), 1);
    assertEq(Characters.getWallet(id), address(0xBEEF));
    assertEq(uint8(Characters.getEntityType(id)), uint8(EntityType.Character));
    assertGt(Characters.getCreatedAt(id), 0);
  }

  function testKillCharacter() public {
    bytes32 charId = bytes32(uint256(2));
    world.memento__registerCharacter(charId, "Morwen", address(0xCAFE), EntityType.Character);

    world.memento__killCharacter(charId, "eaten by dragon", "Dragon's Lair", 42);

    assertFalse(Characters.getAlive(charId));

    bytes32 deathId = keccak256(abi.encodePacked(charId, block.timestamp));
    assertEq(Deaths.getCharacterId(deathId), charId);
    assertEq(Deaths.getLevel(deathId), 1);
    assertEq(Deaths.getTick(deathId), 42);
    assertEq(Deaths.getCause(deathId), "eaten by dragon");
    assertEq(Deaths.getLocation(deathId), "Dragon's Lair");
  }

  function testLevelUp() public {
    bytes32 id = bytes32(uint256(3));
    world.memento__registerCharacter(id, "Thane", address(0xDEAD), EntityType.Character);
    assertEq(Characters.getLevel(id), 1);

    world.memento__levelUp(id, 5);
    assertEq(Characters.getLevel(id), 5);
  }

  // ---------------------------------------------------------------------------
  // ItemSystem
  // ---------------------------------------------------------------------------

  function testRegisterAndTransferItem() public {
    bytes32 itemId = bytes32(uint256(10));
    bytes32 locationId = bytes32(uint256(100));
    bytes32 ownerId = bytes32(uint256(200));

    world.memento__registerItem(itemId, "Rusty Sword", "common", bytes32(0), locationId);

    assertEq(Items.getName(itemId), "Rusty Sword");
    assertEq(Items.getRarity(itemId), "common");
    assertEq(Items.getLocationId(itemId), locationId);
    assertEq(Items.getOwnerId(itemId), bytes32(0));

    world.memento__transferItem(itemId, ownerId);

    assertEq(Items.getOwnerId(itemId), ownerId);
    assertEq(Items.getLocationId(itemId), bytes32(0));
  }

  function testDropItem() public {
    bytes32 itemId = bytes32(uint256(11));
    bytes32 ownerId = bytes32(uint256(201));
    bytes32 locationId = bytes32(uint256(101));

    world.memento__registerItem(itemId, "Health Potion", "rare", ownerId, bytes32(0));
    assertEq(Items.getOwnerId(itemId), ownerId);

    world.memento__dropItem(itemId, locationId);

    assertEq(Items.getOwnerId(itemId), bytes32(0));
    assertEq(Items.getLocationId(itemId), locationId);
  }

  // ---------------------------------------------------------------------------
  // PositionSystem
  // ---------------------------------------------------------------------------

  function testSetAndMovePosition() public {
    bytes32 entityId = bytes32(uint256(60));
    bytes32 locationId = bytes32(uint256(61));

    // Set up terrain first (3x3 all walkable floor)
    bytes memory terrain = new bytes(9);
    for (uint256 i = 0; i < 9; i++) {
      terrain[i] = bytes1(uint8(1)); // TILE_FLOOR
    }
    world.memento__setTerrain(locationId, 3, 3, terrain);

    // Set position
    world.memento__setPosition(entityId, locationId, 1, 1);

    PositionData memory pos = Position.get(entityId);
    assertEq(pos.locationId, locationId);
    assertEq(pos.x, 1);
    assertEq(pos.y, 1);

    // Check reverse index
    bytes32[] memory entities = EntitiesAtPosition.getEntities(locationId, 1, 1);
    assertEq(entities.length, 1);
    assertEq(entities[0], entityId);

    // Move
    world.memento__moveEntity(entityId, 2, 2);

    pos = Position.get(entityId);
    assertEq(pos.x, 2);
    assertEq(pos.y, 2);

    // Old tile should be empty
    entities = EntitiesAtPosition.getEntities(locationId, 1, 1);
    assertEq(entities.length, 0);

    // New tile should have the entity
    entities = EntitiesAtPosition.getEntities(locationId, 2, 2);
    assertEq(entities.length, 1);
    assertEq(entities[0], entityId);
  }

  // ---------------------------------------------------------------------------
  // TerrainSystem
  // ---------------------------------------------------------------------------

  function testSetTerrain() public {
    bytes32 locationId = bytes32(uint256(70));

    bytes memory terrain = new bytes(6); // 3x2
    terrain[0] = bytes1(uint8(2)); // wall
    terrain[1] = bytes1(uint8(1)); // floor
    terrain[2] = bytes1(uint8(3)); // exit
    terrain[3] = bytes1(uint8(1)); // floor
    terrain[4] = bytes1(uint8(4)); // water
    terrain[5] = bytes1(uint8(1)); // floor

    world.memento__setTerrain(locationId, 3, 2, terrain);

    assertEq(Terrain.getWidth(locationId), 3);
    assertEq(Terrain.getHeight(locationId), 2);

    // Walkability checks
    assertTrue(world.memento__isWalkable(locationId, 1, 0));  // floor
    assertTrue(world.memento__isWalkable(locationId, 2, 0));  // exit
    assertTrue(world.memento__isWalkable(locationId, 1, 1));  // water
    assertFalse(world.memento__isWalkable(locationId, 0, 0)); // wall
    assertFalse(world.memento__isWalkable(locationId, -1, 0)); // out of bounds
  }
}
