# mm_look Grantable + LOOK Grammar — Callability Prerequisites (Slice 1, Plan 4 of N)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax. Spec: `docs/superpowers/specs/2026-06-26-agent-driven-opening-cxn-catch-design.md` (**Components D + E**). This plan delivers the two *mechanical, independently-testable prerequisites* that make `mm_look` callable: (D) `mm_look` is in the agent-runtime manifest + granted by `get_allowed_tools`, and (E) the kernel can comprehend "look around" → LOOK because the grammar is authored at boot. **Component B (player-as-persona)** — the new player-self path — is deliberately NOT here: its `gm_self`/turn-issuance semantics need a design decision, so it gets its own Plan 5.

**Goal:** Make `mm_look` a granted, in-manifest tool any persona can call, and author the verb-only LOOK construction on the kernel at bring-up so "look around" comprehends to LOOK (confidence 1.0, Phase-0 proven).

**Architecture:** Three tasks across two repos. (1) agent-runtime: add `mm_look` as a *free* `CxnToolSpec` to `MEMENTO_MANIFEST` — because free specs are always retained by `CapabilitySet.from_tool_names`, every persona's shared manifest gains `mm_look` with no per-roster wiring. (2) engine: add `mm_look` to `INNATE_TOOLS` so `get_allowed_tools(labels)` reports it (the `capabilities` list the gateway computes stays accurate). (3) engine + gateway: add an `author_grammar` method to `HttpComprehensionClient` + a gated, non-fatal gateway-boot call that authors the LOOK construction.

**Tech Stack:** bonfires-ai-core agent-runtime = Python / pytest (`asyncio_mode="auto"`, no decorator), `uv run pytest`, **no `Any` in service signatures**. memento-mori engine+gateway = Python / pytest (`@pytest.mark.asyncio` where async), `httpx` (MockTransport for the client test).

## Branches & bases (TWO repos)

- **bonfires-ai-core (Task 1):** continue on the existing branch `cxn-catch/cxn-fired` (HEAD `d3d9ae3` after Plan 3 Task 1), worktree `<scratchpad>/core-cxn-fired`. New commit on the same branch.
- **memento-mori (Tasks 2 + 3):** branch `opening/cxn-catch` (HEAD `8b10f4e` after Plan 3), worktree `<scratchpad>/mmori-cxn-catch`.

## Global Constraints

- Commit trailer (exact, every commit, both repos): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Never `git add -A`** — stage only the files each task touches.
- **bonfires-ai-core rules:** No `Any` in service signatures. Feature-branch only. `ruff format` before commit. PRs target staging (out of scope here). Every code-changing change gets a `docs/migration/CHANGELOG.md` entry.
- `mm_look` is declared a **free** tool spec (empty `unlock_cxn_ids`) — that is load-bearing: `CapabilitySet.from_tool_names` always retains free specs, so the player-self (and every persona) can call `mm_look` without it being named in any `capabilities` list. Do NOT give it `unlock_cxn_ids`.
- The grammar authoring is **opt-in + non-fatal**: gated on `KERNEL_BASE_URL`+`GM_INTERNAL_TOKEN` (the same env `HttpComprehensionClient` needs), wrapped so a kernel outage at boot never crashes startup. `os.environ` reads stay in the gateway.
- The LOOK construction is the **Phase-0-proven verb-only spec** (dodges the FCG closure-balloon): `{"construct_id":"mm.look.v1","name":"LOOK","predicate":"look","lemmas":["look"],"roles":[],"lexicon":[],"form":[{"role":"verb"}]}`.
- Ruff-format only the files each task touches.

## Key existing symbols (verbatim anchors)

### bonfires-ai-core (agent-runtime) — paths under `services/agent-runtime/`
- **`CxnToolSpec`** — `src/app/modules/tools/builtin/cxn_tools.py:52`: `@dataclass(frozen=True)` with `name: str`, `description: str`, `params: list[str]`, `unlock_cxn_ids: tuple[str, ...] = ()`. A free spec is the 3-arg positional form (no `unlock_cxn_ids`).
- **`MEMENTO_MANIFEST`** — `src/app/adapters/cxn_gateway/manifests/memento.py:6` (the `specs=[...]` list; free specs at `:9`/`:35` e.g. `CxnToolSpec("mm_act", "...", ["text"])`). `MEMENTO_TOOL_NAMES` (`:39`) is derived from `specs` automatically.
- **`CapabilitySet.from_tool_names`** — `src/app/adapters/cxn_gateway/manifests/capability_set.py:34`. `:40-47`: free specs (`unlock_cxn_ids == ()`) are ALWAYS retained: `specs = tuple(spec for spec in MEMENTO_MANIFEST.specs if not spec.unlock_cxn_ids or spec.name in wanted)`.
- **Tests with EXACT-SET assertions (load-bearing — must update):**
  - `tests/test_cxn_tools_factory.py:24` — `expected_names = {"mm_attack","mm_move","mm_take","mm_bolt","mm_get_state","mm_act","mm_search_world"}` then `assert names == expected_names` and `assert len(tools) == len(MEMENTO_MANIFEST.specs)`. Add `"mm_look"`.
  - `tests/test_capability_set.py:138` — `test_from_tool_names_empty_list_is_free_only` uses `== {"mm_get_state","mm_search_world","mm_act"}` (exact). Add `"mm_look"`. (`:129` uses `<=`, so it tolerates the extra, but adding `"mm_look"` there too is consistent.)
  - Also run the full suite and fix any OTHER exact-set manifest/free-tool assertion that now includes `mm_look` (candidates: `test_memento_inloop_gating.py`, `test_cxn_tool_manifest_unlock.py`, `test_memento_capabilities.py`).
- **Test runner:** from `services/agent-runtime/`, run via the main repo's venv (the worktree lacks the external `memory_kernel` dep): `PYTHONPATH=src <main-venv>/bin/python -m pytest tests/test_cxn_tools_factory.py tests/test_capability_set.py -q`, OR `uv run pytest ...` if the env resolves. Confirm green on the untouched branch first.

### memento-mori engine — `engine/src/memento/tools/tool_labels.py`
- `INNATE_TOOLS = frozenset({...})` at `:16` — current members: `mm_get_state, mm_get_world_time, mm_search_world, mm_get_entity, mm_skill_check, mm_calculate_damage, mm_evaluate_disposition, mm_npc_response, mm_send_gossip, mm_npc_memory`. **No `mm_look`.**
- `get_allowed_tools(labels)` at `:155`: `allowed = set(INNATE_TOOLS)` unioned with `KITS[label]`/`LABEL_TOOLS[label]`. Opening players carry `labels:["Character"]`, which hits no KIT → INNATE only. So adding `mm_look` to `INNATE_TOOLS` is the way to grant it to the player (and to every embodied agent — perception is innate).
- **Test with EXACT-SET INNATE assertion (must update):** `engine/tests/state/test_gate_label_parity.py:53-54` asserts `get_allowed_tools(["Character"]) == INNATE` (i.e. the exact INNATE set). Run the suite and update any test that pins INNATE contents (also check `engine/tests/unit/test_kit_edit.py`).

### memento-mori engine — `engine/src/memento/cxn/kernel_client.py`
- `HttpComprehensionClient.__init__` (`:73-95`): `_base_url`, `_token`, `_bonfire_id` (default `"mm-world-v1"`), `_client: httpx.AsyncClient | None`. Raises `ValueError` if base_url/token unset. `comprehend` (`:97-143`) POSTs `f"{self._base_url}/v1/bonfires/{self._bonfire_id}/kernel/comprehend"` with headers `{X-Internal-Token, X-Permission: read, Content-Type}`, using `self._client` if injected else a fresh `httpx.AsyncClient()`; raises `ComprehendError` on non-200. `ComprehendError` imported from `memento.cxn.types`.

### memento-mori gateway — `gateway/src/gateway/app.py`
- Lifespan sets `app.state.bonfire_id = resolve_bonfire_id()`; gated `PERSONA_*` / `OPENING_ROOM_SEED` boot blocks each `await`ed and (for KG/opening) wrapped non-fatal `try/except … logger.warning(..., exc_info=True)`. `import os` + `logger` present. The new authoring block follows that exact pattern.

## File Structure

- bonfires-ai-core: `manifests/memento.py` (+`mm_look` spec), `tests/test_cxn_tools_factory.py` + `tests/test_capability_set.py` (+ any other exact-set test), `docs/migration/CHANGELOG.md`.
- engine: `tools/tool_labels.py` (+`mm_look` in INNATE), `tests/state/test_gate_label_parity.py` (+ any INNATE exact-set test).
- engine + gateway: `cxn/kernel_client.py` (+`author_grammar` + `LOOK_CONSTRUCTION`), `gateway/look_tool.py` (+`seed_look_grammar` helper), `gateway/app.py` (+gated boot block), `engine/tests/.../test_kernel_client_author.py` (new) + `gateway/tests/test_look_grammar_boot.py` (new).

---

# Task 1 — agent-runtime: `mm_look` as a free manifest spec (bonfires-ai-core)

**Files:**
- Modify: `services/agent-runtime/src/app/adapters/cxn_gateway/manifests/memento.py`
- Modify: `services/agent-runtime/tests/test_cxn_tools_factory.py`, `tests/test_capability_set.py` (+ any other exact-set manifest test the suite flags)
- Modify: `docs/migration/CHANGELOG.md`

**Interfaces:**
- Produces: `mm_look` present in `MEMENTO_MANIFEST.specs` as a free spec → auto-retained by `CapabilitySet.from_tool_names` for every persona.

- [ ] **Step 0 — baseline:** from `services/agent-runtime/`, confirm `tests/test_cxn_tools_factory.py` + `tests/test_capability_set.py` are green on the untouched branch (use the venv invocation from the anchors).

- [ ] **Step 1 — add the free `mm_look` spec** to the `specs=[...]` list in `memento.py` (place it beside the other free specs, e.g. after `mm_act`):
```python
    CxnToolSpec(
        "mm_look",
        "Look around the current room — reveal the next notable thing, or look closer at something already seen.",
        [],
    ),
```
  *(No `unlock_cxn_ids` → free → always retained. No params. `MEMENTO_TOOL_NAMES` updates automatically.)*

- [ ] **Step 2 — update the exact-set tests.** In `tests/test_cxn_tools_factory.py:24`, add `"mm_look"` to `expected_names`. In `tests/test_capability_set.py:138` (`test_from_tool_names_empty_list_is_free_only`), add `"mm_look"` to the expected free-only set; in `:129`, add `"mm_look"` to the asserted free subset for consistency.

- [ ] **Step 3 — run, find any other exact-set failures:**
```bash
# from services/agent-runtime/, using the working invocation
<runner> -m pytest tests/test_cxn_tools_factory.py tests/test_capability_set.py tests/test_memento_inloop_gating.py tests/test_cxn_tool_manifest_unlock.py tests/test_memento_capabilities.py -q
```
  Fix any remaining exact-set assertion that must now include `mm_look` (the spec count went 7→8; free-tool sets gained `mm_look`). Do NOT relax a `==` to `<=` — add `mm_look` to the expected set.

- [ ] **Step 4 — verify green:** the above command passes.

- [ ] **Step 5 — CHANGELOG entry** (`docs/migration/CHANGELOG.md`, current phase): `agent-runtime: added mm_look as a free (always-retained) CxnToolSpec in MEMENTO_MANIFEST so personas can look around; no construction payload (read-only)`.

- [ ] **Step 6 — ruff-format + commit** (stage only the touched files):
```bash
cd services/agent-runtime && uv run ruff format src/app/adapters/cxn_gateway/manifests/memento.py tests/test_cxn_tools_factory.py tests/test_capability_set.py
cd <repo-root> && git add services/agent-runtime/src/app/adapters/cxn_gateway/manifests/memento.py services/agent-runtime/tests/test_cxn_tools_factory.py services/agent-runtime/tests/test_capability_set.py docs/migration/CHANGELOG.md
# add any other test file Step 3 required
git commit -m "feat(agent-runtime): add mm_look as a free manifest tool spec

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Task 2 — engine: `mm_look` in `INNATE_TOOLS` (memento-mori)

**Files:**
- Modify: `engine/src/memento/tools/tool_labels.py`
- Modify: `engine/tests/state/test_gate_label_parity.py` (+ any other INNATE exact-set test)

**Interfaces:**
- Produces: `get_allowed_tools(labels)` includes `mm_look` for every entity → the gateway-computed `capabilities` lists report it accurately.

- [ ] **Step 1 — add `mm_look` to `INNATE_TOOLS`** (`tool_labels.py:16`), in the frozenset (alphabetical-ish, beside the other `mm_get_*`/perception tools):
```python
    "mm_look",
```

- [ ] **Step 2 — update INNATE exact-set tests.** In `engine/tests/state/test_gate_label_parity.py` (the assertion that `get_allowed_tools(["Character"]) == INNATE` / pins the INNATE contents), add `"mm_look"` to the expected set. Run the suite and update any other test pinning INNATE contents (`engine/tests/unit/test_kit_edit.py`).

- [ ] **Step 3 — run, verify:**
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest engine/tests/state/test_gate_label_parity.py engine/tests/unit/test_kit_edit.py -q
```
Expected: green (the INNATE set now contains `mm_look`).

- [ ] **Step 4 — ruff-format + commit:**
```bash
python3.12 -m ruff format engine/src/memento/tools/tool_labels.py engine/tests/state/test_gate_label_parity.py
git add engine/src/memento/tools/tool_labels.py engine/tests/state/test_gate_label_parity.py
# add test_kit_edit.py only if Step 2 changed it
git commit -m "feat(engine): grant mm_look as an innate tool (get_allowed_tools)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Task 3 — author the LOOK grammar at gateway boot (memento-mori)

**Files:**
- Modify: `engine/src/memento/cxn/kernel_client.py` (add `author_grammar` + `LOOK_CONSTRUCTION`)
- Modify: `gateway/src/gateway/look_tool.py` (add `seed_look_grammar` helper)
- Modify: `gateway/src/gateway/app.py` (gated, non-fatal boot block)
- Test: `engine/tests/cxn/test_kernel_client_author.py` (new), `gateway/tests/test_look_grammar_boot.py` (new)

**Interfaces:**
- Produces: `HttpComprehensionClient.author_grammar(constructions) -> bool` (POST `/v1/bonfires/{id}/kernel/author-grammar`, X-Permission: write). Module-level `LOOK_CONSTRUCTION: dict`. `seed_look_grammar(bonfire_id) -> bool` (gateway helper, builds the client + authors `[LOOK_CONSTRUCTION]`). The lifespan calls `seed_look_grammar(app.state.bonfire_id)` gated + non-fatal.

- [ ] **Step 1 — add `LOOK_CONSTRUCTION` + `author_grammar`** to `engine/src/memento/cxn/kernel_client.py`. Add the constant near the top (after the logger):
```python
# The Phase-0-proven verb-only LOOK construction (dodges the FCG closure-balloon).
LOOK_CONSTRUCTION: dict[str, Any] = {
    "construct_id": "mm.look.v1",
    "name": "LOOK",
    "predicate": "look",
    "lemmas": ["look"],
    "roles": [],
    "lexicon": [],
    "form": [{"role": "verb"}],
}
```
  And add this method to `HttpComprehensionClient` (after `comprehend`):
```python
    async def author_grammar(self, constructions: list[dict[str, Any]]) -> bool:
        """POST constructions to kernel/author-grammar (X-Permission: write).

        Idempotent server-side. Returns True on 200; raises ComprehendError on
        any non-200 or network error (the caller wraps it non-fatal at boot).
        """
        url = f"{self._base_url}/v1/bonfires/{self._bonfire_id}/kernel/author-grammar"
        body: dict[str, Any] = {"constructions": constructions}
        headers = {
            "X-Internal-Token": self._token,
            "X-Permission": "write",
            "Content-Type": "application/json",
        }
        try:
            if self._client is not None:
                response = await self._client.post(url, json=body, headers=headers)
            else:
                async with httpx.AsyncClient() as http:
                    response = await http.post(url, json=body, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ComprehendError(f"kernel/author-grammar network error: {exc}") from exc
        if response.status_code != 200:
            raise ComprehendError(
                f"kernel/author-grammar returned {response.status_code} for bonfire={self._bonfire_id}",
                status_code=response.status_code,
            )
        return True
```

- [ ] **Step 2 — failing engine test** (`engine/tests/cxn/test_kernel_client_author.py`) using `httpx.MockTransport`:
```python
import httpx
import pytest

from memento.cxn.kernel_client import LOOK_CONSTRUCTION, HttpComprehensionClient


@pytest.mark.asyncio
async def test_author_grammar_posts_look_construction():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["perm"] = request.headers.get("X-Permission")
        seen["token"] = request.headers.get("X-Internal-Token")
        import json
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    c = HttpComprehensionClient(base_url="http://k", token="tok", bonfire_id="bf-1", client=client)
    ok = await c.author_grammar([LOOK_CONSTRUCTION])
    assert ok is True
    assert seen["url"] == "http://k/v1/bonfires/bf-1/kernel/author-grammar"
    assert seen["perm"] == "write" and seen["token"] == "tok"
    assert seen["body"]["constructions"][0]["construct_id"] == "mm.look.v1"
    assert seen["body"]["constructions"][0]["form"] == [{"role": "verb"}]


@pytest.mark.asyncio
async def test_author_grammar_raises_on_non_200():
    from memento.cxn.types import ComprehendError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "nope"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    c = HttpComprehensionClient(base_url="http://k", token="tok", bonfire_id="bf-1", client=client)
    with pytest.raises(ComprehendError):
        await c.author_grammar([LOOK_CONSTRUCTION])
```

- [ ] **Step 3 — run, verify pass:**
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest engine/tests/cxn/test_kernel_client_author.py -q
```
Expected: 2 passed. *(If `engine/tests/cxn/` has no `__init__.py` and sibling cxn tests use one, match the layout.)*

- [ ] **Step 4 — add the `seed_look_grammar` helper** to `gateway/src/gateway/look_tool.py` (append below `seed_opening_room`):
```python
async def seed_look_grammar(bonfire_id: str) -> bool:
    """Author the verb-only LOOK construction on the kernel for ``bonfire_id`` so
    "look around" comprehends to LOOK. Gated on the kernel env by the caller and
    wrapped non-fatal — a kernel outage at boot must not crash startup."""
    from memento.cxn.kernel_client import LOOK_CONSTRUCTION, HttpComprehensionClient

    client = HttpComprehensionClient(bonfire_id=bonfire_id)
    return await client.author_grammar([LOOK_CONSTRUCTION])
```
  Then add the gated boot block to `gateway/src/gateway/app.py`, after the `OPENING_ROOM_SEED` block (before `# Seed NPC registry`):
```python
    if os.environ.get("KERNEL_BASE_URL") and os.environ.get("GM_INTERNAL_TOKEN") and os.environ.get("OPENING_AUTHOR_LOOK_GRAMMAR"):
        from gateway.look_tool import seed_look_grammar

        try:
            await seed_look_grammar(app.state.bonfire_id)
            logger.info("authored LOOK grammar on bonfire %s", app.state.bonfire_id)
        except Exception:
            logger.warning("LOOK grammar authoring failed (non-fatal)", exc_info=True)
```
  *(Gated on the kernel env AND an explicit `OPENING_AUTHOR_LOOK_GRAMMAR` flag so non-kernel/test boots never attempt it. Non-fatal — a kernel outage at boot must not crash startup. `HttpComprehensionClient()` inside the helper reads `KERNEL_BASE_URL`/`GM_INTERNAL_TOKEN` from env itself.)*

- [ ] **Step 5 — failing gateway test** (`gateway/tests/test_look_grammar_boot.py`) — test the real `seed_look_grammar` helper by patching the client at its SOURCE module (the helper late-imports `HttpComprehensionClient` from `memento.cxn.kernel_client`, so patch it there):
```python
import pytest

from memento.cxn.kernel_client import LOOK_CONSTRUCTION


@pytest.mark.asyncio
async def test_seed_look_grammar_authors_look_construction(monkeypatch):
    calls = []

    class _StubClient:
        def __init__(self, *a, **k):
            self.bonfire_id = k.get("bonfire_id")
        async def author_grammar(self, constructions):
            calls.append(constructions)
            return True

    import memento.cxn.kernel_client as kc
    monkeypatch.setattr(kc, "HttpComprehensionClient", _StubClient)

    from gateway.look_tool import seed_look_grammar

    ok = await seed_look_grammar("bf-1")
    assert ok is True
    assert calls == [[LOOK_CONSTRUCTION]]
    assert calls[0][0]["construct_id"] == "mm.look.v1"
```
  *(This exercises real production code — `seed_look_grammar` builds the client and authors the real `LOOK_CONSTRUCTION`. The inline lifespan block that calls the helper is exercised only when the three env flags are set, which the gated-boot pattern keeps out of the default test path; an integration test against a live kernel is deferred to bring-up.)*

- [ ] **Step 6 — run, verify pass:**
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_look_grammar_boot.py engine/tests/cxn/test_kernel_client_author.py -q
```
Expected: 3 passed.

- [ ] **Step 7 — regression smoke** (app boot + kernel client unaffected):
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_mcp_server.py engine/tests/cxn -q
```
Expected: green.

- [ ] **Step 8 — ruff-format + commit:**
```bash
python3.12 -m ruff format engine/src/memento/cxn/kernel_client.py gateway/src/gateway/look_tool.py gateway/src/gateway/app.py engine/tests/cxn/test_kernel_client_author.py gateway/tests/test_look_grammar_boot.py
git add engine/src/memento/cxn/kernel_client.py gateway/src/gateway/look_tool.py gateway/src/gateway/app.py engine/tests/cxn/test_kernel_client_author.py gateway/tests/test_look_grammar_boot.py
git commit -m "feat(cxn): author the verb-only LOOK grammar at gateway boot (gated)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Verification (end-to-end)

1. **Manifest (Task 1):** `mm_look` is a free `CxnToolSpec` in `MEMENTO_MANIFEST` → `CapabilitySet.from_tool_names` retains it for every persona regardless of their `capabilities` list. Exact-set manifest/capability tests updated (spec count 7→8).
2. **Kit (Task 2):** `get_allowed_tools(labels)` includes `mm_look` (via `INNATE_TOOLS`) → the gateway-computed `capabilities` accurately list it. INNATE exact-set tests updated.
3. **Grammar (Task 3):** `HttpComprehensionClient.author_grammar` POSTs the verb-only LOOK construction (X-Permission: write) to `/kernel/author-grammar`; a gated, non-fatal gateway-boot block authors it when `KERNEL_BASE_URL`+`GM_INTERNAL_TOKEN`+`OPENING_AUTHOR_LOOK_GRAMMAR` are set. Client test (MockTransport, 200 + 403) + boot-contract test.
4. **Together:** with Plan 3's `fired_cxns` plumbing already in place, the only remaining gap to a *real* (non-stubbed) "look around → LOOK fires → ◇ caught: LOOK + mm_look runs" is **Component B (player-as-persona)** — Plan 5.

## What this plan deliberately does NOT do (Plan 5 / later)

- **Plan 5 — Component B (player-as-persona):** seeding the player with persona-capable labels, building the player `SelfDto` (seat=LLM), and POSTing `/v1/scenes/{deep_roads}/open` with the player in the roster — including the design decision on `gm_self` semantics for a *player-driven* opening scene (the scene manifest is built only from the GM persona today; there is no GM in the opening) and how the narrator auto-issues the "look around" turn. This is NOT mechanical and needs a brief design beat before planning — hence its own plan.
- **Plan 6:** the cinematic intro (epigraph fade + name box), the client `room_draw` glyph rendering, and retiring the legacy overlay.
- **Bonfire-document / api-contract / kernel-deployment provisioning** beyond authoring the grammar (which bonfire id the live agent-runtime comprehends against must match the authored one — a deployment-config concern).
