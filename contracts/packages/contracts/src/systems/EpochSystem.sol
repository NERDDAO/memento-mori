// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { System } from "@latticexyz/world/src/System.sol";
import { Epochs } from "../codegen/index.sol";

contract EpochSystem is System {
  function commitEpoch(
    bytes32 id,
    bytes32 stateRoot,
    string memory ipfsCid,
    uint256 tick,
    uint32 entityCount,
    string memory metadata
  ) public {
    Epochs.set(id, stateRoot, ipfsCid, tick, block.timestamp, entityCount, metadata);
  }
}
