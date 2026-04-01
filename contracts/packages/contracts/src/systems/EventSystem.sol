// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { System } from "@latticexyz/world/src/System.sol";
import { WorldEvents } from "../codegen/index.sol";
import { EventType } from "../codegen/common.sol";

contract EventSystem is System {
  function recordEvent(
    bytes32 id, EventType eventType, string memory actors, string memory location, string memory summary, uint256 tick
  ) public {
    WorldEvents.set(id, eventType, tick, block.timestamp, actors, location, summary);
  }
}
