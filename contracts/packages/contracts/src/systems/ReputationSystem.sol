// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { System } from "@latticexyz/world/src/System.sol";
import { Reputation } from "../codegen/index.sol";

contract ReputationSystem is System {
  function updateReputation(address wallet, bytes32 factionId, int32 delta) public {
    int32 current = Reputation.getStanding(wallet, factionId);
    int32 newStanding = current + delta;
    if (newStanding > 100) newStanding = 100;
    if (newStanding < -100) newStanding = -100;
    Reputation.setStanding(wallet, factionId, newStanding);
  }
}
