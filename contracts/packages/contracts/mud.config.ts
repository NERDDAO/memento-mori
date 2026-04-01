import { defineWorld } from "@latticexyz/world";

export default defineWorld({
  namespace: "memento",
  enums: {
    EntityType: ["Character", "NPC", "Item", "Location", "Region", "Quest", "Faction"],
    EventType: ["CombatOutcome", "QuestComplete", "NPCDeath", "Discovery", "FactionChange", "Death", "GameEvent"],
  },
  tables: {
    Characters: {
      schema: {
        id: "bytes32",
        wallet: "address",
        entityType: "EntityType",
        level: "uint32",
        alive: "bool",
        createdAt: "uint256",
        name: "string",
      },
      key: ["id"],
    },
    Deaths: {
      schema: {
        id: "bytes32",
        characterId: "bytes32",
        level: "uint32",
        tick: "uint256",
        timestamp: "uint256",
        cause: "string",
        location: "string",
      },
      key: ["id"],
    },
    Items: {
      schema: {
        id: "bytes32",
        ownerId: "bytes32",
        locationId: "bytes32",
        name: "string",
        rarity: "string",
      },
      key: ["id"],
    },
    Locations: {
      schema: {
        id: "bytes32",
        discoveredBy: "address",
        discoveredAt: "uint256",
        name: "string",
        region: "string",
      },
      key: ["id"],
    },
    WorldEvents: {
      schema: {
        id: "bytes32",
        eventType: "EventType",
        tick: "uint256",
        timestamp: "uint256",
        actors: "string",
        location: "string",
        summary: "string",
      },
      key: ["id"],
    },
    Episodes: {
      schema: {
        id: "bytes32",
        tick: "uint256",
        timestamp: "uint256",
        name: "string",
        summary: "string",
        entities: "string",
        edges: "string",
      },
      key: ["id"],
    },
    Reputation: {
      schema: {
        wallet: "address",
        factionId: "bytes32",
        standing: "int32",
      },
      key: ["wallet", "factionId"],
    },
  },
});
