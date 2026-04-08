# Art Department — Procgen + LLM Crew Pipeline

**Date:** 2026-04-07
**Status:** Draft

## Problem

The current ASCII art crew (`crews/ascii_art/crew.py`) generates all art from scratch via LLM — no structural scaffolding, no reusable assets, no procgen. This causes:

- Dimensional compliance issues (artist fights the blank canvas, needs validate→revise loops)
- No pixel sprite capability (everything is ASCII text)
- No asset reuse — every generation is a cold start
- Art generation is only triggered by enrichment; NPC/item/map flows don't produce art as a first-class output

## Design Goals

1. **Procgen scaffolds** for LLM artists — WFC terrain layouts, cellular automata silhouettes
2. **Dual-medium output** — ASCII for terrain/maps/UI, pixel sprites for portraits/items
3. **Build-time atlas** for common assets, on-demand generation for named entities
4. **Art as entity attributes** — stored directly on KG nodes
5. **Subprocess integration** — NPC, item, and map generation crews spawn art crews

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   Art Department                     │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ Cartographer  │  │ Portraitist  │  │ Ambient FX │ │
│  │ (ASCII maps)  │  │ (pixel spr.) │  │ (overlay)  │ │
│  └──────┬───────┘  └──────┬───────┘  └─────┬──────┘ │
│         │                  │                │        │
│  ┌──────┴──────────────────┴────────────────┴──────┐ │
│  │              Procgen Toolkit                     │ │
│  │  WFC engine · cellular automata · templates ·    │ │
│  │  palette system · sprite rasterizer              │ │
│  └──────────────────────────────────────────────────┘ │
│                                                      │
│  ┌──────────────────────────────────────────────────┐ │
│  │              Asset Atlas (build-time)             │ │
│  │  Common tiles · generic sprites · icon set        │ │
│  └──────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
         │                  │                │
    ┌────┴───┐        ┌────┴───┐       ┌────┴───┐
    │ world  │        │  npc   │       │  item  │
    │ gen    │        │  gen   │       │  gen   │
    │ flow   │        │  flow  │       │  flow  │
    └────────┘        └────────┘       └────────┘
```

## Medium Split

| Layer | Medium | Procgen Source | LLM Role | Output Attribute |
|-------|--------|---------------|----------|-----------------|
| Terrain / room scenes | ASCII (35×20) | WFC tile composition | Detail pass — atmosphere, narrative elements | `scene_art`, `scene_art_w`, `scene_art_h` |
| Map glyphs | ASCII (single char) | Biome lookup table | None | `tile_glyph`, `tile_fg` |
| Entity portraits | Pixel sprite (16-32px) | Cellular automata silhouette | Feature description → re-roll/select | `portrait_sprite`, `portrait_size` |
| Item icons | Pixel sprite (8-16px) | Template mask randomization | Palette/style selection | `icon_sprite`, `icon_size` |
| UI borders / frames | Box-drawing ASCII | Template library | None | N/A (client-side) |
| Ambient FX | Procedural overlay | Noise/particle sim | None | Driven by `mood` attribute |

## KG Entity Attributes

Flat properties on entity nodes (Neo4j-friendly, no nested JSON):

```
# ASCII art (locations)
scene_art: str          # newline-joined ASCII lines
scene_art_w: int        # width in chars
scene_art_h: int        # height in chars

# Pixel sprites (NPCs, items)
portrait_sprite: str    # base64-encoded PNG
portrait_w: int         # pixel width (16 or 32)
portrait_h: int         # pixel height (16 or 32)

# Small icons (items, map markers)
icon_sprite: str        # base64-encoded PNG
icon_w: int             # pixel width (8 or 16)
icon_h: int             # pixel height (8 or 16)

# Map tile (all entities that appear on map)
tile_glyph: str         # single character for map rendering
tile_fg: str            # hex color string

# Metadata
art_style: str          # "dark_fantasy" — for palette lookup
art_generated_at: str   # ISO timestamp
```

All sprites are small enough to inline: 32×32 RGBA PNG ≈ 2-4KB base64.

## Procgen Toolkit

### 1. WFC Terrain Engine (`tools/procgen/wfc.py`)

Generates structural ASCII scaffolds for location scenes.

**Input:** Tile ruleset (adjacency constraints) + dimensions + seed tags (biome, mood)
**Output:** ASCII grid with structural elements placed (walls, floors, doors, water, paths)

Tile categories:
- `wall`: `#`, `█`, `▓`
- `floor`: `.`, `·`, ` `
- `door`: `+`, `◊`
- `water`: `~`, `≈`
- `path`: `:`, `·`
- `vegetation`: `♣`, `↑`, `†`
- `border`: box-drawing set

The LLM artist receives this scaffold with instructions: "Preserve structural positions. Add atmospheric detail within floor/empty spaces. Swap generic chars for mood-appropriate variants."

**Implementation:** Python WFC solver. Small grid (35×20) means fast convergence. Adjacency rules defined per biome in a JSON config.

### 2. Cellular Automata Sprite Generator (`tools/procgen/sprite_gen.py`)

Generates pixel sprite silhouettes for entity portraits.

**Based on:** [soulfir/sprite-generator](https://github.com/soulfir/sprite-generator) — cellular automata with bilateral symmetry.

**Input:** Template mask (entity type: humanoid, beast, item) + size (16/32px) + color hints
**Output:** PIL Image → base64 PNG

Template masks define body regions:
- `humanoid`: head, torso, arms, legs
- `beast`: head, body, legs/tail
- `undead`: humanoid variant with decay regions
- `item_weapon`: blade + hilt
- `item_potion`: bottle shape
- `item_armor`: chest + shoulder regions

The LLM art director describes desired features ("skeletal warrior, hooded, carries scythe"). The procgen tool generates N candidates. The art director selects the best match or requests re-rolls with adjusted parameters.

### 3. Template Mask Library (`tools/procgen/templates/`)

JSON template masks for sprite generation:

```json
{
  "humanoid_16": {
    "size": [16, 16],
    "mask": [
      [0,0,0,0,0,1,1,1,1,0,0,0,0,0,0,0],
      ...
    ],
    "regions": {"head": 1, "torso": 2, "arms": 3, "legs": 4}
  }
}
```

### 4. Palette System (`tools/procgen/palette.py`)

Per-biome, per-mood color palettes enforced across all art output.

```python
PALETTES = {
    "crypt": {
        "primary": ["#2d2d3f", "#4a4a5e"],
        "accent": ["#8b0000", "#556b2f"],
        "light": ["#daa520", "#cd853f"],
    },
    "forest": {
        "primary": ["#1a3d1a", "#2d5a2d"],
        "accent": ["#8b4513", "#556b2f"],
        "light": ["#90ee90", "#98fb98"],
    },
    ...
}
```

Used by both sprite generator (pixel colors) and ASCII artist (ANSI color hints for `tile_fg`).

### 5. Sprite Validation (`tools/art_validation.py` — extended)

Add sprite validation alongside existing ASCII validation:

```python
@tool("validate_sprite")
def validate_sprite(sprite_b64: str, expected_w: int, expected_h: int, palette_name: str) -> str:
    """Validate sprite dimensions, transparency, and palette compliance."""
```

## Crew Architecture

### Cartographer Crew

Replaces current `make_scene_art_crew`. Receives WFC scaffold instead of blank canvas.

**Agents:**
- **Terrain Artist** — receives WFC scaffold + location description + mood → fills in atmospheric detail
- **Map Critic** — checks structural integrity preserved, mood consistency, readability

**Tools:** `generate_terrain_scaffold`, `validate_art`, `select_palette`

**Pipeline:**
1. `generate_terrain_scaffold` → structural ASCII grid
2. Artist detailing pass — adds narrative elements within scaffold constraints
3. Critic review — structural + atmospheric check
4. Revision if needed
5. Final validation

### Portraitist Crew

New crew for pixel sprite generation.

**Agents:**
- **Sprite Artist** — describes desired features, invokes sprite generator, selects from candidates
- **Style Critic** — checks palette compliance, silhouette readability, consistency with entity description

**Tools:** `generate_sprite_silhouette`, `validate_sprite`, `select_palette`

**Pipeline:**
1. Parse entity description → feature keywords
2. Select template mask (humanoid/beast/item)
3. `generate_sprite_silhouette` × N candidates
4. Artist selects best candidate (or re-rolls with adjusted params)
5. Style critic review
6. Final validation → base64 PNG

### Art Director (shared concern, not a separate crew)

Palette and style consistency is enforced via:
- `select_palette` tool available to all art crews
- Biome/mood tags on location entities drive palette selection
- Sprite templates are pre-mapped to entity labels (NPC→humanoid, Item→item_*)

No separate art director agent needed — this is tooling, not judgment.

## Integration Points

### NPC Generation Flow (`flows/npc_gen.py`)

Current pattern (background thread for art) is preserved, but routes to portraitist:

```python
# After finalization crew completes:
if uuid_match:
    threading.Thread(
        target=generate_entity_art,
        args=(uid, name, "npc", description, labels, region_biome),
        daemon=True,
    ).start()
```

`generate_entity_art` dispatches:
- Portraitist crew → `portrait_sprite`, `portrait_w`, `portrait_h`
- Existing ASCII art crew (now cartographer-style) → `scene_art` (if entity warrants it)
- Tile glyph assignment → `tile_glyph`, `tile_fg`

### Item Generation Flow (`flows/item_gen.py`)

Add background art thread after balance_check:

```python
# After balance crew completes:
for item in items:
    threading.Thread(
        target=generate_entity_art,
        args=(item_uid, item_name, "item", item_desc, item_labels, region_biome),
        daemon=True,
    ).start()
```

Portraitist runs in icon mode (8-16px template masks for weapons, potions, armor, etc.)

### World Generation Flow (`flows/world_gen.py`)

After `generate_locations`, spawn cartographer per location:

```python
# After location is persisted to KG:
threading.Thread(
    target=generate_location_art,
    args=(location_uid, location_name, description, mood, biome),
    daemon=True,
).start()
```

`generate_location_art`:
1. WFC scaffold from biome + mood
2. Cartographer crew detailing pass
3. Persist `scene_art`, `scene_art_w`, `scene_art_h`, `tile_glyph`, `tile_fg`

### Enrichment Flow (`flows/enrichment.py`)

Becomes the **fallback** for entities that missed art during generation. `enrich_entity_art()` checks for missing art attributes and dispatches to the appropriate crew.

Current `needs_art()` check is extended:

```python
def needs_art(entity) -> dict:
    """Return dict of missing art types."""
    missing = {}
    attrs = entity.get("attributes", {})
    labels = entity.get("labels", [])

    if "Location" in labels and not attrs.get("scene_art"):
        missing["scene"] = True
    if ("NPC" in labels or "Player" in labels) and not attrs.get("portrait_sprite"):
        missing["portrait"] = True
    if "Item" in labels and not attrs.get("icon_sprite"):
        missing["icon"] = True
    if not attrs.get("tile_glyph"):
        missing["tile"] = True

    return missing
```

## Shared Dispatcher (`flows/art_gen.py`)

Single entry point that all flows call:

```python
def generate_entity_art(
    entity_uid: str,
    name: str,
    entity_type: str,       # "npc", "item", "location"
    description: str,
    labels: list[str],
    biome: str = "default",
    mood: str = "dark",
) -> None:
    """Generate all art for an entity and persist to KG."""

    palette = select_palette(biome, mood)

    if entity_type == "location":
        # WFC scaffold → cartographer crew
        scaffold = generate_terrain_scaffold(biome, mood, width=35, height=20)
        crew = make_cartographer_crew(name, description, mood, scaffold, palette)
        result = crew.kickoff()
        # Parse and persist scene_art, tile_glyph, tile_fg

    elif entity_type == "npc":
        # Cellular automata → portraitist crew
        template = select_template(labels)  # humanoid, beast, undead
        candidates = [generate_sprite_silhouette(template, palette) for _ in range(4)]
        crew = make_portraitist_crew(name, description, candidates, palette)
        result = crew.kickoff()
        # Parse and persist portrait_sprite, tile_glyph, tile_fg

    elif entity_type == "item":
        # Template mask → portraitist crew (icon mode)
        template = select_item_template(labels)  # weapon, potion, armor
        candidates = [generate_sprite_silhouette(template, palette, size=8) for _ in range(4)]
        crew = make_portraitist_crew(name, description, candidates, palette, icon_mode=True)
        result = crew.kickoff()
        # Parse and persist icon_sprite, tile_glyph, tile_fg
```

## Asset Atlas (Build-Time)

A pre-generated library of common assets that don't need LLM involvement:

```
engine/assets/atlas/
  tiles/          # WFC tile definitions per biome
    crypt.json
    forest.json
    village.json
  sprites/        # Pre-rendered common sprites
    humanoid_base_16.png
    humanoid_base_32.png
    beast_base_16.png
    weapon_sword_8.png
    potion_generic_8.png
  palettes/       # Color palette definitions
    dark_fantasy.json
    per_biome.json
  templates/      # Sprite mask templates
    humanoid_16.json
    humanoid_32.json
    beast_16.json
    item_weapon_8.json
    item_potion_8.json
```

Generated by a build script (`scripts/generate_atlas.py`) that runs procgen tools without LLM involvement. Checked into the repo.

## Client Rendering

### ASCII Art (existing, minor changes)

`ascii-art-viewer.ts` already handles `string[] → canvas`. No changes needed for scene art. The `scene_art` attribute arrives via WS game state and renders through existing `drawAsciiArt`.

### Pixel Sprites (new)

New `sprite-renderer.ts` alongside `ascii-art-viewer.ts`:

```typescript
export function drawSprite(
  ctx: CanvasRenderingContext2D,
  x: number, y: number,
  spriteB64: string,
  scale: number = 2,  // 2x for crisp pixel art
): void {
  // Decode base64 → ImageBitmap → drawImage with imageSmoothingEnabled=false
}
```

Pretext's canvas supports this — `UnifiedCanvas` already has `PixelRendererEntry` for non-text content. Sprites render with nearest-neighbor scaling for the 8-bit crunch aesthetic.

### Ambient FX (future, not in initial scope)

Client-side procedural overlays driven by location `mood`:
- Rain: falling `·` and `|` characters
- Fog: semi-transparent `░` overlay
- Torchlight: flickering brightness on nearby cells

Deferred — not part of initial implementation.

## External Dependencies

| Dependency | Purpose | Integration |
|-----------|---------|-------------|
| [soulfir/sprite-generator](https://github.com/soulfir/sprite-generator) | Cellular automata sprite gen | Fork/adapt core algorithm into `tools/procgen/sprite_gen.py` |
| [MaartenGr/Sprite-Generator](https://github.com/MaartenGr/Sprite-Generator) | Template mask reference | Reference for mask design, not a direct dependency |
| Pillow | Image manipulation | Already in engine deps (if not, add) |
| NumPy | Matrix ops for WFC/CA | Already in engine deps |

No new infrastructure. No external services. Pure Python procgen + existing CrewAI framework.

## Scope

### Phase 1 (this spec)
- Procgen toolkit: WFC terrain, cellular automata sprites, palette system
- Cartographer crew (replaces current ASCII art crew for scenes)
- Portraitist crew (new, pixel sprites)
- Art dispatcher (`flows/art_gen.py`)
- Integration hooks in NPC, item, and world gen flows
- Client sprite renderer
- Asset atlas build script

### Phase 2 (future)
- Ambient FX overlay system
- Animated sprites (idle, walk cycles via sprite sheets)
- WFC-generated world maps (zoomed-out region view)
- Art style transfer between biomes (entity moves from forest to crypt, palette shifts)

## Testing

- Procgen tools: unit tests with fixed seeds for deterministic output
- Crew integration: test with mocked procgen (known scaffold → verify LLM receives it)
- Sprite validation: dimension, palette, transparency checks
- Atlas generation: build script runs in CI, validates all output assets
- Client rendering: visual regression tests for sprite scaling / ASCII display
