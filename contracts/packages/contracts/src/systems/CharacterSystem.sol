// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { System } from "@latticexyz/world/src/System.sol";
import { Characters, Deaths } from "../codegen/index.sol";
import { EntityType } from "../codegen/common.sol";

contract CharacterSystem is System {
  function registerCharacter(bytes32 id, string memory name, address wallet, EntityType entityType) public {
    Characters.set(id, wallet, entityType, 1, true, block.timestamp, name);
  }

  function killCharacter(bytes32 characterId, string memory cause, string memory location, uint256 tick) public {
    Characters.setAlive(characterId, false);
    bytes32 deathId = keccak256(abi.encodePacked(characterId, block.timestamp));
    uint32 level = Characters.getLevel(characterId);
    Deaths.set(deathId, characterId, level, tick, block.timestamp, cause, location);
  }

  function levelUp(bytes32 characterId, uint32 newLevel) public {
    Characters.setLevel(characterId, newLevel);
  }
}
