"""deep_roads_seed — authored opening-room seed for the Deep Roads.

The three facts establish the three immersive-opening beats:
  dying_adventurer  — canon, FORCED_FIRST salience, on_surface="die"
                      → BEAT 1: witnessed death (permadeath witnessed)
  threat            — latent, high salience
                      → atmosphere / future encounter
  iron_blade        — latent, medium salience, Item+Weapon labels
                      → BEAT 2: controls + lazy materialisation (TAKE)

Exit "on" → NEXT_ROOM → BEAT 3: cross-the-exit goal.
"""

from __future__ import annotations

from memento.opening.seed_types import FORCED_FIRST, SeedFact, SeedRoom

# ---------------------------------------------------------------------------
# Module-level UUID constants (24-hex ObjectId-shaped)
# ---------------------------------------------------------------------------

LOC_DEEP_ROADS: str = "507f1f77bcf86cd799439011"
NEXT_ROOM: str = "507f1f77bcf86cd799439012"
UUID_DYING_ADVENTURER: str = "507f1f77bcf86cd799439013"


# ---------------------------------------------------------------------------
# Seed factory
# ---------------------------------------------------------------------------


def deep_roads_seed() -> SeedRoom:
    """Return the authored SeedRoom for the Deep Roads opening sequence."""
    dying_adventurer = SeedFact(
        key="dying_adventurer",
        name="a dying adventurer",
        kind="character",
        salience=FORCED_FIRST,
        canon=True,
        uuid=UUID_DYING_ADVENTURER,
        labels=("Character",),
        on_surface="die",
    )
    threat = SeedFact(
        key="threat",
        name="something in the dark",
        kind="threat",
        salience=100,
        canon=False,
        labels=("Character",),
    )
    iron_blade = SeedFact(
        key="iron_blade",
        name="an iron blade",
        kind="item",
        salience=50,
        canon=False,
        labels=("Item", "Weapon"),
        attrs={"damage": 4},
    )
    return SeedRoom(
        location_id=LOC_DEEP_ROADS,
        name="the deep roads",
        description="Cold stone closes in; the dark presses from every side.",
        facts=(dying_adventurer, threat, iron_blade),
        exits=({"direction": "on", "target_uuid": NEXT_ROOM},),
        win_exit="on",
    )
