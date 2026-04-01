// src/ui/status.ts
/**
 * Status footer — shows chain sync pipeline status, connection state, game tick.
 */

export interface StatusBar {
  el: HTMLElement;
  setPhase(phase: string): void;
  setChain(connected: boolean): void;
  setTick(tick: number): void;
  clear(): void;
}

const CLEAR_DELAY = 4000; // ms before auto-clearing to idle

export function createStatusBar(): StatusBar {
  const el = document.createElement('div');
  el.className = 'status-bar';
  el.innerHTML = `
    <span class="status-phase">\u2713 Ready</span>
    <span class="status-chain">\u25C7 Redstone: offline</span>
    <span class="status-tick">\u263D Tick 0</span>
  `;

  const phaseEl = el.querySelector('.status-phase') as HTMLElement;
  const chainEl = el.querySelector('.status-chain') as HTMLElement;
  const tickEl = el.querySelector('.status-tick') as HTMLElement;

  let clearTimer: ReturnType<typeof setTimeout> | null = null;

  function scheduleClear() {
    if (clearTimer) clearTimeout(clearTimer);
    clearTimer = setTimeout(() => {
      phaseEl.textContent = '\u2713 Synced';
      phaseEl.className = 'status-phase synced';
    }, CLEAR_DELAY);
  }

  return {
    el,
    setPhase(phase: string) {
      const icons: Record<string, string> = {
        'processing': '\u27F3 Processing turn...',
        'extracting': '\u27F3 Extracting episode...',
        'fetching': '\u27F3 Fetching episode...',
        'pushing': '\u27F3 Pushing onchain...',
        'synced': '\u2713 Synced',
        'thinking': '\u27F3 The world responds...',
        'error': '\u2717 Sync error',
      };
      phaseEl.textContent = icons[phase] || phase;
      phaseEl.className = `status-phase ${phase}`;
      if (phase === 'synced') {
        // already at rest
      } else {
        scheduleClear();
      }
    },
    setChain(connected: boolean) {
      chainEl.textContent = connected
        ? '\u25C6 Redstone: synced'
        : '\u25C7 Redstone: offline';
      chainEl.className = `status-chain ${connected ? 'connected' : ''}`;
    },
    setTick(tick: number) {
      tickEl.textContent = `\u263D Tick ${tick}`;
    },
    clear() {
      phaseEl.textContent = '\u2713 Ready';
      phaseEl.className = 'status-phase';
      chainEl.textContent = '\u25C7 Redstone: offline';
      chainEl.className = 'status-chain';
      tickEl.textContent = '\u263D Tick 0';
    },
  };
}
