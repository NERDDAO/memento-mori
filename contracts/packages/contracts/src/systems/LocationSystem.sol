// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { System } from "@latticexyz/world/src/System.sol";
import { Locations } from "../codegen/index.sol";

contract LocationSystem is System {
  function registerLocation(
    bytes32 id, string memory name, string memory region, address discoveredBy
  ) public {
    Locations.set(id, discoveredBy, block.timestamp, name, region);
  }

  function discoverLocation(bytes32 locationId, address discoverer) public {
    address current = Locations.getDiscoveredBy(locationId);
    if (current == address(0)) {
      Locations.setDiscoveredBy(locationId, discoverer);
      Locations.setDiscoveredAt(locationId, block.timestamp);
    }
  }
}
