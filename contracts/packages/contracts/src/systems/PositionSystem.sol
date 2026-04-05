// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { System } from "@latticexyz/world/src/System.sol";
import { Position, PositionData, EntitiesAtPosition, Terrain } from "../codegen/index.sol";

contract PositionSystem is System {
  function setPosition(bytes32 entityId, bytes32 locationId, int32 x, int32 y) public {
    PositionData memory oldPos = Position.get(entityId);
    if (oldPos.locationId != bytes32(0)) {
      _removeFromTile(oldPos.locationId, oldPos.x, oldPos.y, entityId);
    }
    Position.set(entityId, locationId, x, y);
    EntitiesAtPosition.pushEntities(locationId, x, y, entityId);
  }

  function moveEntity(bytes32 entityId, int32 newX, int32 newY) public {
    PositionData memory current = Position.get(entityId);
    require(current.locationId != bytes32(0), "entity has no position");

    uint32 width = Terrain.getWidth(current.locationId);
    uint32 height = Terrain.getHeight(current.locationId);
    require(newX >= 0 && uint32(newX) < width, "x out of bounds");
    require(newY >= 0 && uint32(newY) < height, "y out of bounds");
    bytes memory terrainData = Terrain.getTerrain(current.locationId);
    uint256 index = uint256(uint32(newY)) * uint256(width) + uint256(uint32(newX));
    uint8 tile = uint8(terrainData[index]);
    require(tile == 1 || tile == 3 || tile == 4, "tile not walkable");

    _removeFromTile(current.locationId, current.x, current.y, entityId);
    Position.set(entityId, current.locationId, newX, newY);
    EntitiesAtPosition.pushEntities(current.locationId, newX, newY, entityId);
  }

  function removePosition(bytes32 entityId) public {
    PositionData memory current = Position.get(entityId);
    if (current.locationId != bytes32(0)) {
      _removeFromTile(current.locationId, current.x, current.y, entityId);
      Position.deleteRecord(entityId);
    }
  }

  function _removeFromTile(bytes32 locationId, int32 x, int32 y, bytes32 entityId) internal {
    bytes32[] memory entities = EntitiesAtPosition.getEntities(locationId, x, y);
    uint256 len = entities.length;
    if (len == 0) return;

    bytes32[] memory updated = new bytes32[](len);
    uint256 j = 0;
    for (uint256 i = 0; i < len; i++) {
      if (entities[i] != entityId) {
        updated[j] = entities[i];
        j++;
      }
    }

    if (j == 0) {
      EntitiesAtPosition.deleteRecord(locationId, x, y);
    } else {
      bytes32[] memory trimmed = new bytes32[](j);
      for (uint256 i = 0; i < j; i++) {
        trimmed[i] = updated[i];
      }
      EntitiesAtPosition.setEntities(locationId, x, y, trimmed);
    }
  }
}
