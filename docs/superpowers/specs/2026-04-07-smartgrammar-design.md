# SmartGrammar — Context-Aware Grammar Generation

**Date:** 2026-04-07
**Status:** Draft
**Repo:** New standalone repo (github.com/soulfir/smartgrammar)

## Problem

Random text generation from grammars produces structurally correct but contextually incoherent output. LLM-based generation is coherent but expensive. There's no middle ground that gives you grammar-enforced structure with context-aware content selection.

## Solution

A Python library that combines Tracery-style grammars with embedding-based selection. Grammar rules define structure (enforced). Embeddings select the most contextually appropriate expansion at each level (cascading). Optional: auto-build grammars from raw text corpora via n-gram extraction + clustering + LLM crew curation.

## Three Operations

### 1. Build (corpus → grammar)

```
Raw text corpus
  → n-gram extraction (2/3/4-grams, frequency counted)
  → embed all n-grams
  → cluster by cosine similarity (HDBSCAN)
  → (optional) crew pass: name clusters, prune, define hierarchy
  → Tracery-format grammar JSON
```

### 2. Index (grammar → searchable)

```
Grammar JSON (Tracery format)
  → for each rule, embed all expansions
  → build FAISS index per rule
  → store indices alongside grammar
```

### 3. Generate (context → structured text)

```
Context string ("dark crypt, eerie mood")
  → embed context
  → walk grammar tree top-down:
      at each rule node:
        query FAISS index with current context
        pick expansion (top-1 or temperature-weighted sample)
        append chosen expansion to context for next level
  → output: structurally enforced, contextually coherent text
```

## Cascading Context

The key mechanism. At each grammar level, the chosen expansion feeds into the context for the next level:

```
Context: "dark crypt, eerie mood"

origin → pick "#sensory#. #atmosphere#." (best match for context)
  sensory → pick "#sound# echoes from #direction#" 
    sound → pick "Chains rattle" (fits crypt context)
    direction → pick "the depths below" (fits crypt + chains)
  atmosphere → pick "The #air_quality# air tastes of #smell#"
    air_quality → pick "stale" (fits crypt + chains + depths)  
    smell → pick "decay" (fits everything above)

Output: "Chains rattle echoes from the depths below. The stale air tastes of decay."
```

Grammar structure is always enforced. Content is selected by semantic relevance cascading through the tree.

## Variety Control

```python
generate(grammar, context, temperature=0.0)  # deterministic, most relevant
generate(grammar, context, temperature=0.5)  # weighted sample from top-5
generate(grammar, context, temperature=1.0)  # uniform random (classic Tracery behavior)
generate(grammar, context, seed=42)          # reproducible
```

## Embedder

```python
class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

Ships with:
- **MiniLMEmbedder** (default) — `sentence-transformers/all-MiniLM-L6-v2`, ~80MB, pip install, no external service
- **OllamaEmbedder** — auto-detected if Ollama running, uses `nomic-embed-text` or configured model

Selection: try Ollama first, fall back to MiniLM.

## Package Structure

```
smartgrammar/
  __init__.py        — public API: build, index, generate, SmartGrammar class
  grammar.py         — load/save Tracery JSON, rule tree traversal, expansion parsing
  embedder.py        — Embedder protocol + MiniLM + Ollama adapters
  index.py           — FAISS index per grammar rule, embed/store/query
  generator.py       — cascading context-aware expansion with temperature
  builder.py         — n-gram extraction, HDBSCAN clustering, crew hook
  cli.py             — CLI: smartgrammar build|index|generate
tests/
  test_grammar.py
  test_embedder.py
  test_index.py
  test_generator.py
  test_builder.py
  test_integration.py
```

## Public API

```python
from smartgrammar import SmartGrammar

# Grammar-first path
sg = SmartGrammar.from_file("narration.json")
sg.index()  # embed all rules
text = sg.generate(context="dark crypt, eerie mood", temperature=0.3)

# Corpus-first path
sg = SmartGrammar.build_from_corpus(texts=["line1", "line2", ...])
sg.index()
text = sg.generate(context="forest clearing, peaceful")

# Add new entries (self-improving)
sg.add("sound", "Bones crunch underfoot")  # auto-embeds and indexes

# Save/load with indices
sg.save("narration.sg")  # grammar JSON + FAISS indices
sg = SmartGrammar.load("narration.sg")
```

## CLI

```bash
# Build grammar from corpus
smartgrammar build --input corpus.txt --output grammar.json

# Index existing grammar
smartgrammar index grammar.json

# Generate text
smartgrammar generate grammar.json --context "dark crypt" --temperature 0.3

# Add entry to rule
smartgrammar add grammar.json sound "Bones crunch underfoot"
```

## Dependencies

```toml
dependencies = [
    "sentence-transformers>=2.0",
    "faiss-cpu>=1.7",
    "numpy>=1.24",
    "hdbscan>=0.8",
]

[project.optional-dependencies]
ollama = ["ollama>=0.1"]
crew = ["crewai>=0.100"]  # for builder crew pass
```

## File Format

`.sg` files are directories (or zip archives) containing:
```
grammar.sg/
  grammar.json      — Tracery-format rules
  meta.json          — embedder info, dimension, rule count
  indices/
    sound.faiss      — FAISS index for "sound" rule
    direction.faiss
    atmosphere.faiss
    ...
```

## Integration with Memento Mori

Replace `text_gen.py`'s random Tracery expansion with SmartGrammar:

```python
# Before (random):
from memento.tools.procgen.text_gen import generate_narration_scaffold

# After (context-aware):
from smartgrammar import SmartGrammar
narration_sg = SmartGrammar.load("engine/assets/atlas/grammars/narration.sg")
scaffold = narration_sg.generate(context=f"{biome}, {mood}", temperature=0.3)
```

The `update_grammar` tool calls `sg.add()` which auto-embeds and re-indexes.

## Testing

- Grammar loading/saving: round-trip Tracery JSON
- Embedder: MiniLM produces correct dimensionality, Ollama adapter formats requests correctly
- Index: embed N items, query returns correct nearest neighbor
- Generator: cascading context produces deterministic output with seed, temperature=0 always returns same result, temperature=1 has variety
- Builder: n-gram extraction counts correctly, HDBSCAN produces clusters from synthetic data
- Integration: full pipeline from corpus → grammar → indexed → generate
