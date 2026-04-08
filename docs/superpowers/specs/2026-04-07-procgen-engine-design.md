# Procgen Engine — Scaffold Mode

**Date:** 2026-04-07
**Status:** Draft
**Depends on:** Art Department (feat/art-department)

## Problem

Every generation crew starts from a blank canvas. The LLM invents names, stats, layouts, descriptions, and item mechanics from scratch each time. This burns tokens on structural decisions that could be made algorithmically, leaving less budget for the creative/narrative work the LLM is actually good at.

## Design Goal

**Scaffold mode:** Procgen generates structured starting material for every crew. Crews still run, but receive pre-filled context instead of open-ended prompts. The LLM's job shifts from "invent everything" to "add personality, detail, and narrative coherence."

No crews are removed. No output formats change. The scaffolds are injected into the existing task descriptions as additional context.

## Architecture

```
┌────────────────────────────────────────────────┐
│              Existing Crews (unchanged)          │
│  npc_gen · item_gen · world_gen · narration      │
├────────────────────────────────────────────────┤
│              Scaffold Layer (new)                 │
│  Generates structured starting material          │
│  Injected into crew task descriptions            │
├────────────────────────────────────────────────┤
│              Procgen Engine (new)                 │
│  tracery · stat tables · noise · soulfir sprites │
├────────────────────────────────────────────────┤
│              Data Layer (new JSON configs)        │
│  grammars · loot tables · biome defs · name corp │
└────────────────────────────────────────────────┘
```

## Four Components

### 1. Tracery Text Grammars

**Lib:** [pytracery](https://pypi.org/project/tracery/) (MIT, pip installable)

**Where it scaffolds:**

| Crew | Current Input | Scaffold Adds |
|------|--------------|---------------|
| Narration (narrator) | "Write 1-2 sentences of ambient narration" | Pre-generated atmospheric sentence the LLM can use, modify, or discard |
| NPC Concept (concept artist) | "Create name, appearance, backstory" | Pre-generated name, 2-3 appearance fragments, backstory seed sentence |
| NPC Concept (personality writer) | "Define personality, traits, speech pattern" | Pre-rolled trait set, speech pattern template, motivation seed |
| Location (scene painter) | "Write vivid arrival text" | Pre-generated sensory fragments (sounds, smells, visuals) for the biome |
| Item Concept | "Design N items for this location" | Pre-generated item name + one-line description per item from loot grammar |

**Grammar files** (`engine/assets/atlas/grammars/`):

```
grammars/
  narration.json      — ambient atmosphere sentences
  npc_names.json      — name fragments (first/last by culture)
  npc_appearance.json  — physical description fragments
  npc_personality.json — trait/motivation/speech templates
  location_desc.json   — biome-specific sensory descriptions
  item_names.json      — item name patterns by type
  item_desc.json       — item description templates by rarity
```

**Example — narration.json:**
```json
{
  "origin": ["#sensory#. #atmosphere#."],
  "sensory": [
    "#sound# echoes from #direction#",
    "The #light# casts #shadow_adj# shadows across the #surface#",
    "A #smell# hangs in the #air_quality# air",
    "#weather_detail# #weather_effect#"
  ],
  "sound": ["A distant drip", "The creak of old wood", "Something skitters", "Wind howls"],
  "direction": ["the depths below", "somewhere ahead", "behind the walls", "the ceiling"],
  "light": ["torchlight", "pale moonlight", "a faint glow", "dying embers"],
  "shadow_adj": ["long", "flickering", "jagged", "dancing"],
  "surface": ["stone floor", "damp walls", "broken tiles", "moss-covered ground"],
  "smell": ["faint decay", "damp earth", "cold iron", "woodsmoke"],
  "air_quality": ["thick", "stale", "frigid", "damp"],
  "atmosphere": [
    "The #air_quality# air tastes of #smell#",
    "#ambient_state#",
    "Everything here feels #mood_adj#"
  ],
  "ambient_state": [
    "Dust motes drift in the still air",
    "The silence is almost oppressive",
    "Water seeps through cracks in the stone"
  ],
  "mood_adj": ["ancient", "forgotten", "watchful", "heavy with dread"]
}
```

**Integration pattern:**
```python
# In the flow, before crew.kickoff():
from memento.tools.procgen.text_gen import generate_scaffold_text

scaffold = generate_scaffold_text("narration", {
    "biome": biome,
    "mood": mood,
})
# Inject into task description:
task.description += f"\n\nSCAFFOLD (use, modify, or discard):\n{scaffold}"
```

The key phrase is **"use, modify, or discard"** — the LLM always has permission to ignore the scaffold. This keeps quality high while reducing the "blank page" problem.

### 2. Stat & Loot Tables

**No external dep** — JSON config + simple Python roller.

**Where it scaffolds:**

| Crew | Current Input | Scaffold Adds |
|------|--------------|---------------|
| NPC Mechanics (stat builder) | "Assign six ability scores (3-18)" | Pre-rolled stat array based on NPC role/archetype |
| NPC Mechanics (ability designer) | "Select 1-3 abilities" | Pre-selected ability names from archetype's ability pool |
| Item Concept | "Design items matching rarity budget" | Pre-rolled items: name, rarity, slot, base stats from loot table |
| Item Mechanics | "Assign damage, defense, weight, effects" | Pre-calculated stat budget based on rarity tier |
| Item Balance | "Review for balance" | Pre-computed power score per item for comparison |

**Table files** (`engine/assets/atlas/tables/`):

```
tables/
  npc_archetypes.json  — role → stat spread + ability pool
  loot_tables.json     — rarity weights + slot distributions
  item_affixes.json    — prefix/suffix modifiers by rarity tier
  stat_budgets.json    — rarity → total stat points allowed
```

**Example — npc_archetypes.json:**
```json
{
  "warrior": {
    "stat_priority": ["STR", "CON", "DEX", "WIS", "INT", "CHA"],
    "stat_range": {"primary": [14, 18], "secondary": [10, 14], "dump": [6, 10]},
    "skills": ["melee_combat", "intimidation", "athletics"],
    "ability_pool": [
      {"name": "Cleave", "type": "combat", "desc": "Strike multiple adjacent foes"},
      {"name": "Battle Cry", "type": "combat", "desc": "Inspire fear in nearby enemies"},
      {"name": "Shield Wall", "type": "defense", "desc": "Reduce incoming damage for a turn"}
    ]
  },
  "scholar": {
    "stat_priority": ["INT", "WIS", "CHA", "DEX", "CON", "STR"],
    "stat_range": {"primary": [14, 18], "secondary": [10, 14], "dump": [6, 10]},
    "skills": ["lore", "perception", "persuasion"],
    "ability_pool": [
      {"name": "Arcane Insight", "type": "social", "desc": "Identify magical properties of objects"},
      {"name": "Counsel", "type": "social", "desc": "Offer advice that grants a temporary buff"},
      {"name": "Ward", "type": "defense", "desc": "Create a protective barrier"}
    ]
  },
  "merchant": {
    "stat_priority": ["CHA", "INT", "WIS", "DEX", "CON", "STR"],
    "stat_range": {"primary": [14, 18], "secondary": [10, 14], "dump": [6, 10]},
    "skills": ["persuasion", "appraisal", "deception"],
    "ability_pool": [
      {"name": "Haggle", "type": "social", "desc": "Negotiate better prices"},
      {"name": "Appraise", "type": "utility", "desc": "Determine true value of items"},
      {"name": "Silver Tongue", "type": "social", "desc": "Convince NPCs to reveal information"}
    ]
  },
  "rogue": {
    "stat_priority": ["DEX", "CHA", "INT", "WIS", "CON", "STR"],
    "stat_range": {"primary": [14, 18], "secondary": [10, 14], "dump": [6, 10]},
    "skills": ["stealth", "lockpicking", "sleight_of_hand"],
    "ability_pool": [
      {"name": "Backstab", "type": "combat", "desc": "Extra damage from stealth"},
      {"name": "Shadowstep", "type": "movement", "desc": "Teleport short distance in darkness"},
      {"name": "Disarm Trap", "type": "utility", "desc": "Safely disable mechanical traps"}
    ]
  },
  "healer": {
    "stat_priority": ["WIS", "CHA", "CON", "INT", "DEX", "STR"],
    "stat_range": {"primary": [14, 18], "secondary": [10, 14], "dump": [6, 10]},
    "skills": ["medicine", "herbalism", "empathy"],
    "ability_pool": [
      {"name": "Mend", "type": "healing", "desc": "Restore health to a target"},
      {"name": "Purify", "type": "healing", "desc": "Remove poison or disease"},
      {"name": "Sanctuary", "type": "defense", "desc": "Create a zone where combat is suppressed"}
    ]
  }
}
```

**Example — loot_tables.json:**
```json
{
  "rarity_weights": {
    "common": {"common": 70, "uncommon": 25, "rare": 5},
    "uncommon": {"common": 40, "uncommon": 40, "rare": 15, "epic": 5},
    "rare": {"uncommon": 30, "rare": 40, "epic": 25, "legendary": 5}
  },
  "slot_weights": {
    "weapon": 30, "armor": 25, "accessory": 20, "ring": 10, "consumable": 15
  },
  "stat_budgets": {
    "common": {"total": 5, "max_single": 3},
    "uncommon": {"total": 10, "max_single": 5},
    "rare": {"total": 18, "max_single": 8},
    "epic": {"total": 28, "max_single": 12},
    "legendary": {"total": 40, "max_single": 18}
  }
}
```

**Example — item_affixes.json:**
```json
{
  "prefixes": {
    "common": ["Worn", "Simple", "Crude", "Old"],
    "uncommon": ["Sturdy", "Fine", "Sharp", "Tempered"],
    "rare": ["Enchanted", "Masterwork", "Blessed", "Cursed"],
    "epic": ["Soulforged", "Abyssal", "Radiant", "Void-touched"],
    "legendary": ["Primordial", "Godslayer", "Worldbreaker", "Eternal"]
  },
  "suffixes": {
    "weapon": ["of Rending", "of the Hunt", "of Wrath", "of Precision"],
    "armor": ["of Warding", "of the Sentinel", "of Thorns", "of Resilience"],
    "accessory": ["of Insight", "of Haste", "of Fortune", "of Shadows"],
    "ring": ["of Power", "of Protection", "of the Serpent", "of Binding"],
    "consumable": []
  }
}
```

**Roller module** (`tools/procgen/stat_roller.py`):
```python
def roll_npc_stats(archetype: str, seed: int | None = None) -> dict:
    """Roll stat block from archetype template."""
    # Load archetype, roll within ranges per priority tier
    # Returns {"STR": 16, "DEX": 12, ..., "skills": [...], "abilities": [...]}

def roll_loot(rarity_budget: str, num_items: int, seed: int | None = None) -> list[dict]:
    """Roll items from loot table."""
    # Roll rarity per item, select slot, generate name from affixes
    # Returns [{"name": "Worn Iron Sword", "rarity": "common", "slot": "weapon", 
    #           "damage": 3, "defense": 0, "weight": 5, "effects": []}]
```

### 3. Perlin Noise Biome Maps

**Lib:** opensimplex (already installed)

**Where it scaffolds:**

| Crew | Current Input | Scaffold Adds |
|------|--------------|---------------|
| Region Design (geographer) | "Design biome, terrain, propose locations" | Pre-generated region grid with biome assignments and location sites marked |
| Location Planning | "Plan 3-5 locations with connections" | Pre-selected location sites from noise map with natural connection paths |
| Exit Connection | "Create EXIT_TO edges between locations" | Pre-computed minimum spanning tree of location positions |

**How it works:**
1. Generate 2D noise map (elevation + moisture) at region scale
2. Threshold into biomes: water/marsh/forest/plains/hills/mountains
3. Place location sites at interesting terrain features (biome boundaries, elevation peaks, river junctions)
4. Compute natural paths between sites (follow valleys, avoid mountains)
5. Feed this structural layout to the region design crew as a scaffold

**Module** (`tools/procgen/biome_gen.py`):
```python
def generate_region_map(
    width: int = 20,
    height: int = 15,
    theme: str = "dark_fantasy",
    seed: int | None = None,
) -> RegionMap:
    """Generate a biome map with location sites and paths."""
    # Returns: grid of biome chars, list of (x,y,biome) location sites,
    #          list of (site_a, site_b) natural connections

def generate_location_sites(
    region_map: RegionMap,
    num_locations: int = 5,
) -> list[LocationSite]:
    """Select interesting positions for locations on the region map."""
    # Prefer biome boundaries, elevation features, path intersections
```

**Output scaffold for region design crew:**
```
REGION SCAFFOLD (structural layout — add names, culture, threats):
Biome map (20x15):
  FFFFF..~~~
  FFFF...~~~ 
  .FF....~~~
  ......~~~~
  ..HH..~~~~
  .HHH.....
  HHMM.....

Location sites:
  1. (3, 2) — forest/plains boundary (good for a settlement)
  2. (8, 1) — waterfront (harbor or fishing village)
  3. (5, 5) — hills (defensible position — fortress or mine)
  4. (6, 6) — mountain peak (temple or dragon lair)
  5. (1, 4) — deep forest (druid grove or bandit camp)

Natural connections:
  1 → 2 (plains path along river)
  1 → 3 (road through hills)
  1 → 5 (forest trail)
  3 → 4 (mountain pass)
```

### 4. Soulfir Sprite Generator (Vendored)

**Lib:** [soulfir/sprite-generator](https://github.com/soulfir/sprite-generator) (MIT)

**Replaces:** Our hand-rolled `sprite_gen.py` from the art department.

**What soulfir adds over our version:**
- Body-part compositing (head, torso, arms, legs generated separately)
- Multi-directional sprites (front, back, left, right — 3-frame walk cycles)
- Connectivity checking (networkx — no floating pixels)
- Mutation system (variation while preserving silhouette)
- Detail layers (3 levels of interior detail)
- Side view generation

**Integration:** Vendor the core classes (`BottomUpGenerator`, `NPC_Humanoid_Generator`, `HeadGenerator`, `TorsoGenerator`, `LimbGenerator`, `ColourPalGen`) into `engine/src/memento/tools/procgen/soulfir/`. Strip GUI code, matplotlib plot code, hardcoded paths. Wire to our palette system.

**New deps needed:** `scipy` (for `scipy.ndimage.rotate` used in sprite compositing). networkx and PIL already available.

**Module** (`tools/procgen/soulfir/`):
```
soulfir/
  __init__.py
  LICENSE           — MIT license from soulfir
  generator.py      — BottomUpGenerator (core CA + connectivity)
  humanoid.py       — NPC_Humanoid_Generator (body-part compositor)
  parts.py          — HeadGenerator, TorsoGenerator, LimbGenerator
  palette.py        — ColourPalGen (color harmony, bridges to our palette system)
```

**Wire to existing art department:**
- `generate_sprite()` in `sprite_gen.py` delegates to soulfir's `NPC_Humanoid_Generator` for NPCs
- Our simple CA remains as fallback for item icons (soulfir is designed for humanoids)
- `Portraitist` crew gets richer sprites without any crew changes

## Scaffold Injection Pattern

All scaffolds follow the same injection pattern — **no crew code changes needed**. The flows generate scaffolds and append them to task descriptions before `crew.kickoff()`.

```python
# In npc_gen.py generate_npcs(), before concept crew:
from memento.tools.procgen.text_gen import scaffold_npc_concept
from memento.tools.procgen.stat_roller import roll_npc_stats

scaffold = scaffold_npc_concept(
    location_name=self.state.location_name,
    region_context=self.state.region_context,
    role=role_text,
)
# Modify the crew factory to accept optional scaffold:
concept_crew = make_concept_crew(
    npc_role=role_text,
    location_name=self.state.location_name,
    region_context=self.state.region_context,
    scaffold=scaffold,  # NEW — appended to task descriptions
)
```

Each `make_*_crew()` factory gets an optional `scaffold: str = ""` parameter. If provided, it's appended to the first task's description:

```python
if scaffold:
    task.description += (
        f"\n\nSCAFFOLD (use as starting point, modify freely, "
        f"or discard if it doesn't fit):\n{scaffold}"
    )
```

## File Map

### New Files

| File | Responsibility |
|------|---------------|
| `engine/src/memento/tools/procgen/text_gen.py` | Tracery wrapper — load grammars, generate scaffold text |
| `engine/src/memento/tools/procgen/stat_roller.py` | Stat + loot table roller |
| `engine/src/memento/tools/procgen/biome_gen.py` | Perlin noise region maps |
| `engine/src/memento/tools/procgen/soulfir/__init__.py` | Vendored soulfir package |
| `engine/src/memento/tools/procgen/soulfir/LICENSE` | MIT license |
| `engine/src/memento/tools/procgen/soulfir/generator.py` | Core BottomUpGenerator |
| `engine/src/memento/tools/procgen/soulfir/humanoid.py` | NPC_Humanoid_Generator |
| `engine/src/memento/tools/procgen/soulfir/parts.py` | Head/Torso/Limb generators |
| `engine/src/memento/tools/procgen/soulfir/color.py` | ColourPalGen + our palette bridge |
| `engine/assets/atlas/grammars/*.json` | Tracery grammar files (7 files) |
| `engine/assets/atlas/tables/*.json` | Stat/loot table files (4 files) |

### Modified Files

| File | Change |
|------|--------|
| `engine/pyproject.toml` | Add `scipy`, `tracery` deps |
| `engine/src/memento/tools/procgen/sprite_gen.py` | Delegate NPC sprites to soulfir, keep simple CA for items |
| `engine/src/memento/flows/npc_gen.py` | Generate scaffolds before concept + mechanics crews |
| `engine/src/memento/flows/item_gen.py` | Generate loot scaffold before concept crew |
| `engine/src/memento/flows/world_gen.py` | Generate biome map before region design crew |
| `engine/src/memento/crews/npc_gen/concept/crew.py` | Accept optional `scaffold` param |
| `engine/src/memento/crews/npc_gen/mechanics/crew.py` | Accept optional `scaffold` param |
| `engine/src/memento/crews/item_gen/concept/crew.py` | Accept optional `scaffold` param |
| `engine/src/memento/crews/world_gen/region_design/crew.py` | Accept optional `scaffold` param |
| `engine/src/memento/crews/world_gen/location_planning/crew.py` | Accept optional `scaffold` param |
| `engine/src/memento/crews/world_gen/exit_connection/crew.py` | Accept optional `scaffold` param |
| `engine/src/memento/crews/narrative/narration/crew.py` | Accept optional `scaffold` param |

## Token Savings Estimate

| Flow | Before (est. tokens) | After (est. tokens) | Savings |
|------|---------------------|--------------------|---------| 
| NPC gen (per NPC) | ~4000 (4 crews) | ~2500 (scaffolded prompts shorter, LLM generates less) | ~37% |
| Item gen (per batch) | ~3000 (3 crews) | ~1800 (pre-rolled stats reduce mechanics crew work) | ~40% |
| World gen (per region) | ~5000 (4 crews) | ~3000 (biome map + location sites pre-computed) | ~40% |
| Narration (per turn) | ~500 | ~300 (Tracery provides atmospheric seed) | ~40% |

Conservative estimates. The LLM still runs every crew, but prompts are shorter (scaffold replaces verbose instructions) and the LLM generates less (it's refining, not inventing).

## Testing

- Tracery grammars: unit test each grammar file produces valid text
- Stat roller: deterministic with seed, verify stat ranges, verify loot table distributions
- Biome gen: deterministic with seed, verify biome thresholds, verify location site selection
- Soulfir: existing tests from soulfir repo, adapted for our interface
- Scaffold injection: verify scaffold text appears in crew task descriptions
- E2E: mock crew kickoff, verify scaffolded prompts contain expected content

## Phases

### Phase 1: Tracery + Stat Tables
- Text grammars for narration, NPC, items, locations
- Stat roller + loot tables
- Scaffold injection into all generation flows
- Highest ROI — immediate token savings

### Phase 2: Biome Maps
- Perlin noise region generation
- Location site selection
- Path computation for exit connections
- Scaffold injection into world gen flow

### Phase 3: Soulfir Sprites
- Vendor and clean up soulfir code
- Wire to our palette system
- Replace simple CA for NPC sprites
- Keep simple CA for item icons
