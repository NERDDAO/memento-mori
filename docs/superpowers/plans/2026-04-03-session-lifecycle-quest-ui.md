# Session Lifecycle & Quest UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add player resume with memorial dead characters, tutorial intro modal, loading screen gate, auto world bootstrap, and clickable quest detail dialog.

**Architecture:** Extract overlay management and session entry flow from app.ts into shared modules, then build 5 features on those foundations. Engine gains auto-seeding and character state restoration. Gateway's join endpoint returns full game state.

**Tech Stack:** TypeScript/Bun (client), Python/FastAPI (gateway/engine), Bonfires KG

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `client/src/ui/overlay.ts` | Create | Overlay visibility manager |
| `client/src/flows/session-flow.ts` | Create | Unified session entry sequence |
| `client/src/app.ts` | Modify | Remove enterWorld/enterWorldExisting, wire new modules |
| `client/src/state/session.ts` | Modify | Add joinSession(), return full response from initSession() |
| `client/src/panels/questlog.ts` | Modify | Register hit regions on quest rows |
| `client/src/ui/dialog.ts` | Modify | Add showQuest() method |
| `client/index.html` | Modify | Add loading + intro overlay divs, styles |
| `engine/src/memento/session.py` | Modify | Auto-seed in _find_starting_location, death info in get_user_characters, new restore_player_state |
| `gateway/src/gateway/routes/session.py` | Modify | Expand /session/join to return full state |

---

### Task 1: Overlay Manager

**Files:**
- Create: `client/src/ui/overlay.ts`

- [ ] **Step 1: Create overlay.ts**

```typescript
// client/src/ui/overlay.ts
/**
 * Named overlay manager — controls visibility of full-screen overlays.
 * Only one overlay is visible at a time.
 */

export interface OverlayManager {
  show(name: string): void;
  dismiss(name: string): void;
  onDismiss(name: string, cb: () => void): void;
  current(): string | null;
}

export function createOverlayManager(names: string[]): OverlayManager {
  const elements = new Map<string, HTMLElement>();
  const callbacks = new Map<string, Array<() => void>>();
  let currentName: string | null = null;

  for (const name of names) {
    const el = document.getElementById(`${name}-overlay`);
    if (el) elements.set(name, el);
    callbacks.set(name, []);
  }

  function show(name: string): void {
    // Hide current overlay if any
    if (currentName && currentName !== name) {
      const prev = elements.get(currentName);
      if (prev) prev.classList.add('hidden');
    }
    const el = elements.get(name);
    if (el) {
      el.classList.remove('hidden');
      currentName = name;
    }
  }

  function dismiss(name: string): void {
    const el = elements.get(name);
    if (el) el.classList.add('hidden');
    if (currentName === name) currentName = null;
    for (const cb of callbacks.get(name) || []) cb();
  }

  function onDismiss(name: string, cb: () => void): void {
    const list = callbacks.get(name);
    if (list) list.push(cb);
  }

  return {
    show,
    dismiss,
    onDismiss,
    current: () => currentName,
  };
}
```

- [ ] **Step 2: Verify build**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && bun build src/app.ts --outdir=. --target=browser 2>&1 | head -20`
Expected: No errors related to overlay.ts (it's not imported yet, just checking it compiles)

- [ ] **Step 3: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add client/src/ui/overlay.ts
git commit -m "feat(client): add overlay manager module"
```

---

### Task 2: World Bootstrap (Engine)

**Files:**
- Modify: `engine/src/memento/session.py:168-184`

- [ ] **Step 1: Update _find_starting_location to call seed_threshold**

In `engine/src/memento/session.py`, replace the `_find_starting_location` method:

```python
    def _find_starting_location(self) -> str:
        """Find an existing location or seed The Threshold.

        Searches KG for locations, preferring ones with room_map data.
        If no locations exist, auto-seeds The Threshold.
        """
        client = get_client()
        try:
            result = client.kg.search("tavern inn starting location", num_results=5)
            entities = result.get("entities", result.get("nodes", []))
            for entity in entities:
                labels = entity.get("labels", [])
                if "Location" in labels:
                    return entity.get("name", "The Threshold")
        except Exception:
            pass

        # No locations found — seed The Threshold
        try:
            from memento.seed import seed_threshold
            seed_result = seed_threshold()
            logger.info("Auto-seeded The Threshold: %s", seed_result.get("uuid", ""))
            return "The Threshold"
        except Exception:
            logger.warning("Auto-seed of The Threshold failed", exc_info=True)
            return "The Threshold"
```

- [ ] **Step 2: Verify engine imports work**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -c "from memento.session import SessionManager; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/session.py
git commit -m "feat(engine): auto-seed The Threshold on first player connect"
```

---

### Task 3: Player Resume — Engine (death info + restore state)

**Files:**
- Modify: `engine/src/memento/session.py:138-166`

- [ ] **Step 1: Add death detection to get_user_characters**

In `engine/src/memento/session.py`, replace the inner loop of `get_user_characters` (the `for edge in edges:` block starting at line 154):

```python
            characters = []
            for edge in edges:
                target = edge.get("target", {})
                if "Player" in target.get("labels", []):
                    player_id = target.get("uuid", target.get("id", ""))
                    char_info = {
                        "player_id": player_id,
                        "player_name": target.get("name", "Unknown"),
                        "archetype": target.get("archetype", ""),
                        "health": int(target.get("health", 100)),
                        "is_dead": False,
                        "death_cause": "",
                        "death_location": "",
                    }

                    # Check for death status
                    try:
                        status_edges = client.kg.get_edges(player_id, direction="outgoing", edge_type="HAS_STATUS")
                        for se in status_edges:
                            label = se.get("label", "")
                            if "DEAD" in label:
                                char_info["is_dead"] = True
                                char_info["death_cause"] = label.replace("DEAD. ", "")
                                break
                        if char_info["is_dead"]:
                            died_edges = client.kg.get_edges(player_id, direction="outgoing", edge_type="DIED_AT")
                            for de in died_edges:
                                death_target = de.get("target", {})
                                char_info["death_location"] = death_target.get("name", "unknown")
                                break
                    except Exception:
                        logger.debug("Death check failed for %s", player_id)

                    characters.append(char_info)
            return characters
```

- [ ] **Step 2: Add restore_player_state method**

Add this method to the `SessionManager` class, after `get_user_characters`:

```python
    def restore_player_state(self, player_id: str) -> dict:
        """Restore full game state for a returning player.

        Returns: {player_id, player_name, location_name, health, max_health, skills, inventory, room_map}
        """
        client = get_client()

        # Get player entity
        try:
            entity = client.kg.get_entity(player_id)
        except Exception:
            logger.warning("Failed to get player entity %s", player_id, exc_info=True)
            return {"player_id": player_id, "location_name": "The Threshold"}

        player_name = entity.get("name", "Unknown")
        health = int(entity.get("health", 100))
        max_health = int(entity.get("max_health", 100))
        archetype = entity.get("archetype", "")
        skills = {}
        try:
            skills = json.loads(entity.get("skills", "{}"))
        except (json.JSONDecodeError, TypeError):
            pass

        # Get location
        location_name = "The Threshold"
        room_map = None
        try:
            loc_edges = client.kg.get_edges(player_id, direction="outgoing", edge_type="LOCATED_IN")
            for le in loc_edges:
                loc_target = le.get("target", {})
                if "Location" in loc_target.get("labels", []):
                    location_name = loc_target.get("name", "The Threshold")
                    loc_uuid = loc_target.get("uuid", loc_target.get("id", ""))
                    # Try to get room_map from location entity
                    if loc_uuid:
                        try:
                            loc_entity = client.kg.get_entity(loc_uuid)
                            rm_raw = loc_entity.get("room_map")
                            if rm_raw:
                                room_map = json.loads(rm_raw) if isinstance(rm_raw, str) else rm_raw
                        except Exception:
                            pass
                    break
        except Exception:
            logger.debug("Location lookup failed for %s", player_id)

        # Get inventory
        inventory = []
        try:
            carry_edges = client.kg.get_edges(player_id, direction="outgoing", edge_type="CARRIES")
            for ce in carry_edges:
                item = ce.get("target", {})
                inventory.append(item.get("name", "Unknown Item"))
        except Exception:
            logger.debug("Inventory lookup failed for %s", player_id)

        return {
            "player_id": player_id,
            "player_name": player_name,
            "location_name": location_name,
            "health": health,
            "max_health": max_health,
            "archetype": archetype,
            "skills": skills,
            "inventory": inventory,
            "room_map": room_map,
        }
```

- [ ] **Step 3: Verify import**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -c "from memento.session import SessionManager; sm = SessionManager(); print(dir(sm))" 2>&1 | grep restore`
Expected: Output includes `restore_player_state`

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/session.py
git commit -m "feat(engine): add death info to character list and restore_player_state"
```

---

### Task 4: Player Resume — Gateway (expand /session/join)

**Files:**
- Modify: `gateway/src/gateway/routes/session.py:127-135`

- [ ] **Step 1: Expand join_session route**

Replace the `join_session` function and add a response model:

```python
class JoinSessionResponse(BaseModel):
    player_id: str
    session_id: str
    location: str
    health: int = 100
    max_health: int = 100
    archetype: str = ""
    skills: dict = {}
    inventory: list[str] = []
    room_map: dict | None = None


@router.post("/session/join", response_model=JoinSessionResponse)
async def join_session(req: JoinSessionRequest, request: Request):
    """Join an existing game session — restores full player state from KG."""
    try:
        from memento.session import SessionManager
        sm = SessionManager()
        result = await asyncio.to_thread(sm.restore_player_state, req.player_id)

        # Register Matrix user for presence
        from gateway.app import bridge
        if bridge and bridge.connected:
            player_name = result.get("player_name", "Unknown")
            await bridge.register_player(player_name, req.player_id)

        # Store player name for presence tracking
        from gateway.app import ws_hub
        if ws_hub:
            ws_hub.player_names[req.player_id] = result.get("player_name", "Unknown")

        return JoinSessionResponse(
            player_id=req.player_id,
            session_id=f"session-{req.player_id[:8]}",
            location=result.get("location_name", "The Threshold"),
            health=result.get("health", 100),
            max_health=result.get("max_health", 100),
            archetype=result.get("archetype", ""),
            skills=result.get("skills", {}),
            inventory=result.get("inventory", []),
            room_map=result.get("room_map"),
        )
    except Exception:
        logger.error("Session join failed, using fallback", exc_info=True)
        return JoinSessionResponse(
            player_id=req.player_id,
            session_id=f"session-{req.player_id[:8]}",
            location="The Threshold",
        )
```

- [ ] **Step 2: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add gateway/src/gateway/routes/session.py
git commit -m "feat(gateway): expand /session/join to return full player state"
```

---

### Task 5: Add joinSession to client session module

**Files:**
- Modify: `client/src/state/session.ts`

- [ ] **Step 1: Add joinSession function and export initSession response data**

Add this function after the existing `initSession` function in `client/src/state/session.ts`:

```typescript
export interface SessionCreateResponse {
  player_id: string;
  session_id: string;
  location: string;
  opening_narrative?: string;
  archetype?: string;
  health?: number;
  max_health?: number;
  skills?: Record<string, number>;
  inventory?: string[];
  room_map?: any;
}

export async function joinSession(playerId: string): Promise<SessionCreateResponse> {
  const resp = await fetch(`${GATEWAY_URL}/api/session/join`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_id: playerId }),
  });
  const data: SessionCreateResponse = await resp.json();

  session.playerId = data.player_id;
  session.sessionId = data.session_id;
  session.currentLocation = data.location;

  localStorage.setItem('mm_player_id', session.playerId);

  connectWebSocket();
  return data;
}
```

Also modify `initSession` to return the raw response data. Change the return section (lines 50-63) to:

```typescript
export async function initSession(playerName: string, walletAddress: string, archetype: string = ''): Promise<SessionCreateResponse> {
  const resp = await fetch(`${GATEWAY_URL}/api/session/create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_name: playerName, wallet_address: walletAddress, archetype }),
  });
  const data: SessionCreateResponse = await resp.json();
  session.playerId = data.player_id;
  session.sessionId = data.session_id;
  session.playerName = playerName;
  session.walletAddress = walletAddress;
  session.currentLocation = data.location;
  session.openingNarrative = data.opening_narrative || '';

  localStorage.setItem('mm_player_id', session.playerId);
  localStorage.setItem('mm_player_name', playerName);
  localStorage.setItem('mm_wallet', walletAddress);

  connectWebSocket();
  return data;
}
```

- [ ] **Step 2: Verify build**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && bun build src/app.ts --outdir=. --target=browser 2>&1 | head -20`
Expected: Build succeeds (app.ts uses `Session` type from initSession, which changes to `SessionCreateResponse` — update the one callsite in app.ts if needed)

- [ ] **Step 3: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add client/src/state/session.ts
git commit -m "feat(client): add joinSession and typed SessionCreateResponse"
```

---

### Task 6: Session Flow + Loading Screen + Intro Modal

**Files:**
- Create: `client/src/flows/session-flow.ts`
- Modify: `client/index.html` (add loading + intro overlays, styles)

- [ ] **Step 1: Add loading and intro overlay divs to index.html**

After the `death-overlay` div (line 499) and before the `<script>` tag, add:

```html
  <div id="loading-overlay" class="hidden">
    <h1 style="color: var(--accent); font-size: 24px; letter-spacing: 4px;">MEMENTO MORI</h1>
    <p class="loading-dots" style="color: var(--text-dim);">Entering the world</p>
  </div>
  <div id="intro-overlay" class="hidden">
    <div class="intro-content">
      <div class="intro-page" data-page="0">
        <h2 style="color: var(--accent); letter-spacing: 2px;">WELCOME TO MEMENTO MORI</h2>
        <p>A permadeath MUD where your actions shape a living world.<br>Every choice matters. Every death is final.</p>
      </div>
      <div class="intro-page hidden" data-page="1">
        <h2 style="color: var(--accent); letter-spacing: 2px;">ROUNDS & ACTIONS</h2>
        <p>Type commands in the input bar at the bottom.<br>Actions are batched into rounds. NPCs and the world respond to what you do.<br>Watch the status bar for the current round phase.</p>
      </div>
      <div class="intro-page hidden" data-page="2">
        <h2 style="color: var(--accent); letter-spacing: 2px;">PERMADEATH</h2>
        <p>When you die, it is permanent.<br>Your character becomes a memorial — a ghost in the world's history.<br>Connect your wallet to begin a new life.</p>
      </div>
      <div class="intro-nav">
        <button id="intro-skip-btn">Skip</button>
        <span id="intro-dots" style="color: var(--text-dim);"></span>
        <button id="intro-next-btn">Next</button>
      </div>
    </div>
  </div>
```

- [ ] **Step 2: Add styles for loading and intro overlays**

In the `<style>` section of `index.html`, after the death-overlay styles (around line 366), add:

```css
    /* Loading overlay */
    #loading-overlay {
      position: fixed; inset: 0; background: var(--bg-primary);
      display: flex; align-items: center; justify-content: center; z-index: 200;
      flex-direction: column; gap: 16px;
    }
    .loading-dots::after { content: ''; animation: dots 1.5s steps(4,end) infinite; }

    /* Intro overlay */
    #intro-overlay {
      position: fixed; inset: 0; background: var(--bg-primary);
      display: flex; align-items: center; justify-content: center; z-index: 200;
    }
    .intro-content {
      max-width: 480px; text-align: center; padding: 32px;
    }
    .intro-content h2 { margin-bottom: 16px; font-size: 18px; }
    .intro-content p { color: var(--text-dim); line-height: 1.8; font-size: 14px; }
    .intro-nav {
      display: flex; justify-content: space-between; align-items: center;
      margin-top: 32px;
    }
    .intro-nav button {
      background: none; border: 1px solid var(--border); color: var(--text-primary);
      padding: 6px 20px; font-family: inherit; cursor: pointer;
    }
    .intro-nav button:hover { border-color: var(--accent); }
    #intro-dots { letter-spacing: 4px; }
```

- [ ] **Step 3: Create session-flow.ts**

```typescript
// client/src/flows/session-flow.ts
/**
 * Unified session entry — both new and returning players flow through startGame().
 * Manages the loading → intro → game overlay sequence.
 */

import { initSession, joinSession, setConnectionHandler, getSession, type SessionCreateResponse } from '../state/session';
import { createInitialState, applyStateUpdate, type GameState } from '../state/game-state';
import { updateRoundState } from '../state/round-state';
import type { OverlayManager } from '../ui/overlay';

export interface StartGameConfig {
  playerName: string;
  walletAddress: string;
  isReturning: boolean;
  playerId?: string;
  archetype?: string;
}

export interface GameCallbacks {
  onGameReady: (state: GameState, openingNarrative: string) => void;
}

export async function startGame(
  config: StartGameConfig,
  overlays: OverlayManager,
  callbacks: GameCallbacks,
): Promise<void> {
  // 1. Show loading overlay
  overlays.show('loading');

  // 2. Create or join session
  let data: SessionCreateResponse;
  if (config.isReturning && config.playerId) {
    const session = getSession();
    session.playerName = config.playerName;
    session.walletAddress = config.walletAddress;
    localStorage.setItem('mm_player_name', config.playerName);
    localStorage.setItem('mm_wallet', config.walletAddress);
    data = await joinSession(config.playerId);
  } else {
    data = await initSession(config.playerName, config.walletAddress, config.archetype || '');
  }

  // 3. Build game state from response
  const gameState = createInitialState(config.playerName);
  gameState.location.name = data.location;
  if (data.archetype) gameState.player.archetype = data.archetype;
  if (data.health) gameState.player.health = data.health;
  if (data.max_health) gameState.player.maxHealth = data.max_health;
  if (data.skills) gameState.player.skills = data.skills as Record<string, number>;
  if (data.room_map) applyStateUpdate(gameState, { room_map: data.room_map });
  if (data.inventory) {
    gameState.inventory = data.inventory.map(name => ({ name, rarity: 'common', equipped: false }));
  }

  // 4. Wait for WebSocket connection
  await new Promise<void>((resolve) => {
    const session = getSession();
    if (session.connected) {
      resolve();
      return;
    }
    const prevHandler = null;
    setConnectionHandler((connected) => {
      if (connected) resolve();
    });
  });

  // 5. Dismiss loading
  overlays.dismiss('loading');

  // 6. Show intro for first-time players
  if (!localStorage.getItem('mm_intro_seen')) {
    overlays.show('intro');
    await new Promise<void>((resolve) => {
      initIntroNav(() => {
        localStorage.setItem('mm_intro_seen', 'true');
        overlays.dismiss('intro');
        resolve();
      });
    });
  }

  // 7. Hand off to app
  updateRoundState({ type: 'phase', phase: 'ready', location: data.location });
  callbacks.onGameReady(gameState, data.opening_narrative || (config.isReturning ? `Welcome back, ${config.playerName}.` : ''));
}

/** Wire up the intro modal's Next/Skip buttons. */
function initIntroNav(onDone: () => void): void {
  const pages = document.querySelectorAll('.intro-page');
  const dotsEl = document.getElementById('intro-dots');
  const nextBtn = document.getElementById('intro-next-btn');
  const skipBtn = document.getElementById('intro-skip-btn');
  let current = 0;
  const total = pages.length;

  function updateDots(): void {
    if (dotsEl) {
      dotsEl.textContent = Array.from({ length: total }, (_, i) => i === current ? '\u25CF' : '\u25CB').join(' ');
    }
  }

  function showPage(idx: number): void {
    pages.forEach((p, i) => {
      (p as HTMLElement).classList.toggle('hidden', i !== idx);
    });
    current = idx;
    updateDots();
    if (nextBtn) nextBtn.textContent = idx >= total - 1 ? 'Begin' : 'Next';
  }

  nextBtn?.addEventListener('click', () => {
    if (current >= total - 1) {
      onDone();
    } else {
      showPage(current + 1);
    }
  });

  skipBtn?.addEventListener('click', () => onDone());

  showPage(0);
}
```

- [ ] **Step 4: Verify build**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && bun build src/app.ts --outdir=. --target=browser 2>&1 | head -20`
Expected: Build succeeds (session-flow.ts not imported yet by app.ts)

- [ ] **Step 5: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add client/src/flows/session-flow.ts client/index.html
git commit -m "feat(client): add session flow, loading screen, and intro modal"
```

---

### Task 7: Wire Everything into app.ts

**Files:**
- Modify: `client/src/app.ts`

This is the largest task — it replaces `enterWorld`, `enterWorldExisting`, and the scattered overlay management with the new modules.

- [ ] **Step 1: Add imports**

At the top of `app.ts`, add these imports (after the existing imports around line 27):

```typescript
import { createOverlayManager } from './ui/overlay';
import { startGame } from './flows/session-flow';
import { joinSession, type SessionCreateResponse } from './state/session';
```

- [ ] **Step 2: Delete getThresholdMap**

Remove the entire `getThresholdMap()` function (lines 79-120). This hardcoded map is no longer needed — the engine returns room_map via session response.

- [ ] **Step 3: Create overlay manager in DOMContentLoaded**

After the status bar mount (line 462), add:

```typescript
  // Overlay manager
  const overlays = createOverlayManager(['char-create', 'death', 'loading', 'intro']);
```

- [ ] **Step 4: Replace enterWorld and enterWorldExisting**

Remove both functions (lines 327-420). Replace with:

```typescript
// --- Enter game (new or returning) ---
function enterGame(config: { playerName: string; walletAddress: string; isReturning: boolean; playerId?: string; archetype?: string }): void {
  startGame(
    { ...config },
    overlays,
    {
      onGameReady(state, openingNarrative) {
        gameState = state;
        if (gameState.roomMap) registerMapEntities(gameState.roomMap);
        renderAllPanels();
        if (openingNarrative) {
          narrative.addBlock(openingNarrative, config.isReturning ? 'system' : 'narrative');
        }
        (document.getElementById('action-input') as HTMLInputElement).focus();
      },
    },
  );
}
```

- [ ] **Step 5: Update showCharacterPicker for memorial dead characters**

Replace `showCharacterPicker` (lines 356-393) with:

```typescript
function showCharacterPicker(characters: any[], walletAddress: string): void {
  const walletStepEl = document.getElementById('wallet-step')!;
  const pickerDiv = document.createElement('div');
  pickerDiv.id = 'char-picker';

  const alive = characters.filter((c: any) => !c.is_dead);
  const dead = characters.filter((c: any) => c.is_dead);

  let html = '<div class="picker-title">Your Characters</div>';

  // Living characters
  for (const c of alive) {
    html += `
      <div class="picker-card" data-player-id="${c.player_id}">
        <span class="picker-name">${c.player_name}</span>
        <span class="picker-info">${c.archetype || 'Unknown'} \u00B7 HP ${c.health}</span>
      </div>`;
  }

  // Memorial (dead) characters
  for (const c of dead) {
    html += `
      <div class="picker-card picker-memorial">
        <span class="picker-name">\u2620 ${c.player_name}</span>
        <span class="picker-info">${c.death_cause || 'Perished'} \u00B7 Fell at ${c.death_location || 'unknown'}</span>
      </div>`;
  }

  html += `
    <div class="picker-card picker-new">
      <span class="picker-name">+ New Character</span>
    </div>`;

  pickerDiv.innerHTML = html;
  walletStepEl.after(pickerDiv);

  pickerDiv.addEventListener('click', (e: MouseEvent) => {
    const card = (e.target as HTMLElement).closest('.picker-card') as HTMLElement | null;
    if (!card || card.classList.contains('picker-memorial')) return;
    if (card.classList.contains('picker-new')) {
      pickerDiv.remove();
      const archStep = document.getElementById('archetype-step');
      if (archStep) {
        archStep.classList.remove('hidden');
        loadArchetypes();
      } else {
        document.getElementById('name-step')!.classList.remove('hidden');
      }
    } else {
      const playerId = card.dataset.playerId!;
      const playerName = card.querySelector('.picker-name')!.textContent || 'Wanderer';
      pickerDiv.remove();
      overlays.dismiss('char-create');
      enterGame({ playerName, walletAddress, isReturning: true, playerId });
    }
  });
}
```

- [ ] **Step 6: Update enterBtn click handler**

Replace the `enterBtn.addEventListener` and `nameInput.addEventListener` blocks (lines 658-670) with:

```typescript
  enterBtn.addEventListener('click', () => {
    const name = nameInput.value.trim() || 'Wanderer';
    const wallet = getAddress();
    if (wallet) {
      overlays.dismiss('char-create');
      enterGame({ playerName: name, walletAddress: wallet, isReturning: false, archetype: selectedArchetype });
    }
  });

  nameInput.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      const name = nameInput.value.trim() || 'Wanderer';
      const wallet = getAddress();
      if (wallet) {
        overlays.dismiss('char-create');
        enterGame({ playerName: name, walletAddress: wallet, isReturning: false, archetype: selectedArchetype });
      }
    }
  });
```

- [ ] **Step 7: Update death restart to use overlay manager**

Replace the death restart handler (lines 581-594) with:

```typescript
  document.getElementById('death-restart-btn')!.addEventListener('click', () => {
    overlays.dismiss('death');
    overlays.show('char-create');
    narrative = initNarrative(narrativeWin.body);
    narrative.canvas.addEventListener('narrative-entity-click', (e: Event) => {
      const { entityId, entityName } = (e as CustomEvent).detail;
      if (entityName) {
        if (entityId) wiki.show(entityId, entityName);
        else wiki.showByName(entityName);
      }
    });
    (document.getElementById('char-name-input') as HTMLInputElement).focus();
  });
```

- [ ] **Step 8: Update showDeathScreen to use overlay manager**

Replace `showDeathScreen` function (lines 130-143) with:

```typescript
function showDeathScreen(cause: string): void {
  const causeEl = document.getElementById('death-cause')!;
  const statsEl = document.getElementById('death-stats')!;

  causeEl.textContent = cause || 'The world continues without you.';
  statsEl.innerHTML = gameState ? `
    <div>Name: ${gameState.player.name}</div>
    <div>Level: ${gameState.player.level}</div>
    <div>Last Location: ${gameState.location.name}</div>
  ` : '';

  overlays.show('death');
}
```

- [ ] **Step 9: Add memorial picker styles to index.html**

In the `<style>` section of `index.html`, after `.picker-new` styles (line 443), add:

```css
    .picker-memorial { opacity: 0.4; cursor: default; border-color: var(--text-damage); }
    .picker-memorial .picker-name { color: var(--text-damage); }
    .picker-memorial .picker-info { color: var(--text-dim); font-style: italic; }
```

- [ ] **Step 10: Verify build**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && bun build src/app.ts --outdir=. --target=browser 2>&1 | head -20`
Expected: Build succeeds with no errors

- [ ] **Step 11: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add client/src/app.ts client/index.html
git commit -m "feat(client): wire overlay manager, session flow, memorial picker into app"
```

---

### Task 8: Quest Interface — Hit Regions + Dialog Extension

**Files:**
- Modify: `client/src/panels/questlog.ts`
- Modify: `client/src/ui/dialog.ts`
- Modify: `client/src/app.ts` (wire click handler)

- [ ] **Step 1: Add hit regions to questlog.ts**

Replace the `renderQuestLogPanel` function in `client/src/panels/questlog.ts`:

```typescript
export function renderQuestLogPanel(panel: TerminalPanel, quests: QuestEntry[]): void {
  const cols = panel.cols;
  const cells: CharCell[][] = [];

  panel.clearHitRegions();

  if (!quests || quests.length === 0) {
    cells.push(textRow('No active quests', theme.colors.dim, cols));
    panel.paint(cells);
    return;
  }

  for (let i = 0; i < quests.length; i++) {
    const q = quests[i];
    if (i > 0) cells.push(emptyRow(cols));

    const questStartRow = cells.length;

    // Quest name + done marker
    const nameSegs: Array<{ text: string; fg: string; attrs?: number }> = [
      { text: q.name, fg: q.completed ? theme.colors.dim : theme.colors.primary, attrs: 1 },
    ];
    if (q.completed) {
      nameSegs.push({ text: ' [DONE]', fg: theme.colors.heal });
    }
    cells.push(coloredRow(nameSegs, cols));

    // Giver
    if (q.giver) {
      cells.push(coloredRow([
        { text: 'from ', fg: theme.colors.dim },
        { text: q.giver, fg: theme.colors.npc },
      ], cols));
    }

    // Progress bar
    const progress = q.totalStages > 0 ? Math.round((q.currentStage / q.totalStages) * 10) : 0;
    const filled = Math.min(10, Math.max(0, progress));
    const empty = 10 - filled;
    const stageText = ` ${q.currentStage}/${q.totalStages}`;

    cells.push(coloredRow([
      { text: '\u2588'.repeat(filled), fg: theme.colors.accent },
      { text: '\u2591'.repeat(empty), fg: theme.colors.dim },
      { text: stageText, fg: theme.colors.primary },
    ], cols));

    // Description (truncated)
    if (q.description) {
      const desc = q.description.length > 60 ? q.description.slice(0, 57) + '...' : q.description;
      cells.push(textRow(desc, theme.colors.dim, cols));
    }

    // Register hit region for the entire quest entry
    const questEndRow = cells.length;
    panel.registerHitRegion({
      col: 0,
      row: questStartRow,
      width: cols,
      height: questEndRow - questStartRow,
      data: { questName: q.name },
    });
  }

  panel.paint(cells);
}
```

- [ ] **Step 2: Add showQuest to dialog.ts**

In `client/src/ui/dialog.ts`, update the `Dialog` interface and add `showQuest`:

```typescript
export interface Dialog {
  el: HTMLElement;
  show(npcName: string, npcRole: string, text: string): void;
  showQuest(quest: { name: string; description: string; currentStage: number; totalStages: number; giver: string; completed: boolean }): void;
  dismiss(): void;
  readonly active: boolean;
}
```

Then add the `showQuest` method inside `createDialog()`, after the existing `show` method (after line 87):

```typescript
    showQuest(quest: { name: string; description: string; currentStage: number; totalStages: number; giver: string; completed: boolean }) {
      if (currentTw) currentTw.cancel();

      const status = quest.completed ? ' [COMPLETE]' : '';
      titleBar.textContent = `\u2500 ${quest.name}${status} \u2500`;
      body.innerHTML = '';
      backdrop.style.display = '';

      // Build quest detail text
      const lines: string[] = [];
      if (quest.giver) lines.push(`Quest giver: ${quest.giver}`);
      lines.push('');
      lines.push(quest.description);
      lines.push('');
      const filled = quest.totalStages > 0 ? Math.round((quest.currentStage / quest.totalStages) * 10) : 0;
      const bar = '\u2588'.repeat(Math.min(10, filled)) + '\u2591'.repeat(10 - Math.min(10, filled));
      lines.push(`Progress: ${bar} ${quest.currentStage}/${quest.totalStages}`);

      const text = lines.join('\n');

      currentTw = createTypewriter({
        text,
        font: DIALOG_FONT,
        maxWidth: DIALOG_MAX_WIDTH,
        container: body,
        charDelay: 15,
        lineClass: 'tw-line',
        cursorClass: 'tw-cursor',
      });
      currentTw.onComplete(() => { currentTw = null; });
      currentTw.start();
    },
```

- [ ] **Step 3: Wire quest click handler in app.ts**

In `app.ts`, after the `presentWin.panel!.canvas.addEventListener` block (around line 472), add:

```typescript
  questWin.panel!.canvas.addEventListener('panel-click', (e: Event) => {
    const detail = (e as CustomEvent).detail;
    if (detail.questName && gameState) {
      const quest = gameState.quests.find(q => q.name === detail.questName);
      if (quest) npcDialog.showQuest(quest);
    }
  });
```

- [ ] **Step 4: Verify build**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && bun build src/app.ts --outdir=. --target=browser 2>&1 | head -20`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add client/src/panels/questlog.ts client/src/ui/dialog.ts client/src/app.ts
git commit -m "feat(client): clickable quest log entries with detail dialog"
```

---

### Task 9: End-to-End Verification

- [ ] **Step 1: Build client**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && bun build src/app.ts --outdir=. --target=browser`
Expected: Build succeeds with no errors

- [ ] **Step 2: Check for TypeScript errors**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && bunx tsc --noEmit 2>&1 | head -30`
Expected: No type errors (or only pre-existing ones)

- [ ] **Step 3: Verify engine imports**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -c "from memento.session import SessionManager; sm = SessionManager(); print('create_player' in dir(sm), 'restore_player_state' in dir(sm))"`
Expected: `True True`

- [ ] **Step 4: Verify gateway routes**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/gateway && python -c "from gateway.routes.session import router; routes = [r.path for r in router.routes]; print(routes)"`
Expected: List includes `/session/create`, `/session/join`, `/session/characters`, `/archetypes`

- [ ] **Step 5: Manual smoke test**

Start the game with `./start.sh --dev` and verify:
1. First load shows loading overlay, then intro tutorial, then game
2. Returning with same wallet shows character picker
3. Dead characters appear as memorials (skull + dimmed)
4. Clicking quest entries opens the dialog with quest details
5. Overlay transitions are smooth (no stuck overlays)

- [ ] **Step 6: Final commit if any fixes needed**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add -A
git commit -m "fix: address e2e verification issues"
```
