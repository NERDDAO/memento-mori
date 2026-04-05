// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { System } from "@latticexyz/world/src/System.sol";
import { Terrain } from "../codegen/index.sol";

contract TerrainSystem is System {
  uint8 constant TILE_VOID = 0;
  uint8 constant TILE_FLOOR = 1;
  uint8 constant TILE_WALL = 2;
  uint8 constant TILE_EXIT = 3;
  uint8 constant TILE_WATER = 4;
  uint8 constant TILE_FURNITURE = 5;

  function setTerrain(bytes32 locationId, uint32 width, uint32 height, bytes memory terrainData) public {
    require(terrainData.length == width * height, "terrain size mismatch");
    Terrain.set(locationId, width, height, terrainData);
  }

  function getTileType(bytes32 locationId, int32 x, int32 y) public view returns (uint8) {
    uint32 width = Terrain.getWidth(locationId);
    uint32 height = Terrain.getHeight(locationId);
    require(x >= 0 && uint32(x) < width, "x out of bounds");
    require(y >= 0 && uint32(y) < height, "y out of bounds");
    bytes memory terrainData = Terrain.getTerrain(locationId);
    uint256 index = uint256(uint32(y)) * uint256(width) + uint256(uint32(x));
    return uint8(terrainData[index]);
  }

  function isWalkable(bytes32 locationId, int32 x, int32 y) public view returns (bool) {
    uint32 width = Terrain.getWidth(locationId);
    uint32 height = Terrain.getHeight(locationId);
    if (x < 0 || uint32(x) >= width || y < 0 || uint32(y) >= height) return false;
    bytes memory terrainData = Terrain.getTerrain(locationId);
    uint256 index = uint256(uint32(y)) * uint256(width) + uint256(uint32(x));
    uint8 tile = uint8(terrainData[index]);
    return tile == TILE_FLOOR || tile == TILE_EXIT || tile == TILE_WATER;
  }
}
