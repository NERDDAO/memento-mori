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

  // 4. Wait for WebSocket connection (with 15s timeout — WS auto-reconnects)
  await Promise.race([
    new Promise<void>((resolve) => {
      const session = getSession();
      if (session.connected) { resolve(); return; }
      setConnectionHandler((connected) => { if (connected) resolve(); });
    }),
    new Promise<void>((resolve) => setTimeout(resolve, 15000)),
  ]);

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
