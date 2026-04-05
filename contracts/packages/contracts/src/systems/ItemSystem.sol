// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { System } from "@latticexyz/world/src/System.sol";
import { Items } from "../codegen/index.sol";

contract ItemSystem is System {
  function registerItem(
    bytes32 id,
    string memory name,
    string memory rarity,
    bytes32 ownerId,
    bytes32 locationId
  ) public {
    Items.set(id, ownerId, locationId, name, rarity);
  }

  function transferItem(bytes32 itemId, bytes32 newOwnerId) public {
    Items.setOwnerId(itemId, newOwnerId);
    Items.setLocationId(itemId, bytes32(0));
  }

  function dropItem(bytes32 itemId, bytes32 locationId) public {
    Items.setOwnerId(itemId, bytes32(0));
    Items.setLocationId(itemId, locationId);
  }
}
