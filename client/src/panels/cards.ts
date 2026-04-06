// src/panels/cards.ts
/**
 * Cards panel — renders stacked NPC + player cards onto an offscreen canvas
 * for compositing into the unified canvas 'cards' region.
 */

import { drawCard, CARD_W, type CardContent } from '../map/card-renderer';
import type { GameState } from '../state/game-state';
import { theme } from '../renderer/theme';

let offscreen: HTMLCanvasElement | null = null;
let offscreenCtx: CanvasRenderingContext2D | null = null;

/** Render all room NPC cards + player card onto an offscreen canvas. Returns the canvas. */
export function renderCards(state: GameState): HTMLCanvasElement {
  if (!offscreen) {
    offscreen = document.createElement('canvas');
    offscreenCtx = offscreen.getContext('2d')!;
  }

  // Build card list: player first, then all NPCs
  const cards: CardContent[] = [];

  // Player card
  cards.push({
    type: 'player',
    name: state.player.name,
    labels: [`Lv ${state.player.level}`, state.player.archetype || 'Wanderer'],
    summary: state.location.name,
    health: state.player.health,
    maxHealth: state.player.maxHealth,
    xp: state.player.xp,
    xpThreshold: state.player.xpThreshold,
  });

  // NPC cards
  for (const npc of state.location.npcs) {
    cards.push({
      type: 'entity',
      name: npc.name,
      labels: npc.role ? [npc.role] : ['NPC'],
      summary: '',
    });
  }

  // Allocate generous height for first pass measurement
  const estimatedHeight = cards.length * 200;
  offscreen.width = Math.ceil(CARD_W);
  offscreen.height = Math.max(estimatedHeight, 100);

  // First pass — measure actual height
  offscreenCtx!.fillStyle = theme.colors.bg;
  offscreenCtx!.fillRect(0, 0, offscreen.width, offscreen.height);

  let y = 4;
  for (const card of cards) {
    const h = drawCard(offscreenCtx!, 0, y, card);
    y += h + 8;
  }

  // Trim to actual content height and re-draw (canvas clears on resize)
  offscreen.height = Math.max(y, 10);
  offscreenCtx!.fillStyle = theme.colors.bg;
  offscreenCtx!.fillRect(0, 0, offscreen.width, offscreen.height);

  y = 4;
  for (const card of cards) {
    const h = drawCard(offscreenCtx!, 0, y, card);
    y += h + 8;
  }

  return offscreen;
}
