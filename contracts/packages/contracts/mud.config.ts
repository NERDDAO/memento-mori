import { defineWorld } from "@latticexyz/world";

export default defineWorld({
  namespace: "memento",
  enums: {
    EntityType: ["Character", "NPC", "Item", "Location", "Region", "Quest", "Faction"],
  },
  tables: {
    // --- Onchain (permanent, composable) ---
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

    // --- Epoch commitments (state root + IPFS pointer) ---
    Epochs: {
      schema: {
        id: "bytes32",
        stateRoot: "bytes32",
        tick: "uint256",
        timestamp: "uint256",
        entityCount: "uint32",
        ipfsCid: "string",
        metadata: "string",
      },
      key: ["id"],
    },
  },
});
