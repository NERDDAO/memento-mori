# Procgen Engine Phase 1: Tracery + Stat Tables

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add procgen scaffolds (grammar-generated text, table-rolled stats/loot) to all generation crews, reducing LLM token usage ~40% while keeping all crews running.

**Architecture:** A Tracery text generator and JSON-driven stat/loot roller produce structured scaffolds. Each crew factory gets an optional `scaffold` param appended to task descriptions with "use, modify, or discard" framing. Flows generate scaffolds before `crew.kickoff()` and pass them through.

**Tech Stack:** Python 3.10+, tracery (pip), JSON config files, existing CrewAI framework

**Spec:** `docs/superpowers/specs/2026-04-07-procgen-engine-design.md`

---

## File Map

### New Files

| File | Responsibility |
|------|---------------|
| `engine/src/memento/tools/procgen/text_gen.py` | Tracery wrapper — load grammars, generate scaffold text per domain |
| `engine/src/memento/tools/procgen/stat_roller.py` | NPC stat roller + item loot roller from JSON tables |
| `engine/assets/atlas/grammars/narration.json` | Ambient atmosphere sentence grammar |
| `engine/assets/atlas/grammars/npc_names.json` | Fantasy name fragment grammar |
| `engine/assets/atlas/grammars/npc_appearance.json` | Physical description fragment grammar |
| `engine/assets/atlas/grammars/npc_personality.json` | Trait/motivation/speech grammar |
| `engine/assets/atlas/grammars/location_desc.json` | Biome-specific sensory description grammar |
| `engine/assets/atlas/grammars/item_names.json` | Item name patterns by type grammar |
| `engine/assets/atlas/tables/npc_archetypes.json` | Role → stat spread + ability pool |
| `engine/assets/atlas/tables/loot_tables.json` | Rarity weights + slot distributions + stat budgets |
| `engine/assets/atlas/tables/item_affixes.json` | Prefix/suffix modifiers by rarity |

### Modified Files

| File | Change |
|------|--------|
| `engine/pyproject.toml` | Add `tracery` dep |
| `engine/src/memento/crews/npc_gen/concept/crew.py:8` | Add `scaffold=""` param to `make_concept_crew` |
| `engine/src/memento/crews/npc_gen/mechanics/crew.py:8` | Add `scaffold=""` param to `make_mechanics_crew` |
| `engine/src/memento/crews/item_gen/concept/crew.py:9` | Add `scaffold=""` param to `make_item_concept_crew` |
| `engine/src/memento/crews/item_gen/mechanics/crew.py:7` | Add `scaffold=""` param to `make_item_mechanics_crew` |
| `engine/src/memento/crews/world_gen/region_design/crew.py:8` | Add `scaffold=""` param to `make_region_design_crew` |
| `engine/src/memento/crews/world_gen/location_planning/crew.py:7` | Add `scaffold=""` param |
| `engine/src/memento/crews/world_gen/exit_connection/crew.py:8` | Add `scaffold=""` param |
| `engine/src/memento/crews/narrative/narration/crew.py:9` | Add `scaffold=""` param to `make_narration_crew` |
| `engine/src/memento/flows/npc_gen.py:87,95` | Generate scaffolds before concept + mechanics crews |
| `engine/src/memento/flows/item_gen.py:28,39` | Generate scaffold before concept + mechanics crews |
| `engine/src/memento/flows/world_gen.py:42,54` | Generate scaffold before region + location planning |

### Test Files

| File | Tests |
|------|-------|
| `engine/tests/tools/procgen/test_text_gen.py` | Tracery grammar loading, text generation, biome variants |
| `engine/tests/tools/procgen/test_stat_roller.py` | NPC stat rolling, loot rolling, determinism, range checks |
| `engine/tests/integration/test_scaffold_injection.py` | Scaffold appears in crew task descriptions |

---

## Task 1: Add Tracery Dependency

**Files:**
- Modify: `engine/pyproject.toml`

- [ ] **Step 1: Add tracery to dependencies**

In `engine/pyproject.toml`, add `"tracery>=0.1.1"` to the dependencies list:

```toml
dependencies = [
    "crewai[tools]",
    "bonfires",
    "pydantic>=2.0",
    "pyyaml",
    "web3",
    "requests",
    "Pillow>=10.0",
    "numpy>=1.24",
    "tracery>=0.1.1",
]
```

- [ ] **Step 2: Verify import**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -c "import tracery; from tracery.modifiers import base_english; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/pyproject.toml
git commit -m "feat(procgen): add tracery dependency for grammar-based text generation"
```

---

## Task 2: Tracery Grammar Files

**Files:**
- Create: `engine/assets/atlas/grammars/narration.json`
- Create: `engine/assets/atlas/grammars/npc_names.json`
- Create: `engine/assets/atlas/grammars/npc_appearance.json`
- Create: `engine/assets/atlas/grammars/npc_personality.json`
- Create: `engine/assets/atlas/grammars/location_desc.json`
- Create: `engine/assets/atlas/grammars/item_names.json`

- [ ] **Step 1: Create grammars directory**

```bash
mkdir -p /home/at0x/Vaults/Bonfires/memento-mori/engine/assets/atlas/grammars
```

- [ ] **Step 2: Create narration.json**

```json
{
  "origin": ["#sensory#. #atmosphere#."],
  "sensory": [
    "#sound# echoes from #direction#",
    "The #light# casts #shadow_adj# shadows across the #surface#",
    "A faint #smell# hangs in the #air_quality# air",
    "#weather_detail#"
  ],
  "sound": ["A distant drip", "The creak of old wood", "Something skitters", "Wind howls", "A low rumble", "Faint whispers", "Chains rattle", "Stone grinds against stone"],
  "direction": ["the depths below", "somewhere ahead", "behind the walls", "the ceiling above", "a nearby passage", "the darkness"],
  "light": ["torchlight", "pale moonlight", "a faint glow", "dying embers", "phosphorescent moss", "a crack in the ceiling"],
  "shadow_adj": ["long", "flickering", "jagged", "dancing", "crawling", "twisted"],
  "surface": ["stone floor", "damp walls", "broken tiles", "moss-covered ground", "crumbling masonry", "packed earth"],
  "smell": ["decay", "damp earth", "cold iron", "woodsmoke", "sulphur", "old parchment", "dried blood"],
  "air_quality": ["thick", "stale", "frigid", "damp", "heavy", "thin"],
  "atmosphere": [
    "The #air_quality# air tastes of #smell#",
    "#ambient_state#",
    "Everything here feels #mood_adj#"
  ],
  "ambient_state": [
    "Dust motes drift in the still air",
    "The silence is almost oppressive",
    "Water seeps through cracks in the stone",
    "Something moved just at the edge of vision",
    "The ground is slick with moisture",
    "Old bloodstains mark the floor"
  ],
  "mood_adj": ["ancient", "forgotten", "watchful", "heavy with dread", "eerily quiet", "wrong somehow"],
  "weather_detail": [
    "Rain drums steadily overhead",
    "A cold draft cuts through the passage",
    "Fog clings to the ground like a living thing",
    "The air shimmers with heat",
    "Frost crystals line every surface"
  ]
}
```

- [ ] **Step 3: Create npc_names.json**

```json
{
  "origin": ["#first# #last#"],
  "first": ["Aldric", "Brenna", "Caelum", "Drusilla", "Eamon", "Freya", "Gareth", "Helga", "Idris", "Jessamine", "Kael", "Liora", "Mordecai", "Nyx", "Orin", "Petra", "Quillon", "Rhea", "Silas", "Thorne", "Ursa", "Vex", "Wren", "Xander", "Yara", "Zephyr", "Ashwin", "Brigid", "Corvus", "Dahlia", "Elara", "Fenris", "Griselda", "Hadrian", "Isolde", "Jareth"],
  "last": ["#surname_prefix##surname_suffix#"],
  "surname_prefix": ["Black", "Iron", "Storm", "Ash", "Bone", "Crow", "Dark", "Flame", "Frost", "Grave", "Hallow", "Night", "Raven", "Shadow", "Thorn", "Wolf", "Blood", "Stone", "Rust", "Mire"],
  "surname_suffix": ["wood", "forge", "born", "bane", "hollow", "moor", "vale", "crest", "fell", "keep", "water", "wind", "fire", "hand", "heart", "ward", "blade", "thorn", "weald", "marsh"]
}
```

- [ ] **Step 4: Create npc_appearance.json**

```json
{
  "origin": ["#build#. #face#. #distinguishing#."],
  "build": [
    "A #height# figure with #body_type# frame",
    "#height# and #body_type#, with #posture# posture",
    "Of #height# stature, #body_type# beneath #clothing#"
  ],
  "height": ["tall", "short", "average-height", "towering", "diminutive", "broad"],
  "body_type": ["wiry", "stocky", "gaunt", "muscular", "heavyset", "lean", "weathered"],
  "posture": ["stooped", "rigid", "relaxed", "hunched", "proud", "guarded"],
  "clothing": ["a tattered cloak", "worn leather armor", "heavy robes", "a stained apron", "patched travelling clothes", "faded livery"],
  "face": [
    "#eyes# eyes peer from a #face_shape# face",
    "A #face_shape# face dominated by #facial_feature#",
    "#eyes# eyes and #facial_feature# mark a #face_shape# face"
  ],
  "eyes": ["Sharp", "Sunken", "Bright", "Weary", "Cold", "Keen", "Hollow", "Dark"],
  "face_shape": ["angular", "round", "scarred", "weathered", "gaunt", "broad", "narrow"],
  "facial_feature": ["a crooked nose", "a thick beard", "ritual scarring", "a missing ear", "a jagged scar", "deep laugh lines", "burn marks"],
  "distinguishing": [
    "They carry #carried_item#",
    "A #trinket# hangs from their #trinket_location#",
    "#habit# betrays their #background#"
  ],
  "carried_item": ["a gnarled walking stick", "a sheathed blade of unusual make", "a bundle of dried herbs", "a heavy ledger", "a lantern that never seems to go out"],
  "trinket": ["tarnished locket", "bone charm", "holy symbol", "signet ring", "faded ribbon"],
  "trinket_location": ["neck", "belt", "wrist", "ear"],
  "habit": ["A nervous twitch", "Calloused hands", "An accent from the eastern provinces", "The way they watch doorways", "Ink-stained fingers"],
  "background": ["military service", "years at the forge", "a life of hardship", "noble upbringing", "time in the mines", "a scholarly past"]
}
```

- [ ] **Step 5: Create npc_personality.json**

```json
{
  "origin": ["#trait_primary#, but #trait_secondary#. #motivation#. #speech#."],
  "trait_primary": [
    "Fiercely loyal to those who earn their trust",
    "Cautious to the point of paranoia",
    "Generous despite having little",
    "Quietly ambitious",
    "Haunted by past failures",
    "Stubbornly pragmatic",
    "Warm and disarming",
    "Coldly calculating"
  ],
  "trait_secondary": [
    "harbours a deep resentment toward authority",
    "prone to sudden bursts of temper",
    "secretly terrified of the dark",
    "struggles with a guilty conscience",
    "has difficulty trusting strangers",
    "hides a cruel streak",
    "drinks more than they should",
    "keeps a dangerous secret"
  ],
  "motivation": [
    "Driven by #motivation_core#",
    "Everything they do serves #motivation_core#",
    "Their one true goal is #motivation_core#"
  ],
  "motivation_core": [
    "revenge against those who wronged their family",
    "accumulating enough coin to leave this place",
    "protecting someone they love from a hidden threat",
    "finding a cure for a mysterious illness",
    "uncovering the truth about their parents",
    "paying off a debt to dangerous people",
    "earning redemption for a terrible mistake",
    "surviving long enough to see the next season"
  ],
  "speech": [
    "Speaks in #speech_style#",
    "Their speech is #speech_style#",
    "Communicates through #speech_style#"
  ],
  "speech_style": [
    "clipped, military cadences",
    "slow, deliberate sentences",
    "rapid-fire chatter peppered with profanity",
    "formal, almost archaic phrasing",
    "quiet murmurs barely above a whisper",
    "blunt, unvarnished honesty",
    "flowery metaphors and roundabout answers",
    "grunts and gestures more than words"
  ]
}
```

- [ ] **Step 6: Create location_desc.json**

```json
{
  "origin": ["#visual#. #sensory#. #detail#."],
  "visual": [
    "The #space_type# stretches #direction_desc#, #lighting#",
    "#architecture# lines the #surface_type#, #condition#",
    "A #space_size# #space_type# opens before you, #lighting#"
  ],
  "space_type": ["chamber", "corridor", "hall", "passage", "cavern", "room", "gallery"],
  "space_size": ["vast", "cramped", "narrow", "cavernous", "modest"],
  "direction_desc": ["ahead into darkness", "in every direction", "toward a distant archway", "down a gentle slope"],
  "lighting": ["lit by #light_source#", "bathed in #light_quality# light", "shrouded in near-total darkness"],
  "light_source": ["guttering torches", "bioluminescent fungi", "cracks in the ceiling", "a single hanging lantern", "glowing runes"],
  "light_quality": ["pale", "warm", "sickly green", "flickering amber", "cold blue"],
  "architecture": ["Rough-hewn stone", "Crumbling brick", "Polished marble veined with black", "Timber beams thick with age", "Cyclopean blocks"],
  "surface_type": ["walls", "floor", "ceiling", "pillars", "archways"],
  "condition": ["worn smooth by countless feet", "cracked and water-stained", "surprisingly well-preserved", "covered in a thin layer of dust"],
  "sensory": [
    "The air is #temperature# and #air_feel#",
    "#ambient_sound# fills the space",
    "The scent of #location_smell# is unmistakable"
  ],
  "temperature": ["cold", "warm", "frigid", "uncomfortably hot", "cool"],
  "air_feel": ["damp", "dry", "still", "carries a faint breeze", "thick with moisture"],
  "ambient_sound": ["A steady dripping", "Dead silence", "A low hum", "Distant echoes", "The rush of underground water"],
  "location_smell": ["wet stone", "old fires", "something rotting", "earth and roots", "incense long burned away"],
  "detail": [
    "#furniture# occupies the #position#",
    "#debris# is scattered across the floor",
    "#wall_feature# catches the eye"
  ],
  "furniture": ["A broken table", "An overturned chair", "A stone sarcophagus", "A rusted cage", "A wooden rack"],
  "debris": ["Rubble from a collapsed wall", "Shattered pottery", "Bones of indeterminate origin", "Torn cloth and broken tools"],
  "wall_feature": ["A faded mural", "Deep claw marks", "A bricked-up doorway", "Graffiti in an unknown script", "A carved relief"],
  "position": ["far corner", "center of the room", "space near the entrance", "alcove to one side"]
}
```

- [ ] **Step 7: Create item_names.json**

```json
{
  "origin": ["#prefix# #base#"],
  "prefix": ["#common_prefix#"],
  "common_prefix": ["Worn", "Simple", "Crude", "Old", "Battered", "Rusty", "Cracked", "Dull"],
  "uncommon_prefix": ["Sturdy", "Fine", "Sharp", "Tempered", "Reinforced", "Polished", "Hardened"],
  "rare_prefix": ["Enchanted", "Masterwork", "Blessed", "Gleaming", "Runic", "Warden's"],
  "epic_prefix": ["Soulforged", "Abyssal", "Radiant", "Void-touched", "Mythral", "Primeval"],
  "legendary_prefix": ["Primordial", "Godslayer", "Worldbreaker", "Eternal", "Doomforged"],
  "base": ["#weapon_base#"],
  "weapon_base": ["Sword", "Axe", "Dagger", "Mace", "Spear", "Bow", "Staff", "Hammer", "Blade", "Halberd"],
  "armor_base": ["Shield", "Helm", "Breastplate", "Greaves", "Gauntlets", "Chainmail", "Buckler", "Pauldrons"],
  "accessory_base": ["Amulet", "Cloak", "Belt", "Boots", "Bracers", "Circlet", "Talisman", "Pendant"],
  "ring_base": ["Ring", "Band", "Signet", "Loop"],
  "consumable_base": ["Potion", "Elixir", "Salve", "Tonic", "Draught", "Vial", "Flask"],
  "weapon_suffix": ["of Rending", "of the Hunt", "of Wrath", "of Precision", "of Cleaving", "of the Viper"],
  "armor_suffix": ["of Warding", "of the Sentinel", "of Thorns", "of Resilience", "of the Bulwark"],
  "accessory_suffix": ["of Insight", "of Haste", "of Fortune", "of Shadows", "of the Wanderer"],
  "ring_suffix": ["of Power", "of Protection", "of the Serpent", "of Binding", "of Vitality"],
  "consumable_suffix": []
}
```

- [ ] **Step 8: Commit all grammar files**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/assets/atlas/grammars/
git commit -m "feat(procgen): add Tracery grammar files for narration, NPCs, locations, and items"
```

---

## Task 3: Tracery Text Generator Module

**Files:**
- Create: `engine/src/memento/tools/procgen/text_gen.py`
- Test: `engine/tests/tools/procgen/test_text_gen.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/tools/procgen/test_text_gen.py
"""Tests for Tracery text generation."""
import pytest
from memento.tools.procgen.text_gen import (
    generate_text,
    generate_npc_name,
    generate_npc_scaffold,
    generate_item_name,
    generate_narration_scaffold,
    generate_location_scaffold,
)


def test_generate_text_narration():
    result = generate_text("narration", seed=42)
    assert isinstance(result, str)
    assert len(result) > 10
    # Should be 2 sentences (origin has 2 parts separated by .)
    assert "." in result


def test_generate_text_deterministic():
    r1 = generate_text("narration", seed=42)
    r2 = generate_text("narration", seed=42)
    assert r1 == r2


def test_generate_text_different_seeds():
    r1 = generate_text("narration", seed=42)
    r2 = generate_text("narration", seed=99)
    assert r1 != r2


def test_generate_npc_name():
    name = generate_npc_name(seed=42)
    assert isinstance(name, str)
    parts = name.split()
    assert len(parts) == 2  # first + last


def test_generate_npc_scaffold():
    scaffold = generate_npc_scaffold(role="tavern keeper", location="The Rusty Nail", seed=42)
    assert "Name:" in scaffold
    assert "Appearance:" in scaffold
    assert "Personality:" in scaffold


def test_generate_item_name_with_rarity():
    name = generate_item_name(slot="weapon", rarity="rare", seed=42)
    assert isinstance(name, str)
    assert len(name) > 3


def test_generate_narration_scaffold():
    scaffold = generate_narration_scaffold(seed=42)
    assert isinstance(scaffold, str)
    assert len(scaffold) > 10


def test_generate_location_scaffold():
    scaffold = generate_location_scaffold(seed=42)
    assert isinstance(scaffold, str)
    assert len(scaffold) > 10


def test_unknown_grammar_returns_empty():
    result = generate_text("nonexistent_grammar", seed=42)
    assert result == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/tools/procgen/test_text_gen.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement text_gen.py**

```python
# engine/src/memento/tools/procgen/text_gen.py
"""Tracery-based text generation for procgen scaffolds.

Loads JSON grammar files and generates text using the Tracery library.
Each grammar file defines expansion rules for a specific domain
(narration, NPC names, item names, etc).
"""

import json
import logging
import random
from pathlib import Path

import tracery
from tracery.modifiers import base_english

_GRAMMARS_DIR = Path(__file__).resolve().parents[4] / "assets" / "atlas" / "grammars"
_GRAMMAR_CACHE: dict[str, dict] = {}

logger = logging.getLogger(__name__)


def _load_grammar(name: str) -> dict | None:
    """Load a grammar file by name. Returns None if not found."""
    if name in _GRAMMAR_CACHE:
        return _GRAMMAR_CACHE[name]
    path = _GRAMMARS_DIR / f"{name}.json"
    if not path.exists():
        logger.warning("Grammar file not found: %s", path)
        return None
    data = json.loads(path.read_text())
    _GRAMMAR_CACHE[name] = data
    return data


def generate_text(grammar_name: str, overrides: dict | None = None, seed: int | None = None) -> str:
    """Generate text from a named grammar file.

    Args:
        grammar_name: Name of the grammar file (without .json).
        overrides: Optional dict of rule overrides to merge into the grammar.
        seed: Random seed for deterministic output.

    Returns:
        Generated text string, or empty string if grammar not found.
    """
    rules = _load_grammar(grammar_name)
    if rules is None:
        return ""

    # Merge overrides
    merged = dict(rules)
    if overrides:
        merged.update(overrides)

    # Seed random for determinism
    if seed is not None:
        random.seed(seed)

    grammar = tracery.Grammar(merged)
    grammar.add_modifiers(base_english)
    result = grammar.flatten("#origin#")

    # Reset random state
    if seed is not None:
        random.seed()

    return result


def generate_npc_name(seed: int | None = None) -> str:
    """Generate a fantasy NPC name."""
    return generate_text("npc_names", seed=seed)


def generate_narration_scaffold(seed: int | None = None) -> str:
    """Generate an atmospheric narration sentence for scaffold."""
    return generate_text("narration", seed=seed)


def generate_location_scaffold(seed: int | None = None) -> str:
    """Generate a location description scaffold."""
    return generate_text("location_desc", seed=seed)


def generate_npc_scaffold(role: str = "", location: str = "", seed: int | None = None) -> str:
    """Generate a full NPC scaffold with name, appearance, and personality.

    Returns a multi-line string ready to inject into crew task descriptions.
    """
    name = generate_text("npc_names", seed=seed)
    # Use different seeds for each component to avoid repetition
    base_seed = seed or 0
    appearance = generate_text("npc_appearance", seed=base_seed + 1 if seed else None)
    personality = generate_text("npc_personality", seed=base_seed + 2 if seed else None)

    parts = [
        f"Name: {name}",
        f"Appearance: {appearance}",
        f"Personality: {personality}",
    ]
    if role:
        parts.insert(0, f"Role: {role}")
    if location:
        parts.insert(1 if role else 0, f"Location: {location}")

    return "\n".join(parts)


def generate_item_name(slot: str = "weapon", rarity: str = "common", seed: int | None = None) -> str:
    """Generate an item name appropriate for the given slot and rarity.

    Selects prefix from rarity tier and base/suffix from slot type.
    """
    # Map rarity to prefix key
    prefix_key = f"{rarity}_prefix"
    # Map slot to base and suffix keys
    base_key = f"{slot}_base" if slot in ("weapon", "armor", "accessory", "ring", "consumable") else "weapon_base"
    suffix_key = f"{slot}_suffix" if slot in ("weapon", "armor", "accessory", "ring") else ""

    overrides = {
        "prefix": [f"#{prefix_key}#"],
        "base": [f"#{base_key}#"],
    }

    # Add suffix for non-common items
    if rarity in ("rare", "epic", "legendary") and suffix_key:
        overrides["origin"] = [f"#prefix# #base# #suffix#"]
        overrides["suffix"] = [f"#{suffix_key}#"]
    else:
        overrides["origin"] = ["#prefix# #base#"]

    return generate_text("item_names", overrides=overrides, seed=seed)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/tools/procgen/test_text_gen.py -v
```

Expected: All 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/tools/procgen/text_gen.py engine/tests/tools/procgen/test_text_gen.py
git commit -m "feat(procgen): add Tracery text generator with NPC, item, location, and narration scaffolds"
```

---

## Task 4: Stat & Loot Table JSON Files

**Files:**
- Create: `engine/assets/atlas/tables/npc_archetypes.json`
- Create: `engine/assets/atlas/tables/loot_tables.json`
- Create: `engine/assets/atlas/tables/item_affixes.json`

- [ ] **Step 1: Create tables directory**

```bash
mkdir -p /home/at0x/Vaults/Bonfires/memento-mori/engine/assets/atlas/tables
```

- [ ] **Step 2: Create npc_archetypes.json**

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
  },
  "guard": {
    "stat_priority": ["CON", "STR", "WIS", "DEX", "CHA", "INT"],
    "stat_range": {"primary": [14, 18], "secondary": [10, 14], "dump": [6, 10]},
    "skills": ["perception", "melee_combat", "intimidation"],
    "ability_pool": [
      {"name": "Stand Firm", "type": "defense", "desc": "Cannot be moved or knocked down"},
      {"name": "Detain", "type": "combat", "desc": "Restrain a target for one turn"},
      {"name": "Alert", "type": "utility", "desc": "Call for reinforcements"}
    ]
  },
  "innkeeper": {
    "stat_priority": ["CHA", "WIS", "CON", "INT", "DEX", "STR"],
    "stat_range": {"primary": [12, 16], "secondary": [10, 14], "dump": [8, 12]},
    "skills": ["persuasion", "cooking", "gossip"],
    "ability_pool": [
      {"name": "Hearty Meal", "type": "healing", "desc": "Restore health through a warm meal"},
      {"name": "Rumour Mill", "type": "social", "desc": "Share local gossip and quest hooks"},
      {"name": "Barkeep's Eye", "type": "utility", "desc": "Spot trouble before it starts"}
    ]
  },
  "default": {
    "stat_priority": ["CON", "WIS", "CHA", "STR", "DEX", "INT"],
    "stat_range": {"primary": [12, 16], "secondary": [10, 14], "dump": [8, 12]},
    "skills": ["perception", "survival", "persuasion"],
    "ability_pool": [
      {"name": "Endure", "type": "defense", "desc": "Resist one negative effect"},
      {"name": "Barter", "type": "social", "desc": "Trade items at fair value"},
      {"name": "Keen Senses", "type": "utility", "desc": "Detect hidden objects or passages"}
    ]
  }
}
```

- [ ] **Step 3: Create loot_tables.json**

```json
{
  "rarity_weights": {
    "common": {"common": 70, "uncommon": 25, "rare": 5},
    "uncommon": {"common": 40, "uncommon": 40, "rare": 15, "epic": 5},
    "rare": {"uncommon": 30, "rare": 40, "epic": 25, "legendary": 5}
  },
  "slot_weights": {
    "weapon": 30,
    "armor": 25,
    "accessory": 20,
    "ring": 10,
    "consumable": 15
  },
  "stat_budgets": {
    "common": {"total": 5, "max_single": 3},
    "uncommon": {"total": 10, "max_single": 5},
    "rare": {"total": 18, "max_single": 8},
    "epic": {"total": 28, "max_single": 12},
    "legendary": {"total": 40, "max_single": 18}
  },
  "base_stats": {
    "weapon": {"damage": [2, 5], "defense": 0, "weight": [3, 8]},
    "armor": {"damage": 0, "defense": [2, 5], "weight": [5, 15]},
    "accessory": {"damage": 0, "defense": [0, 2], "weight": [1, 3]},
    "ring": {"damage": 0, "defense": 0, "weight": [0, 1]},
    "consumable": {"damage": 0, "defense": 0, "weight": [0, 2]}
  }
}
```

- [ ] **Step 4: Create item_affixes.json**

```json
{
  "prefixes": {
    "common": ["Worn", "Simple", "Crude", "Old", "Battered", "Rusty"],
    "uncommon": ["Sturdy", "Fine", "Sharp", "Tempered", "Reinforced"],
    "rare": ["Enchanted", "Masterwork", "Blessed", "Gleaming", "Runic"],
    "epic": ["Soulforged", "Abyssal", "Radiant", "Void-touched", "Mythral"],
    "legendary": ["Primordial", "Godslayer", "Worldbreaker", "Eternal", "Doomforged"]
  },
  "suffixes": {
    "weapon": ["of Rending", "of the Hunt", "of Wrath", "of Precision", "of Cleaving"],
    "armor": ["of Warding", "of the Sentinel", "of Thorns", "of Resilience", "of the Bulwark"],
    "accessory": ["of Insight", "of Haste", "of Fortune", "of Shadows", "of the Wanderer"],
    "ring": ["of Power", "of Protection", "of the Serpent", "of Binding", "of Vitality"],
    "consumable": ["of Restoration", "of Clarity", "of Vigor", "of Haste"]
  }
}
```

- [ ] **Step 5: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/assets/atlas/tables/
git commit -m "feat(procgen): add NPC archetype, loot table, and item affix JSON configs"
```

---

## Task 5: Stat & Loot Roller Module

**Files:**
- Create: `engine/src/memento/tools/procgen/stat_roller.py`
- Test: `engine/tests/tools/procgen/test_stat_roller.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/tools/procgen/test_stat_roller.py
"""Tests for NPC stat roller and item loot roller."""
import pytest
from memento.tools.procgen.stat_roller import (
    roll_npc_stats,
    roll_loot,
    load_archetypes,
    load_loot_tables,
)


def test_load_archetypes():
    archetypes = load_archetypes()
    assert "warrior" in archetypes
    assert "scholar" in archetypes
    assert "default" in archetypes


def test_load_loot_tables():
    tables = load_loot_tables()
    assert "rarity_weights" in tables
    assert "stat_budgets" in tables


def test_roll_npc_stats_warrior():
    stats = roll_npc_stats("warrior", seed=42)
    assert "STR" in stats
    assert "DEX" in stats
    assert "CON" in stats
    assert "INT" in stats
    assert "WIS" in stats
    assert "CHA" in stats
    # Primary stat (STR for warrior) should be in range [14, 18]
    assert 14 <= stats["STR"] <= 18
    assert "skills" in stats
    assert "abilities" in stats
    assert len(stats["abilities"]) >= 1
    assert len(stats["abilities"]) <= 3


def test_roll_npc_stats_unknown_archetype_uses_default():
    stats = roll_npc_stats("nonexistent_role", seed=42)
    default_stats = roll_npc_stats("default", seed=42)
    assert stats["skills"] == default_stats["skills"]


def test_roll_npc_stats_deterministic():
    s1 = roll_npc_stats("warrior", seed=42)
    s2 = roll_npc_stats("warrior", seed=42)
    assert s1 == s2


def test_roll_npc_stats_different_seeds():
    s1 = roll_npc_stats("warrior", seed=42)
    s2 = roll_npc_stats("warrior", seed=99)
    assert s1 != s2


def test_roll_loot_returns_correct_count():
    items = roll_loot("common", num_items=3, seed=42)
    assert len(items) == 3


def test_roll_loot_item_has_required_fields():
    items = roll_loot("common", num_items=1, seed=42)
    item = items[0]
    assert "name" in item
    assert "rarity" in item
    assert "slot" in item
    assert "damage" in item
    assert "defense" in item
    assert "weight" in item


def test_roll_loot_rarity_respects_budget():
    # With common budget, should mostly get common items
    items = roll_loot("common", num_items=20, seed=42)
    rarities = [i["rarity"] for i in items]
    common_count = rarities.count("common")
    assert common_count >= 10  # at least half should be common


def test_roll_loot_deterministic():
    l1 = roll_loot("uncommon", num_items=3, seed=42)
    l2 = roll_loot("uncommon", num_items=3, seed=42)
    assert l1 == l2


def test_roll_loot_stats_within_budget():
    items = roll_loot("rare", num_items=5, seed=42)
    for item in items:
        rarity = item["rarity"]
        # stat_budgets: common=5, uncommon=10, rare=18, epic=28, legendary=40
        max_budgets = {"common": 5, "uncommon": 10, "rare": 18, "epic": 28, "legendary": 40}
        budget = max_budgets.get(rarity, 40)
        total_stats = item["damage"] + item["defense"]
        assert total_stats <= budget, f"{item['name']} total stats {total_stats} exceeds budget {budget}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/tools/procgen/test_stat_roller.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement stat_roller.py**

```python
# engine/src/memento/tools/procgen/stat_roller.py
"""NPC stat roller and item loot roller from JSON table configs.

Generates deterministic stat blocks and loot drops from archetype
templates and rarity-weighted tables. Designed to provide scaffolds
for LLM crews — the LLM refines what the tables produce.
"""

import json
import random
from pathlib import Path

_TABLES_DIR = Path(__file__).resolve().parents[4] / "assets" / "atlas" / "tables"

_ARCHETYPES: dict = {}
_LOOT_TABLES: dict = {}
_AFFIXES: dict = {}


def _ensure_loaded() -> None:
    if _ARCHETYPES:
        return
    _ARCHETYPES.update(json.loads((_TABLES_DIR / "npc_archetypes.json").read_text()))
    _LOOT_TABLES.update(json.loads((_TABLES_DIR / "loot_tables.json").read_text()))
    _AFFIXES.update(json.loads((_TABLES_DIR / "item_affixes.json").read_text()))


def load_archetypes() -> dict:
    """Load and return NPC archetype data."""
    _ensure_loaded()
    return dict(_ARCHETYPES)


def load_loot_tables() -> dict:
    """Load and return loot table data."""
    _ensure_loaded()
    return dict(_LOOT_TABLES)


def roll_npc_stats(archetype: str, seed: int | None = None) -> dict:
    """Roll a stat block from an archetype template.

    Args:
        archetype: Archetype name (warrior, scholar, merchant, etc).
                   Falls back to 'default' if not found.
        seed: Random seed for deterministic output.

    Returns:
        Dict with STR, DEX, CON, INT, WIS, CHA, skills, abilities.
    """
    _ensure_loaded()
    rng = random.Random(seed)

    arch = _ARCHETYPES.get(archetype, _ARCHETYPES["default"])
    stat_range = arch["stat_range"]
    priority = arch["stat_priority"]

    # Roll stats: first 2 in priority get primary range, next 2 secondary, last 2 dump
    stats: dict[str, int] = {}
    for i, stat_name in enumerate(priority):
        if i < 2:
            lo, hi = stat_range["primary"]
        elif i < 4:
            lo, hi = stat_range["secondary"]
        else:
            lo, hi = stat_range["dump"]
        stats[stat_name] = rng.randint(lo, hi)

    # Select 1-3 abilities from pool
    num_abilities = rng.randint(1, min(3, len(arch["ability_pool"])))
    abilities = rng.sample(arch["ability_pool"], num_abilities)

    return {
        **stats,
        "skills": list(arch["skills"]),
        "abilities": abilities,
    }


def _roll_rarity(budget: str, rng: random.Random) -> str:
    """Roll a rarity tier from the budget's weight table."""
    _ensure_loaded()
    weights = _LOOT_TABLES["rarity_weights"].get(budget, _LOOT_TABLES["rarity_weights"]["common"])
    rarities = list(weights.keys())
    weight_values = list(weights.values())
    return rng.choices(rarities, weights=weight_values, k=1)[0]


def _roll_slot(rng: random.Random) -> str:
    """Roll an item slot from slot weights."""
    _ensure_loaded()
    slots = list(_LOOT_TABLES["slot_weights"].keys())
    weights = list(_LOOT_TABLES["slot_weights"].values())
    return rng.choices(slots, weights=weights, k=1)[0]


def _roll_item_stats(slot: str, rarity: str, rng: random.Random) -> dict:
    """Roll base stats for an item given its slot and rarity."""
    _ensure_loaded()
    base = _LOOT_TABLES["base_stats"][slot]
    budget = _LOOT_TABLES["stat_budgets"].get(rarity, _LOOT_TABLES["stat_budgets"]["common"])

    def _roll_range(val):
        if isinstance(val, list):
            return rng.randint(val[0], val[1])
        return val

    damage = _roll_range(base["damage"])
    defense = _roll_range(base["defense"])
    weight = _roll_range(base["weight"])

    # Scale damage/defense by rarity budget
    rarity_mult = {"common": 1.0, "uncommon": 1.5, "rare": 2.0, "epic": 3.0, "legendary": 4.0}
    mult = rarity_mult.get(rarity, 1.0)
    damage = int(damage * mult)
    defense = int(defense * mult)

    # Cap to budget
    max_single = budget["max_single"]
    damage = min(damage, max_single)
    defense = min(defense, max_single)

    return {"damage": damage, "defense": defense, "weight": weight}


def _generate_item_name(slot: str, rarity: str, rng: random.Random) -> str:
    """Generate an item name from affixes."""
    _ensure_loaded()
    prefixes = _AFFIXES["prefixes"].get(rarity, _AFFIXES["prefixes"]["common"])
    suffixes = _AFFIXES["suffixes"].get(slot, [])

    prefix = rng.choice(prefixes)

    # Base names by slot
    bases = {
        "weapon": ["Sword", "Axe", "Dagger", "Mace", "Spear", "Bow", "Staff"],
        "armor": ["Shield", "Helm", "Breastplate", "Greaves", "Chainmail"],
        "accessory": ["Amulet", "Cloak", "Belt", "Boots", "Bracers"],
        "ring": ["Ring", "Band", "Signet"],
        "consumable": ["Potion", "Elixir", "Salve", "Tonic"],
    }
    base = rng.choice(bases.get(slot, bases["weapon"]))

    name = f"{prefix} {base}"
    if rarity in ("rare", "epic", "legendary") and suffixes:
        suffix = rng.choice(suffixes)
        name = f"{name} {suffix}"

    return name


def roll_loot(
    rarity_budget: str,
    num_items: int = 3,
    seed: int | None = None,
) -> list[dict]:
    """Roll items from loot tables.

    Args:
        rarity_budget: Budget tier (common, uncommon, rare).
        num_items: Number of items to generate.
        seed: Random seed for deterministic output.

    Returns:
        List of item dicts with name, rarity, slot, damage, defense, weight.
    """
    rng = random.Random(seed)
    items: list[dict] = []

    for _ in range(num_items):
        rarity = _roll_rarity(rarity_budget, rng)
        slot = _roll_slot(rng)
        stats = _roll_item_stats(slot, rarity, rng)
        name = _generate_item_name(slot, rarity, rng)

        items.append({
            "name": name,
            "rarity": rarity,
            "slot": slot,
            **stats,
        })

    return items
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/tools/procgen/test_stat_roller.py -v
```

Expected: All 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/tools/procgen/stat_roller.py engine/tests/tools/procgen/test_stat_roller.py
git commit -m "feat(procgen): add NPC stat roller and item loot roller from JSON tables"
```

---

## Task 6: Scaffold Injection into Crew Factories

**Files:**
- Modify: `engine/src/memento/crews/npc_gen/concept/crew.py:8`
- Modify: `engine/src/memento/crews/npc_gen/mechanics/crew.py:8`
- Modify: `engine/src/memento/crews/item_gen/concept/crew.py:9`
- Modify: `engine/src/memento/crews/item_gen/mechanics/crew.py:7`
- Modify: `engine/src/memento/crews/world_gen/region_design/crew.py:8`
- Modify: `engine/src/memento/crews/world_gen/location_planning/crew.py:7`
- Modify: `engine/src/memento/crews/world_gen/exit_connection/crew.py:8`
- Modify: `engine/src/memento/crews/narrative/narration/crew.py:9`

All changes follow the same pattern. Each crew factory gets a `scaffold: str = ""` parameter. If non-empty, it's appended to the **first** task's description.

- [ ] **Step 1: Read all 8 crew factory files**

Read each file to confirm the exact function signature and first task variable name. The subagent report says:
- `make_concept_crew(npc_role, location_name, region_context="")` — line 8
- `make_mechanics_crew(npc_concept)` — line 8
- `make_item_concept_crew(location_name, rarity_budget="common", num_items=3)` — line 9
- `make_item_mechanics_crew(item_concept)` — line 7
- `make_region_design_crew(theme, adjacent_regions="", player_level=1)` — line 8
- `make_location_planning_crew(region_concept)` — line 7
- `make_exit_connection_crew(locations, region_name)` — line 8
- `make_narration_crew(action, context, events, mode="action")` — line 9

- [ ] **Step 2: Add scaffold param to all 8 factories**

For each factory, the change is:

1. Add `scaffold: str = ""` as the last parameter
2. After the first `Task(...)` is created, append scaffold to its description

Example for `make_concept_crew`:

```python
# Before:
def make_concept_crew(npc_role: str, location_name: str, region_context: str = "") -> Crew:

# After:
def make_concept_crew(npc_role: str, location_name: str, region_context: str = "", scaffold: str = "") -> Crew:
```

And after the first task is defined:

```python
    # After concept_task = Task(...):
    if scaffold:
        concept_task.description += (
            "\n\nSCAFFOLD (use as starting point, modify freely, or discard if it doesn't fit):\n"
            + scaffold
        )
```

Apply this same pattern to all 8 factories. The variable name of the first task varies per file — read each to confirm.

- [ ] **Step 3: Verify all imports still work**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -c "
from memento.crews.npc_gen.concept import make_concept_crew
from memento.crews.npc_gen.mechanics import make_mechanics_crew
from memento.crews.item_gen.concept import make_item_concept_crew
from memento.crews.item_gen.mechanics import make_item_mechanics_crew
from memento.crews.world_gen.region_design import make_region_design_crew
from memento.crews.world_gen.location_planning import make_location_planning_crew
from memento.crews.world_gen.exit_connection import make_exit_connection_crew
from memento.crews.narrative.narration import make_narration_crew
print('All OK')
"
```

Expected: `All OK`

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/crews/
git commit -m "feat(procgen): add scaffold parameter to all generation crew factories"
```

---

## Task 7: Wire Scaffolds into NPC Generation Flow

**Files:**
- Modify: `engine/src/memento/flows/npc_gen.py:87,95`
- Test: `engine/tests/integration/test_scaffold_injection.py`

- [ ] **Step 1: Write failing test**

```python
# engine/tests/integration/test_scaffold_injection.py
"""Tests for scaffold injection into crew factories."""
import pytest
from unittest.mock import patch, MagicMock

from memento.crews.npc_gen.concept.crew import make_concept_crew
from memento.crews.npc_gen.mechanics.crew import make_mechanics_crew
from memento.crews.item_gen.concept.crew import make_item_concept_crew
from memento.crews.narrative.narration.crew import make_narration_crew


def test_concept_crew_scaffold_appears_in_task():
    crew = make_concept_crew(
        npc_role="tavern keeper",
        location_name="The Rusty Nail",
        scaffold="Name: Aldric Blackforge\nAppearance: A tall figure with a wiry frame.",
    )
    first_task = crew.tasks[0]
    assert "SCAFFOLD" in first_task.description
    assert "Aldric Blackforge" in first_task.description


def test_concept_crew_no_scaffold_no_injection():
    crew = make_concept_crew(
        npc_role="tavern keeper",
        location_name="The Rusty Nail",
    )
    first_task = crew.tasks[0]
    assert "SCAFFOLD" not in first_task.description


def test_mechanics_crew_scaffold_appears():
    crew = make_mechanics_crew(
        npc_concept="A grizzled warrior named Thorne.",
        scaffold="STR: 16, DEX: 12, CON: 15, INT: 8, WIS: 11, CHA: 9",
    )
    first_task = crew.tasks[0]
    assert "SCAFFOLD" in first_task.description
    assert "STR: 16" in first_task.description


def test_item_concept_crew_scaffold_appears():
    crew = make_item_concept_crew(
        location_name="Crypt of Shadows",
        scaffold="1. Worn Dagger (common, weapon)\n2. Simple Shield (common, armor)",
    )
    first_task = crew.tasks[0]
    assert "SCAFFOLD" in first_task.description
    assert "Worn Dagger" in first_task.description


def test_narration_crew_scaffold_appears():
    crew = make_narration_crew(
        action="look around",
        context="A dark crypt",
        events="none",
        scaffold="A distant drip echoes from the depths below. The stale air tastes of decay.",
    )
    first_task = crew.tasks[0]
    assert "SCAFFOLD" in first_task.description
    assert "distant drip" in first_task.description
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/integration/test_scaffold_injection.py -v
```

Expected: FAIL (scaffold param doesn't exist yet, or if Task 6 is done, should PASS)

- [ ] **Step 3: Wire scaffolds into NPC gen flow**

In `engine/src/memento/flows/npc_gen.py`, modify the `generate_npcs` method. Before the concept crew call (around line 87), generate scaffolds:

```python
# Add imports at top of generate_npcs method or file:
from memento.tools.procgen.text_gen import generate_npc_scaffold
from memento.tools.procgen.stat_roller import roll_npc_stats
import json

# Before concept_crew = make_concept_crew(...):
npc_scaffold = generate_npc_scaffold(
    role=f"NPC {i+1} from this plan:\n{roles}",
    location=self.state.location_name,
)

concept_crew = make_concept_crew(
    npc_role=f"NPC {i+1} from this plan:\n{roles}",
    location_name=self.state.location_name,
    region_context=self.state.region_context,
    scaffold=npc_scaffold,  # NEW
)
concept = concept_crew.kickoff().raw

# Before mech_crew = make_mechanics_crew(...):
# Try to infer archetype from concept text
archetype = "default"
for arch_name in ("warrior", "scholar", "merchant", "rogue", "healer", "guard", "innkeeper"):
    if arch_name in concept.lower():
        archetype = arch_name
        break
stat_scaffold = roll_npc_stats(archetype)
stat_text = json.dumps(stat_scaffold, indent=2)

mech_crew = make_mechanics_crew(
    npc_concept=concept,
    scaffold=f"Pre-rolled stats (adjust as needed):\n{stat_text}",  # NEW
)
```

- [ ] **Step 4: Verify import and no syntax errors**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -c "from memento.flows.npc_gen import NPCGenerationFlow; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Run scaffold injection tests**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/integration/test_scaffold_injection.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/flows/npc_gen.py engine/tests/integration/test_scaffold_injection.py
git commit -m "feat(procgen): wire NPC scaffolds into concept and mechanics crew calls"
```

---

## Task 8: Wire Scaffolds into Item Generation Flow

**Files:**
- Modify: `engine/src/memento/flows/item_gen.py:28,39`

- [ ] **Step 1: Read current item_gen.py**

Read `engine/src/memento/flows/item_gen.py` to confirm exact lines.

- [ ] **Step 2: Wire scaffolds into item gen flow**

Before the concept crew call, generate a loot scaffold:

```python
# Add import:
from memento.tools.procgen.stat_roller import roll_loot
import json

# Before crew = make_item_concept_crew(...):
loot_scaffold = roll_loot(
    rarity_budget=self.state.rarity_budget,
    num_items=self.state.num_items,
)
scaffold_text = "Pre-rolled items (refine names, add lore, adjust as needed):\n"
scaffold_text += json.dumps(loot_scaffold, indent=2)

crew = make_item_concept_crew(
    location_name=self.state.location_name,
    rarity_budget=self.state.rarity_budget,
    num_items=self.state.num_items,
    scaffold=scaffold_text,  # NEW
)
```

Before the mechanics crew call:

```python
crew = make_item_mechanics_crew(
    item_concept=concepts,
    scaffold="Stats were pre-rolled in the concept scaffold. Refine as needed.",  # NEW
)
```

- [ ] **Step 3: Verify import**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -c "from memento.flows.item_gen import ItemGenerationFlow; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/flows/item_gen.py
git commit -m "feat(procgen): wire loot table scaffolds into item generation flow"
```

---

## Task 9: Wire Scaffolds into World Generation Flow

**Files:**
- Modify: `engine/src/memento/flows/world_gen.py:42,54`

- [ ] **Step 1: Read current world_gen.py**

Read `engine/src/memento/flows/world_gen.py` to confirm exact lines.

- [ ] **Step 2: Wire scaffolds into region design**

Before the region design crew call:

```python
# Add import:
from memento.tools.procgen.text_gen import generate_location_scaffold

# Before crew = make_region_design_crew(...):
region_scaffold = generate_location_scaffold()

crew = make_region_design_crew(
    theme=self.state.theme,
    player_level=self.state.player_level,
    scaffold=f"Terrain sketch (use as inspiration):\n{region_scaffold}",  # NEW
)
```

Before location planning crew:

```python
crew = make_location_planning_crew(
    region_concept=region_concept,
    scaffold=f"Location atmosphere seeds:\n{generate_location_scaffold()}\n{generate_location_scaffold()}",  # NEW
)
```

- [ ] **Step 3: Verify import**

Run:
```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -c "from memento.flows.world_gen import WorldGenFlow; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/flows/world_gen.py
git commit -m "feat(procgen): wire location scaffolds into world generation flow"
```

---

## Task 10: Wire Scaffold into Narration Crew

**Files:**
- Modify: Where `make_narration_crew` is called (search for the call site)

- [ ] **Step 1: Find narration crew call site**

Search for where `make_narration_crew` is called in the codebase:

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && grep -rn "make_narration_crew" src/
```

- [ ] **Step 2: Wire scaffold at the call site**

At the call site, generate a narration scaffold:

```python
from memento.tools.procgen.text_gen import generate_narration_scaffold

scaffold = generate_narration_scaffold()
crew = make_narration_crew(
    action=action,
    context=context,
    events=events,
    mode=mode,
    scaffold=scaffold,  # NEW
)
```

- [ ] **Step 3: Verify import**

Run the same verify pattern as previous tasks.

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/
git commit -m "feat(procgen): wire narration scaffold into narrator crew calls"
```

---

## Task 11: Loot Table Designer Crew (mm_tool)

**Files:**
- Create: `engine/src/memento/crews/loot_designer/crew.py`
- Create: `engine/src/memento/crews/loot_designer/__init__.py`
- Create: `engine/src/memento/tools/mm_generate_loot_table.py`
- Test: `engine/tests/crews/test_loot_designer.py`
- Test: `engine/tests/tools/test_mm_generate_loot_table.py`

A crew that generates themed loot tables for specific locations/events, exposed as an `mm_generate_loot_table` tool that NPC agents and the engine can invoke. The crew uses `search_world` to understand the location context and produces a JSON loot table that gets merged into the static tables or used directly.

- [ ] **Step 1: Write failing tests for the mm_tool**

```python
# engine/tests/tools/test_mm_generate_loot_table.py
"""Tests for mm_generate_loot_table tool."""
import json
import pytest
from unittest.mock import patch, MagicMock
from memento.tools.mm_generate_loot_table import mm_generate_loot_table


@patch("memento.tools.mm_generate_loot_table._get_loot_designer_crew")
def test_mm_generate_loot_table_returns_json(mock_crew_fn):
    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = MagicMock(raw=json.dumps([
        {"name": "Crypt Blade", "rarity": "uncommon", "slot": "weapon", "damage": 6, "defense": 0, "weight": 5, "lore": "Forged in darkness"}
    ]))
    mock_crew_fn.return_value = mock_crew

    result = mm_generate_loot_table.run(
        location_name="Crypt of Shadows",
        theme="undead",
        num_items=3,
        rarity_budget="uncommon",
    )
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert len(parsed) >= 1
```

- [ ] **Step 2: Write failing tests for the crew**

```python
# engine/tests/crews/test_loot_designer.py
"""Tests for the Loot Designer crew."""
import pytest
from memento.crews.loot_designer.crew import make_loot_designer_crew


def test_make_loot_designer_crew_returns_crew():
    crew = make_loot_designer_crew(
        location_name="Crypt of Shadows",
        theme="undead",
        num_items=3,
        rarity_budget="uncommon",
    )
    assert crew is not None
    assert len(crew.agents) >= 1
    assert len(crew.tasks) >= 1


def test_loot_designer_crew_has_scaffold():
    crew = make_loot_designer_crew(
        location_name="Forest Clearing",
        theme="nature",
        num_items=5,
        rarity_budget="rare",
    )
    first_task = crew.tasks[0]
    assert "SCAFFOLD" in first_task.description or "Pre-rolled" in first_task.description
```

- [ ] **Step 3: Implement loot designer crew**

The crew uses the stat roller to pre-generate a scaffold, then has an LLM agent add thematic names, lore, and special effects.

- [ ] **Step 4: Implement mm_generate_loot_table tool**

A CrewAI `@tool` that constructs and kicks off the loot designer crew, returning the themed loot table JSON.

- [ ] **Step 5: Run tests, verify pass**
- [ ] **Step 6: Commit**

---

## Task 12: Full Test Suite Run

**Files:** None (verification only)

- [ ] **Step 1: Run all procgen tests**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/tools/procgen/ tests/integration/test_scaffold_injection.py -v
```

Expected: All tests pass.

- [ ] **Step 2: Run full art department + procgen test suite**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: No regressions.

- [ ] **Step 3: Verify all flow imports**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -c "
from memento.flows.npc_gen import NPCGenerationFlow
from memento.flows.item_gen import ItemGenerationFlow
from memento.flows.world_gen import WorldGenFlow
from memento.tools.procgen.text_gen import generate_npc_scaffold, generate_narration_scaffold, generate_location_scaffold
from memento.tools.procgen.stat_roller import roll_npc_stats, roll_loot
print('All imports OK')
"
```

Expected: `All imports OK`
