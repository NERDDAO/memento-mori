"""Shared test fixtures (UUIDs, entity docs) for the cxn control system.

UUIDs are valid 24-hex ObjectId shapes so they round-trip through the same
id validation graph-memory uses for bonfire/actor ids.
"""

# Characters
KAEL = "6650000000000000000000a1"        # player-agent
GOBLIN = "6650000000000000000000a2"      # NPC patient

# Items
IRON_SWORD = "6650000000000000000000b1"  # instrument (Weapon, damage attr)

# Locations
ASH_MARKET = "6650000000000000000000c1"  # starting room
RIVER_GATE = "6650000000000000000000c2"  # MOVE destination (exit of ASH_MARKET)

BONFIRE_ID = "6650000000000000000000f1"  # mm-world-v1 namespace
