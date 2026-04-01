// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { MudTest } from "@latticexyz/world/test/MudTest.t.sol";
import { IWorld } from "../src/codegen/world/IWorld.sol";
import {
  Characters,
  Deaths,
  Items,
  Locations,
  WorldEvents,
  Episodes,
  Reputation
} from "../src/codegen/index.sol";
import { EntityType, EventType } from "../src/codegen/common.sol";

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

    // Kill
    world.memento__killCharacter(charId, "eaten by dragon", "Dragon's Lair", 42);

    // Character should be dead
    assertFalse(Characters.getAlive(charId));

    // Death record should exist
    bytes32 deathId = keccak256(abi.encodePacked(charId, block.timestamp));
    assertEq(Deaths.getCharacterId(deathId), charId);
    assertEq(Deaths.getLevel(deathId), 1);
    assertEq(Deaths.getTick(deathId), 42);
    assertEq(Deaths.getTimestamp(deathId), block.timestamp);
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

    // Register item at a location (no owner)
    world.memento__registerItem(itemId, "Rusty Sword", "common", bytes32(0), locationId);

    assertEq(Items.getName(itemId), "Rusty Sword");
    assertEq(Items.getRarity(itemId), "common");
    assertEq(Items.getLocationId(itemId), locationId);
    assertEq(Items.getOwnerId(itemId), bytes32(0));

    // Transfer to owner
    world.memento__transferItem(itemId, ownerId);

    assertEq(Items.getOwnerId(itemId), ownerId);
    assertEq(Items.getLocationId(itemId), bytes32(0)); // location cleared on transfer
  }

  function testDropItem() public {
    bytes32 itemId = bytes32(uint256(11));
    bytes32 ownerId = bytes32(uint256(201));
    bytes32 locationId = bytes32(uint256(101));

    // Register item with an owner
    world.memento__registerItem(itemId, "Health Potion", "rare", ownerId, bytes32(0));
    assertEq(Items.getOwnerId(itemId), ownerId);

    // Drop it
    world.memento__dropItem(itemId, locationId);

    assertEq(Items.getOwnerId(itemId), bytes32(0));
    assertEq(Items.getLocationId(itemId), locationId);
  }

  // ---------------------------------------------------------------------------
  // LocationSystem
  // ---------------------------------------------------------------------------

  function testRegisterAndDiscoverLocation() public {
    bytes32 locId = bytes32(uint256(20));
    address alice = address(0xA11CE);
    address bob = address(0xB0B);

    // Register with no discoverer
    world.memento__registerLocation(locId, "Crypt of Echoes", "Shadowfen", address(0));

    assertEq(Locations.getName(locId), "Crypt of Echoes");
    assertEq(Locations.getRegion(locId), "Shadowfen");
    assertEq(Locations.getDiscoveredBy(locId), address(0));

    // First discovery sets discoverer
    world.memento__discoverLocation(locId, alice);
    assertEq(Locations.getDiscoveredBy(locId), alice);
    uint256 discoveredAt = Locations.getDiscoveredAt(locId);
    assertGt(discoveredAt, 0);

    // Second discovery should NOT overwrite
    world.memento__discoverLocation(locId, bob);
    assertEq(Locations.getDiscoveredBy(locId), alice);
    assertEq(Locations.getDiscoveredAt(locId), discoveredAt);
  }

  // ---------------------------------------------------------------------------
  // EventSystem
  // ---------------------------------------------------------------------------

  function testRecordEvent() public {
    bytes32 eventId = bytes32(uint256(30));
    world.memento__recordEvent(
      eventId,
      EventType.CombatOutcome,
      "Kael,Morwen",
      "Arena",
      "Kael defeated Morwen in single combat",
      7
    );

    assertEq(uint8(WorldEvents.getEventType(eventId)), uint8(EventType.CombatOutcome));
    assertEq(WorldEvents.getTick(eventId), 7);
    assertEq(WorldEvents.getTimestamp(eventId), block.timestamp);
    assertEq(WorldEvents.getActors(eventId), "Kael,Morwen");
    assertEq(WorldEvents.getLocation(eventId), "Arena");
    assertEq(WorldEvents.getSummary(eventId), "Kael defeated Morwen in single combat");
  }

  // ---------------------------------------------------------------------------
  // EpisodeSystem
  // ---------------------------------------------------------------------------

  function testRecordEpisode() public {
    bytes32 epId = bytes32(uint256(40));
    string memory entities = '["Kael","Dragon"]';
    string memory edges = '["Kael->fought->Dragon"]';

    world.memento__recordEpisode(
      epId,
      "The Dragon's Demise",
      "Kael slew the ancient dragon",
      entities,
      edges,
      99
    );

    assertEq(Episodes.getTick(epId), 99);
    assertEq(Episodes.getTimestamp(epId), block.timestamp);
    assertEq(Episodes.getName(epId), "The Dragon's Demise");
    assertEq(Episodes.getSummary(epId), "Kael slew the ancient dragon");
    assertEq(Episodes.getEntities(epId), entities);
    assertEq(Episodes.getEdges(epId), edges);
  }

  // ---------------------------------------------------------------------------
  // ReputationSystem
  // ---------------------------------------------------------------------------

  function testReputation() public {
    address player = address(0xF00D);
    bytes32 factionId = bytes32(uint256(50));

    // Start at 0, add 25
    world.memento__updateReputation(player, factionId, 25);
    assertEq(Reputation.getStanding(player, factionId), 25);

    // Add 50 more -> 75
    world.memento__updateReputation(player, factionId, 50);
    assertEq(Reputation.getStanding(player, factionId), 75);

    // Try to exceed 100 -> should clamp at 100
    world.memento__updateReputation(player, factionId, 50);
    assertEq(Reputation.getStanding(player, factionId), 100);

    // Large negative to go below -100 -> should clamp at -100
    world.memento__updateReputation(player, factionId, -250);
    assertEq(Reputation.getStanding(player, factionId), -100);

    // Bring back toward zero
    world.memento__updateReputation(player, factionId, 100);
    assertEq(Reputation.getStanding(player, factionId), 0);
  }
}
