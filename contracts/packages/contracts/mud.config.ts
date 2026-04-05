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
        quantity: "uint32",
        name: "string",
        rarity: "string",
        slotType: "string",
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

    // --- Spatial index (onchain coordinate system) ---
    Position: {
      schema: {
        id: "bytes32",
        locationId: "bytes32",
        x: "int32",
        y: "int32",
      },
      key: ["id"],
    },
    EntitiesAtPosition: {
      schema: {
        locationId: "bytes32",
        x: "int32",
        y: "int32",
        entities: "bytes32[]",
      },
      key: ["locationId", "x", "y"],
    },
    Terrain: {
      schema: {
        locationId: "bytes32",
        width: "uint32",
        height: "uint32",
        terrain: "bytes",
      },
      key: ["locationId"],
    },
  },
});
