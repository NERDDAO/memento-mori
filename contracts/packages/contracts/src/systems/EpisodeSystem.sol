// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { System } from "@latticexyz/world/src/System.sol";
import { Episodes } from "../codegen/index.sol";

contract EpisodeSystem is System {
  function recordEpisode(
    bytes32 id, bytes32 contentHash, uint256 tick
  ) public {
    Episodes.set(id, tick, block.timestamp, contentHash);
  }
}
