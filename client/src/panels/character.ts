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
