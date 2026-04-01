# Unified Text UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the HTML side panel with a unified text-based window UI using DOM + Pretext hybrid rendering, add a Pretext-animated NPC dialog, and add an engine-driven in-game time system displayed in a header bar.

**Architecture:** Every UI panel becomes a reusable `Window` component (DOM div styled as TUI). Pretext measures and line-breaks text inside windows for precise monospace layout. NPC dialog uses Pretext's `layoutNextLine` for character-by-character typewriter animation. A new CrewAI tool in the engine tracks in-game time.

**Tech Stack:** TypeScript/Bun (client), @chenglou/pretext (text measurement), Python/CrewAI/Pydantic (engine), FastAPI (gateway)

**Spec:** `docs/superpowers/specs/2026-04-01-unified-text-ui-design.md`

---

## Task 1: Window Component

**Files:**
- Create: `client/src/ui/window.ts`

- [ ] **Step 1: Create the Window component**

```ts
// client/src/ui/window.ts
export interface WindowOptions {
  title: string;
  id?: string;
  className?: string;
  scrollable?: boolean;
}

export interface Window {
  el: HTMLElement;
  body: HTMLElement;
  setTitle(title: string): void;
  show(): void;
  hide(): void;
  toggle(): void;
  readonly visible: boolean;
}

export function createWindow(opts: WindowOptions): Window {
  const el = document.createElement('div');
  el.className = `win${opts.className ? ` ${opts.className}` : ''}`;
  if (opts.id) el.id = opts.id;

  const titleBar = document.createElement('div');
  titleBar.className = 'win-title';
  titleBar.textContent = `\u2500 ${opts.title} \u2500`;

  const body = document.createElement('div');
  body.className = 'win-body';
  if (opts.scrollable) body.style.overflowY = 'auto';

  el.appendChild(titleBar);
  el.appendChild(body);

  return {
    el,
    body,
    setTitle(title: string) {
      titleBar.textContent = `\u2500 ${title} \u2500`;
    },
    show() { el.style.display = ''; },
    hide() { el.style.display = 'none'; },
    toggle() { el.style.display = el.style.display === 'none' ? '' : 'none'; },
    get visible() { return el.style.display !== 'none'; },
  };
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && bun build src/ui/window.ts --outdir /tmp/test-build --no-bundle 2>&1 | head -5`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add client/src/ui/window.ts
git commit -m "feat(client): add reusable Window component for text UI"
```

---

## Task 2: Typewriter Animation Module

**Files:**
- Create: `client/src/ui/typewriter.ts`

- [ ] **Step 1: Create the typewriter module**

Uses Pretext's `prepareWithSegments` + `layoutNextLine` to break text into lines, then reveals characters incrementally into a DOM container.

```ts
// client/src/ui/typewriter.ts
import { prepareWithSegments, layoutNextLine, type LayoutCursor } from '@chenglou/pretext';

export interface TypewriterController {
  start(): void;
  skip(): void;
  cancel(): void;
  onComplete(cb: () => void): void;
}

export interface TypewriterOptions {
  text: string;
  font: string;
  maxWidth: number;
  container: HTMLElement;
  charDelay?: number;       // ms per character, default 25
  lineClass?: string;       // CSS class for each line div
  cursorClass?: string;     // CSS class for the blinking cursor span
}

export function createTypewriter(opts: TypewriterOptions): TypewriterController {
  const {
    text,
    font,
    maxWidth,
    container,
    charDelay = 25,
    lineClass = 'tw-line',
    cursorClass = 'tw-cursor',
  } = opts;

  let completeCb: (() => void) | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let cancelled = false;
  let started = false;

  // Pretext line-breaking
  const prepared = prepareWithSegments(text, font);
  const lines: string[] = [];
  let cursor: LayoutCursor = { segmentIndex: 0, graphemeIndex: 0 };
  while (true) {
    const line = layoutNextLine(prepared, cursor, maxWidth);
    if (!line) break;
    lines.push(line.text);
    cursor = line.end;
  }

  // State
  let lineIdx = 0;
  let charIdx = 0;
  let currentLineEl: HTMLElement | null = null;
  let cursorEl: HTMLElement | null = null;

  function ensureCursor() {
    if (!cursorEl) {
      cursorEl = document.createElement('span');
      cursorEl.className = cursorClass;
      cursorEl.textContent = '\u2588'; // full block cursor
    }
    return cursorEl;
  }

  function tick() {
    if (cancelled || lineIdx >= lines.length) {
      finish();
      return;
    }

    // Start a new line
    if (!currentLineEl) {
      currentLineEl = document.createElement('div');
      currentLineEl.className = lineClass;
      container.appendChild(currentLineEl);
    }

    // Reveal next character
    const line = lines[lineIdx];
    if (charIdx < line.length) {
      // Remove cursor, add char, re-add cursor
      ensureCursor().remove();
      currentLineEl.textContent = line.slice(0, charIdx + 1);
      currentLineEl.appendChild(ensureCursor());
      charIdx++;
      timer = setTimeout(tick, charDelay);
    } else {
      // Line complete — move to next
      ensureCursor().remove();
      lineIdx++;
      charIdx = 0;
      currentLineEl = null;
      timer = setTimeout(tick, charDelay);
    }
  }

  function finish() {
    if (cursorEl) cursorEl.remove();
    cursorEl = null;
    if (completeCb) completeCb();
  }

  function showAll() {
    if (timer) clearTimeout(timer);
    container.innerHTML = '';
    for (const line of lines) {
      const div = document.createElement('div');
      div.className = lineClass;
      div.textContent = line;
      container.appendChild(div);
    }
    finish();
  }

  return {
    start() {
      if (started) return;
      started = true;
      container.innerHTML = '';
      tick();
    },
    skip() {
      if (cancelled) return;
      showAll();
    },
    cancel() {
      cancelled = true;
      if (timer) clearTimeout(timer);
      if (cursorEl) cursorEl.remove();
    },
    onComplete(cb: () => void) {
      completeCb = cb;
    },
  };
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && bun build src/ui/typewriter.ts --outdir /tmp/test-build --no-bundle 2>&1 | head -5`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add client/src/ui/typewriter.ts
git commit -m "feat(client): add Pretext-powered typewriter animation module"
```

---

## Task 3: Header Component

**Files:**
- Create: `client/src/ui/header.ts`

- [ ] **Step 1: Create the header component**

```ts
// client/src/ui/header.ts
export interface WorldTime {
  moon_phase: string;
  moon_icon: string;
  day_name: string;
  day_number: number;
  month: string;
  season: string;
  time_of_day: string;
}

export interface Header {
  el: HTMLElement;
  updateTime(time: WorldTime): void;
}

export function createHeader(): Header {
  const el = document.createElement('div');
  el.className = 'tui-header';
  el.innerHTML = `
    <span class="header-time">
      <span class="header-moon">\u263D</span>
      <span class="header-date">\u2014</span>
    </span>
    <span class="header-title">MEMENTO MORI</span>
  `;

  const moonEl = el.querySelector('.header-moon') as HTMLElement;
  const dateEl = el.querySelector('.header-date') as HTMLElement;

  return {
    el,
    updateTime(time: WorldTime) {
      moonEl.textContent = time.moon_icon;
      dateEl.textContent = `${time.moon_phase}  \u00B7  ${ordinal(time.day_number)} of ${time.month}  \u00B7  ${time.time_of_day}`;
    },
  };
}

function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && bun build src/ui/header.ts --outdir /tmp/test-build --no-bundle 2>&1 | head -5`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add client/src/ui/header.ts
git commit -m "feat(client): add header component with world time display"
```

---

## Task 4: NPC Dialog Component

**Files:**
- Create: `client/src/ui/dialog.ts`

- [ ] **Step 1: Create the dialog component with typewriter integration**

```ts
// client/src/ui/dialog.ts
import { createTypewriter, type TypewriterController } from './typewriter';

export interface Dialog {
  el: HTMLElement;
  show(npcName: string, npcRole: string, text: string): void;
  dismiss(): void;
  readonly active: boolean;
}

const DIALOG_FONT = '15px Georgia, "Times New Roman", serif';
const DIALOG_MAX_WIDTH = 440; // px, inner content width

export function createDialog(): Dialog {
  const backdrop = document.createElement('div');
  backdrop.className = 'dialog-backdrop';
  backdrop.style.display = 'none';

  const win = document.createElement('div');
  win.className = 'dialog-win';

  const titleBar = document.createElement('div');
  titleBar.className = 'win-title dialog-title';

  const body = document.createElement('div');
  body.className = 'win-body dialog-body';

  win.appendChild(titleBar);
  win.appendChild(body);
  backdrop.appendChild(win);

  let currentTw: TypewriterController | null = null;

  function dismiss() {
    if (currentTw) {
      currentTw.cancel();
      currentTw = null;
    }
    backdrop.style.display = 'none';
    body.innerHTML = '';
  }

  // Escape to skip animation or dismiss
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || backdrop.style.display === 'none') return;
    if (currentTw) {
      currentTw.skip();
      currentTw = null;
    } else {
      dismiss();
    }
  });

  // Click backdrop to dismiss
  backdrop.addEventListener('click', (e) => {
    if (e.target === backdrop) dismiss();
  });

  // Click dialog body to skip typewriter
  body.addEventListener('click', () => {
    if (currentTw) {
      currentTw.skip();
      currentTw = null;
    }
  });

  return {
    el: backdrop,
    show(npcName: string, npcRole: string, text: string) {
      if (currentTw) currentTw.cancel();

      titleBar.textContent = `\u2500 ${npcName}${npcRole ? ` \u2014 ${npcRole}` : ''} \u2500`;
      body.innerHTML = '';
      backdrop.style.display = '';

      currentTw = createTypewriter({
        text,
        font: DIALOG_FONT,
        maxWidth: DIALOG_MAX_WIDTH,
        container: body,
        charDelay: 25,
        lineClass: 'tw-line',
        cursorClass: 'tw-cursor',
      });
      currentTw.onComplete(() => { currentTw = null; });
      currentTw.start();
    },
    dismiss,
    get active() {
      return backdrop.style.display !== 'none';
    },
  };
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && bun build src/ui/dialog.ts --outdir /tmp/test-build --no-bundle 2>&1 | head -5`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add client/src/ui/dialog.ts
git commit -m "feat(client): add NPC dialog with Pretext typewriter animation"
```

---

## Task 5: Overhaul index.html Layout and CSS

**Files:**
- Modify: `client/index.html`

Replace the entire `<style>` block and `<body>` content. The HTML body becomes minimal mount points — all content is created by JS. CSS adds window styling, header, dialog overlay, and typewriter cursor animation.

- [ ] **Step 1: Replace the style block and body**

Keep the existing `<head>` (meta tags, title, script tag). Replace everything inside `<style>...</style>` with the new CSS, and replace `<body>...</body>` with the new markup.

**New CSS** (full replacement of the style block):

```css
:root {
  --bg-primary: #0a0a0f;
  --bg-secondary: #12121a;
  --bg-panel: #16161f;
  --text-primary: #c8c8d0;
  --text-dim: #6a6a78;
  --text-npc: #d4a574;
  --text-damage: #e05050;
  --text-heal: #50c878;
  --text-system: #5a5a70;
  --text-location: #7aa2d4;
  --border: #2a2a38;
  --accent: #8b5cf6;
  --input-bg: #1a1a25;
  --win-title-bg: #16161f;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body {
  height: 100%; overflow: hidden;
  background: var(--bg-primary); color: var(--text-primary);
  font-family: 'Courier New', Consolas, monospace; font-size: 13px;
}

/* ── TUI Shell ── */
#app {
  display: grid; grid-template-rows: auto 1fr auto;
  height: 100vh; gap: 4px; padding: 4px;
}

/* ── Header ── */
.tui-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 4px 12px; color: var(--text-dim); font-size: 12px;
  border: 1px solid var(--border); border-radius: 2px; background: var(--bg-primary);
}
.tui-header .header-title { color: var(--accent); letter-spacing: 2px; font-weight: bold; }
.tui-header .header-moon { margin-right: 6px; }

/* ── Main grid ── */
#tui-main {
  display: grid; grid-template-columns: 1fr 260px; gap: 4px;
  overflow: hidden; min-height: 0;
}
#left-col { display: flex; flex-direction: column; gap: 4px; min-height: 0; }
#right-col { display: flex; flex-direction: column; gap: 4px; overflow-y: auto; min-height: 0; }

/* ── Window ── */
.win {
  border: 1px solid var(--border); border-radius: 2px;
  display: flex; flex-direction: column; background: var(--bg-primary); min-height: 0;
}
.win-title {
  background: var(--win-title-bg); padding: 2px 8px; font-size: 11px;
  color: var(--text-dim); border-bottom: 1px solid var(--border);
  text-transform: uppercase; letter-spacing: 1px; flex-shrink: 0;
}
.win-body { padding: 8px 10px; flex: 1; min-height: 0; }

/* ── Narrative ── */
#narrative-win { flex: 1; min-height: 0; }
#narrative-win .win-body {
  overflow-y: auto; position: relative;
  font-family: Georgia, 'Times New Roman', serif; font-size: 16px; line-height: 1.7;
}

/* ── Map ── */
#map-win .win-body { padding: 0; }
#map-win canvas { display: block; width: 100%; }

/* ── Sidebar ── */
.sidebar-win .win-body { font-size: 13px; }

/* ── Command ── */
#command-win .win-body {
  display: flex; align-items: center; gap: 8px; padding: 4px 10px;
}
#command-win .prompt-char { color: var(--text-dim); flex-shrink: 0; }
#command-win input {
  flex: 1; background: none; border: none; color: var(--text-primary);
  font-family: inherit; font-size: 14px; outline: none;
}
#command-win input::placeholder { color: var(--text-dim); opacity: 0.5; }

/* ── Dialog overlay ── */
.dialog-backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}
.dialog-win {
  border: 1px solid var(--border); border-radius: 2px; background: var(--bg-primary);
  max-width: 500px; width: 90%; max-height: 60vh; display: flex; flex-direction: column;
}
.dialog-title {
  background: var(--win-title-bg); padding: 4px 10px; font-size: 12px;
  color: var(--text-npc); border-bottom: 1px solid var(--border); letter-spacing: 1px;
}
.dialog-body {
  padding: 12px 16px; overflow-y: auto;
  font-family: Georgia, 'Times New Roman', serif; font-size: 15px;
  line-height: 1.6; color: var(--text-primary);
}

/* ── Typewriter ── */
.tw-line { min-height: 1.6em; }
.tw-cursor {
  color: var(--text-npc); animation: blink-cursor 0.8s step-end infinite;
}
@keyframes blink-cursor { 50% { opacity: 0; } }

/* ── Narrative blocks ── */
.narrative-block { margin-bottom: 16px; animation: fadeIn 0.3s ease; }
.narrative-block.player-action {
  font-style: italic; border-left: 2px solid var(--border);
  padding-left: 10px; color: var(--text-dim);
}
.narrative-block.system {
  color: var(--text-system); font-family: 'Courier New', monospace; font-size: 13px;
}

/* ── Entity links ── */
.entity-link { text-decoration: underline dotted; cursor: pointer; transition: opacity 0.15s; }
.entity-link:hover { opacity: 0.8; }
.entity-npc { color: var(--text-npc); }
.entity-item { color: #a335ee; }
.entity-exit { color: #50c8c8; }
.entity-location { color: var(--text-location); }

/* ── Inline text styles ── */
.npc-name, .npc { color: var(--text-npc); }
.damage { color: var(--text-damage); font-weight: bold; }
.heal { color: var(--text-heal); }
.italic { font-style: italic; }
.bold { font-weight: bold; }
.location { color: var(--text-location); }

/* ── Sidebar elements ── */
.bar-fill-hp { color: var(--text-damage); }
.bar-fill-xp { color: var(--accent); }
.bar-empty { color: var(--border); }
.stat-label { color: var(--text-dim); display: inline-block; width: 24px; }
.exit-row { cursor: pointer; padding: 1px 0; }
.exit-row:hover { color: #fff; }
.exit-dir { color: #50c8c8; }
.exit-dest { color: var(--text-dim); margin-left: 4px; }
.npc-row { padding: 1px 0; cursor: pointer; }
.npc-row:hover .npc { color: #fff; }
.npc-diamond { color: var(--text-npc); margin-right: 4px; }
.npc-role { color: var(--text-dim); margin-left: 4px; }
.item-row { padding: 1px 0; }
.item-bullet { color: var(--text-dim); margin-right: 4px; }
.item-equip { color: var(--text-dim); margin-left: 4px; font-size: 11px; }
.empty-msg { color: var(--text-dim); font-style: italic; }

/* ── Thinking ── */
.thinking { color: var(--text-system); font-style: italic; font-family: 'Courier New', monospace; font-size: 13px; }
.thinking::after { content: ''; animation: dots 1.5s steps(4,end) infinite; }
@keyframes dots { 0%{content:''} 25%{content:'.'} 50%{content:'..'} 75%{content:'...'} }
@keyframes fadeIn { from{opacity:0;transform:translateY(4px)} to{opacity:1;transform:translateY(0)} }

/* ── Health bar ── */
.health-bar { height: 6px; background: var(--border); border-radius: 2px; overflow: hidden; margin-top: 2px; }
.health-bar-fill { height: 100%; background: var(--text-damage); transition: width 0.3s; }

/* ── Overlays ── */
#char-create-overlay {
  position: fixed; inset: 0; background: var(--bg-primary);
  display: flex; align-items: center; justify-content: center; z-index: 200;
  flex-direction: column; gap: 16px;
}
#char-create-overlay h1 { color: var(--accent); font-size: 24px; letter-spacing: 4px; }
#char-create-overlay p { color: var(--text-dim); }
#char-create-overlay input {
  background: var(--input-bg); border: 1px solid var(--border); color: var(--text-primary);
  font-family: inherit; font-size: 16px; padding: 8px 16px; text-align: center;
  outline: none; width: 240px;
}
#char-create-overlay input:focus { border-color: var(--accent); }
#char-create-overlay button {
  background: var(--accent); color: #fff; border: none; padding: 8px 24px;
  font-family: inherit; cursor: pointer;
}
#death-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.9);
  display: none; align-items: center; justify-content: center; z-index: 200;
  flex-direction: column; gap: 16px; color: var(--text-damage);
}
#death-overlay h1 { font-size: 28px; letter-spacing: 6px; }
#death-overlay .death-cause { color: var(--text-dim); font-size: 14px; }
#death-overlay button {
  background: none; border: 1px solid var(--border); color: var(--text-primary);
  padding: 8px 24px; font-family: inherit; cursor: pointer; margin-top: 16px;
}
```

**New body** (full replacement):

```html
<body>
  <div id="app">
    <div id="tui-header"></div>
    <div id="tui-main">
      <div id="left-col">
        <div id="narrative-mount"></div>
        <div id="map-mount"></div>
      </div>
      <div id="right-col">
        <div id="character-mount"></div>
        <div id="inventory-mount"></div>
        <div id="exits-mount"></div>
        <div id="present-mount"></div>
      </div>
    </div>
    <div id="command-mount"></div>
    <div id="dialog-mount"></div>
  </div>
  <div id="char-create-overlay">
    <h1>MEMENTO MORI</h1>
    <p>What is your name, wanderer?</p>
    <input type="text" id="char-name-input" placeholder="Enter name" autofocus />
    <button id="char-create-btn">Enter the World</button>
  </div>
  <div id="death-overlay">
    <h1>YOU HAVE DIED</h1>
    <p class="death-cause" id="death-cause"></p>
    <p id="death-stats"></p>
    <button id="death-restart-btn">Begin Again</button>
  </div>
  <script type="module" src="app.js"></script>
</body>
```

- [ ] **Step 2: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add client/index.html
git commit -m "feat(client): overhaul layout to window-based TUI with typewriter CSS"
```

---

## Task 6: Refactor Sidebar Panels

**Files:**
- Modify: `client/src/panels/character.ts`
- Modify: `client/src/panels/inventory.ts`
- Create: `client/src/panels/exits.ts`
- Create: `client/src/panels/present.ts`
- Delete: `client/src/panels/actions.ts`

- [ ] **Step 1: Rewrite character.ts**

The function takes a Window `.body` element and renders bar-chart stats using monospace block characters.

```ts
// client/src/panels/character.ts
import type { GameState } from '../state/game-state';

export function renderCharacterPanel(body: HTMLElement, state: GameState): void {
  const p = state.player;
  const hpPct = p.maxHealth > 0 ? Math.round((p.health / p.maxHealth) * 100) : 0;
  const xpPct = p.xpThreshold > 0 ? Math.round((p.xp / p.xpThreshold) * 100) : 0;
  const hpFill = Math.round(hpPct / 10);
  const xpFill = Math.round(xpPct / 10);

  body.innerHTML = `
    <div><span class="stat-label">HP</span> <span class="bar-fill-hp">${'\u2588'.repeat(hpFill)}</span><span class="bar-empty">${'\u2591'.repeat(10 - hpFill)}</span> <span style="color:var(--text-dim)">${p.health}/${p.maxHealth}</span></div>
    <div><span class="stat-label">XP</span> <span class="bar-fill-xp">${'\u2588'.repeat(xpFill)}</span><span class="bar-empty">${'\u2591'.repeat(10 - xpFill)}</span> <span style="color:var(--text-dim)">${p.xp}/${p.xpThreshold}</span></div>
    <div><span class="stat-label">Lv</span> ${p.level}</div>
  `;
}
```

- [ ] **Step 2: Rewrite inventory.ts**

```ts
// client/src/panels/inventory.ts
import type { GameState } from '../state/game-state';

const RARITY_COLORS: Record<string, string> = {
  common: '#808080', uncommon: '#1eff00', rare: '#0070dd', epic: '#a335ee', legendary: '#ff8000',
};

export function renderInventoryPanel(body: HTMLElement, state: GameState): void {
  if (state.inventory.length === 0) {
    body.innerHTML = '<div class="empty-msg">Empty</div>';
    return;
  }
  body.innerHTML = state.inventory
    .map((item) => {
      const color = RARITY_COLORS[item.rarity] || RARITY_COLORS.common;
      const equip = item.equipped ? '<span class="item-equip">E</span>' : '';
      return `<div class="item-row"><span class="item-bullet">\u00B7</span> <span style="color:${color}">${item.name}</span>${equip}</div>`;
    })
    .join('');
}
```

- [ ] **Step 3: Create exits.ts**

```ts
// client/src/panels/exits.ts
import type { GameState } from '../state/game-state';

export function renderExitsPanel(
  body: HTMLElement, state: GameState, onAction: (action: string) => void,
): void {
  if (state.location.exits.length === 0) {
    body.innerHTML = '<div class="empty-msg">None</div>';
    return;
  }
  body.innerHTML = state.location.exits
    .map((e) =>
      `<div class="exit-row" data-dir="${e.direction}"><span class="exit-dir">\u2192 ${e.direction.charAt(0).toUpperCase() + e.direction.slice(1)}</span><span class="exit-dest">${e.name}</span></div>`,
    )
    .join('');
  body.querySelectorAll('.exit-row').forEach((row) => {
    row.addEventListener('click', () => onAction(`go ${(row as HTMLElement).dataset.dir}`));
  });
}
```

- [ ] **Step 4: Create present.ts**

```ts
// client/src/panels/present.ts
import type { GameState } from '../state/game-state';

export function renderPresentPanel(
  body: HTMLElement, state: GameState, onAction: (action: string) => void,
): void {
  const npcs = state.location.npcs || [];
  const items = state.location.items || [];
  if (npcs.length === 0 && items.length === 0) {
    body.innerHTML = '<div class="empty-msg">Nothing here</div>';
    return;
  }
  let html = '';
  for (const npc of npcs) {
    const name = typeof npc === 'string' ? npc : npc.name;
    const role = typeof npc === 'string' ? '' : (npc.role || '');
    html += `<div class="npc-row" data-action="talk to ${name}"><span class="npc-diamond">\u25C6</span><span class="npc">${name}</span>${role ? `<span class="npc-role">\u2014 ${role}</span>` : ''}</div>`;
  }
  for (const item of items) {
    const name = typeof item === 'string' ? item : item.name;
    html += `<div class="item-row" data-action="examine ${name}" style="cursor:pointer"><span class="item-bullet">\u00B7</span> ${name}</div>`;
  }
  body.innerHTML = html;
  body.querySelectorAll('[data-action]').forEach((el) => {
    el.addEventListener('click', () => onAction((el as HTMLElement).dataset.action!));
  });
}
```

- [ ] **Step 5: Delete actions.ts**

```bash
rm client/src/panels/actions.ts
```

- [ ] **Step 6: Verify all panels compile**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && bun build src/panels/character.ts src/panels/inventory.ts src/panels/exits.ts src/panels/present.ts --outdir /tmp/test-build --no-bundle 2>&1 | head -10`
Expected: No errors

- [ ] **Step 7: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add client/src/panels/character.ts client/src/panels/inventory.ts client/src/panels/exits.ts client/src/panels/present.ts
git rm client/src/panels/actions.ts
git commit -m "feat(client): refactor sidebar panels for window-based rendering"
```

---

## Task 7: Refactor Narrative Panel

**Files:**
- Modify: `client/src/panels/narrative.ts`

- [ ] **Step 1: Verify narrative.ts is container-agnostic**

Read `client/src/panels/narrative.ts`. The `initNarrative(container)` function takes a generic `HTMLElement`. Confirm it does not reference `#narrative-pane` or any specific DOM ID. If it does, update those references to use the passed `container` parameter.

The narrative panel should work unchanged when passed `narrativeWin.body` instead of the old `#narrative-pane` div.

- [ ] **Step 2: Commit if changes needed**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add client/src/panels/narrative.ts
git commit -m "refactor(client): ensure narrative panel is container-agnostic"
```

---

## Task 8: Refactor Map Panel

**Files:**
- Modify: `client/src/panels/map.ts`

- [ ] **Step 1: Remove renderLocationPanel from map.ts**

Read `client/src/panels/map.ts`. Remove the `renderLocationPanel` export and its implementation — that functionality is now in `exits.ts` and `present.ts`.

Keep `initMapPanel(container, onAction)` and `updateMap(state, onAction)` unchanged — they operate on whatever container element they receive.

- [ ] **Step 2: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add client/src/panels/map.ts
git commit -m "refactor(client): remove renderLocationPanel from map panel"
```

---

## Task 9: Wire Everything in app.ts

**Files:**
- Modify: `client/src/app.ts`

This is the main integration. Create all Windows, mount them into the DOM, and rewire the existing game logic.

- [ ] **Step 1: Rewrite app.ts**

The structure stays the same (handleMessage, handleAction, enterWorld, getThresholdMap) but the bootstrap creates Window components and mounts them.

Key changes from the current `app.ts`:
- Import `createWindow`, `createHeader`, `createDialog`
- Import new panel functions (`renderExitsPanel`, `renderPresentPanel`)
- Remove import of `renderActionsPanel` and `renderLocationPanel`
- In `DOMContentLoaded`: create windows, replace mount divs, init narrative with window body
- In `renderAllPanels()`: call panels with `win.body` instead of `document.getElementById`
- In `handleMessage()`: update header when `world_time` arrives in state_update

**Full replacement** — copy the existing `app.ts`, then apply these modifications:

1. Replace imports:
```ts
// REMOVE:
import { renderActionsPanel } from './panels/actions';
// ADD:
import { renderExitsPanel } from './panels/exits';
import { renderPresentPanel } from './panels/present';
import { createWindow, type Window } from './ui/window';
import { createHeader, type WorldTime } from './ui/header';
import { createDialog } from './ui/dialog';
```

2. Remove the `renderLocationPanel` import from `./panels/map` — keep only `initMapPanel` and `updateMap`.

3. Add module-level variables for the windows:
```ts
let header: ReturnType<typeof createHeader>;
let npcDialog: ReturnType<typeof createDialog>;
let narrativeWin: Window;
let mapWin: Window;
let characterWin: Window;
let inventoryWin: Window;
let exitsWin: Window;
let presentWin: Window;
let commandWin: Window;
```

4. Replace `renderAllPanels()`:
```ts
function renderAllPanels() {
  characterWin.setTitle(gameState.player.name || 'Character');
  renderCharacterPanel(characterWin.body, gameState);
  renderInventoryPanel(inventoryWin.body, gameState);
  renderExitsPanel(exitsWin.body, gameState, handleAction);
  renderPresentPanel(presentWin.body, gameState, handleAction);
  updateMap(gameState, handleAction);
}
```

5. In `handleMessage()`, after `applyStateUpdate`, add:
```ts
if (msg.state_update.world_time) {
  header.updateTime(msg.state_update.world_time as WorldTime);
}
```

6. Replace the `DOMContentLoaded` handler bootstrap with window creation and mounting:
```ts
document.addEventListener('DOMContentLoaded', () => {
  // Header
  header = createHeader();
  document.getElementById('tui-header')!.replaceWith(header.el);
  header.el.id = 'tui-header';

  // Windows
  narrativeWin = createWindow({ title: 'Narrative', id: 'narrative-win', scrollable: true });
  mapWin = createWindow({ title: 'Map', id: 'map-win' });
  characterWin = createWindow({ title: 'Character', id: 'character-win', className: 'sidebar-win' });
  inventoryWin = createWindow({ title: 'Inventory', id: 'inventory-win', className: 'sidebar-win' });
  exitsWin = createWindow({ title: 'Exits', id: 'exits-win', className: 'sidebar-win' });
  presentWin = createWindow({ title: 'Present', id: 'present-win', className: 'sidebar-win' });
  commandWin = createWindow({ title: 'Command', id: 'command-win' });

  // Mount
  document.getElementById('narrative-mount')!.replaceWith(narrativeWin.el);
  document.getElementById('map-mount')!.replaceWith(mapWin.el);
  document.getElementById('character-mount')!.replaceWith(characterWin.el);
  document.getElementById('inventory-mount')!.replaceWith(inventoryWin.el);
  document.getElementById('exits-mount')!.replaceWith(exitsWin.el);
  document.getElementById('present-mount')!.replaceWith(presentWin.el);
  document.getElementById('command-mount')!.replaceWith(commandWin.el);

  // Map starts hidden, toggle with 'm'
  mapWin.hide();
  document.addEventListener('keydown', (e) => {
    if (e.key === 'm' && document.activeElement?.tagName !== 'INPUT') mapWin.toggle();
  });

  // Dialog
  npcDialog = createDialog();
  document.getElementById('dialog-mount')!.replaceWith(npcDialog.el);

  // Narrative
  narrative = initNarrative(narrativeWin.body);

  // Command input
  commandWin.body.innerHTML = '<span class="prompt-char">&gt;</span><input type="text" placeholder="What do you do?" />';
  const inputEl = commandWin.body.querySelector('input') as HTMLInputElement;
  initInput(inputEl, handleAction);

  // Map
  initMapPanel(mapWin.body, handleAction);

  // Connection handler
  setConnectionHandler((connected) => {
    narrative.addBlock(connected ? 'Reconnected.' : 'Connection lost. Reconnecting...', 'system');
  });

  // Message handler
  setMessageHandler(handleMessage);

  // Character creation
  const nameInput = document.getElementById('char-name-input') as HTMLInputElement;
  const createBtn = document.getElementById('char-create-btn')!;
  const startGame = () => { const n = nameInput.value.trim(); if (n) enterWorld(n); };
  createBtn.addEventListener('click', startGame);
  nameInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') startGame(); });

  // Death restart
  document.getElementById('death-restart-btn')!.addEventListener('click', () => window.location.reload());
});
```

7. Keep `getThresholdMap()`, `registerMapEntities()`, `handleAction()`, `showDeathScreen()`, `enterWorld()`, and `handleMessage()` largely the same — just update the panel calls as shown above.

- [ ] **Step 2: Build the client**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && bun build src/app.ts --outfile app.js 2>&1`
Expected: Clean build

- [ ] **Step 3: Fix any build errors**

Common issues:
- Missing exports from `map.ts` (if `renderLocationPanel` was still imported)
- Type mismatch on `Window` name collision with global `Window` — rename to `TuiWindow` if needed
- `actions.ts` import still present somewhere

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add client/src/app.ts
git commit -m "feat(client): integrate window layout, header, and dialog in app orchestrator"
```

---

## Task 10: Engine Time System — Model + Tool

**Files:**
- Create: `engine/src/memento/models/time.py`
- Modify: `engine/src/memento/models/__init__.py`
- Create: `engine/src/memento/tools/time.py`

- [ ] **Step 1: Create WorldTime model**

```python
# engine/src/memento/models/time.py
from pydantic import BaseModel

MOON_PHASES = [
    ("New Moon", "\U0001f311"),
    ("Waxing Crescent", "\U0001f312"),
    ("First Quarter", "\U0001f313"),
    ("Waxing Gibbous", "\U0001f314"),
    ("Full Moon", "\U0001f315"),
    ("Waning Gibbous", "\U0001f316"),
    ("Last Quarter", "\U0001f317"),
    ("Waning Crescent", "\U0001f318"),
]

MONTHS = [
    "Ashfall", "Bleakwind", "Cinderwatch", "Duskhollow",
    "Embertide", "Frostmere", "Grimshade", "Hollowmoon",
    "Ironveil", "Jadewane", "Knellrise", "Lostember",
]

TIMES_OF_DAY = ["Dawn", "Morning", "Midday", "Afternoon", "Dusk", "Evening", "Night", "Midnight"]


class WorldTime(BaseModel):
    tick: int = 0

    @property
    def time_of_day(self) -> str:
        return TIMES_OF_DAY[self.tick % len(TIMES_OF_DAY)]

    @property
    def day_number(self) -> int:
        return (self.tick // len(TIMES_OF_DAY)) % 30 + 1

    @property
    def month(self) -> str:
        return MONTHS[(self.tick // (len(TIMES_OF_DAY) * 30)) % len(MONTHS)]

    @property
    def season(self) -> str:
        month_idx = (self.tick // (len(TIMES_OF_DAY) * 30)) % len(MONTHS)
        return ["Winter", "Spring", "Summer", "Autumn"][month_idx // 3]

    @property
    def moon_phase(self) -> str:
        return MOON_PHASES[(self.tick // len(TIMES_OF_DAY)) % len(MOON_PHASES)][0]

    @property
    def moon_icon(self) -> str:
        return MOON_PHASES[(self.tick // len(TIMES_OF_DAY)) % len(MOON_PHASES)][1]

    def advance(self, ticks: int = 1) -> "WorldTime":
        return WorldTime(tick=self.tick + ticks)

    def to_display(self) -> dict:
        return {
            "moon_phase": self.moon_phase,
            "moon_icon": self.moon_icon,
            "day_name": "",
            "day_number": self.day_number,
            "month": self.month,
            "season": self.season,
            "time_of_day": self.time_of_day,
        }
```

- [ ] **Step 2: Export from models/__init__.py**

Add `from .time import WorldTime` to the imports in `engine/src/memento/models/__init__.py`.

- [ ] **Step 3: Create time tool**

```python
# engine/src/memento/tools/time.py
from crewai.tools import tool
from memento.models.time import WorldTime

_world_time = WorldTime(tick=0)


def get_current_time() -> WorldTime:
    """Get current world time (helper for flows, not a CrewAI tool)."""
    return _world_time


def advance_time(ticks: int = 1) -> WorldTime:
    """Advance world time (helper for flows, not a CrewAI tool)."""
    global _world_time
    _world_time = _world_time.advance(ticks)
    return _world_time


@tool("get_world_time")
def get_world_time() -> str:
    """Get the current in-game world time including moon phase, date, and time of day."""
    t = _world_time
    return f"{t.moon_icon} {t.moon_phase} | {t.day_number} of {t.month} | {t.time_of_day} | {t.season}"
```

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/models/time.py engine/src/memento/models/__init__.py engine/src/memento/tools/time.py
git commit -m "feat(engine): add WorldTime model and time tool"
```

---

## Task 11: Wire Time Into Game Turn

**Files:**
- Modify: `engine/src/memento/flows/game_turn.py`

- [ ] **Step 1: Add world_time to TurnState and post_turn**

Read `engine/src/memento/flows/game_turn.py`.

1. Add import at top:
```python
from memento.tools.time import advance_time, get_current_time
```

2. Add field to `TurnState`:
```python
world_time: dict = {}
```

3. In the `post_turn` method, before the final return, advance time and store it:
```python
world_time = advance_time(1)
self.state.world_time = world_time.to_display()
```

The gateway/Matrix bridge should already pass through all fields from `state` — verify in Task 12.

- [ ] **Step 2: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add engine/src/memento/flows/game_turn.py
git commit -m "feat(engine): advance world time each game turn"
```

---

## Task 12: Gateway Time Passthrough

**Files:**
- Potentially modify: gateway files

- [ ] **Step 1: Verify state_update passthrough**

Read how narrative responses flow from engine → Matrix → gateway → WebSocket → client. Check if the gateway passes through arbitrary keys in the state_update, or filters to a specific set.

Look at:
- `gateway/src/gateway/matrix_bridge.py` — how it reads engine output from Matrix
- `gateway/src/gateway/ws.py` — how it sends to WebSocket clients

If state_update is passed through as-is (likely), no changes needed — `world_time` will flow through automatically.

- [ ] **Step 2: Commit if changes needed**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add gateway/
git commit -m "feat(gateway): pass world_time through state_update"
```

---

## Task 13: Build, Test, Polish

**Files:**
- Any files needing fixes

- [ ] **Step 1: Full client build**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && bun build src/app.ts --outfile app.js 2>&1`
Expected: Clean build

- [ ] **Step 2: Visual check in browser**

Open the client and verify:
- Header bar renders with default time placeholder
- All windows have title bars with `─ Title ─` format
- Narrative window scrolls, entity links work
- Sidebar windows stack: Character (with bars), Inventory, Exits (clickable), Present (clickable)
- Command bar at bottom with prompt and input
- Map toggles with 'm' key
- Character creation overlay works
- Death overlay works

- [ ] **Step 3: Test NPC dialog typewriter**

If the engine is running, talk to an NPC and verify:
- Dialog window appears centered with backdrop
- Text types out character by character
- Click body or press Escape to skip/dismiss
- Conversation also appears in narrative scroll

If engine is not running, test the dialog manually by adding a temporary button or console call.

- [ ] **Step 4: Fix visual issues**

Common fixes:
- Narrative window not taking full height → check `flex: 1` on `#narrative-win`
- Sidebar overflowing → check `overflow-y: auto` on `#right-col`
- Map canvas not sizing → check the container passed to `initMapPanel`
- Input not focusing → ensure `commandWin.body.querySelector('input')` finds the element
- `Window` type name collision with global `Window` → rename export to `TuiWindow` if needed

- [ ] **Step 5: Final commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add -A
git commit -m "polish: unified text UI integration fixes"
```
