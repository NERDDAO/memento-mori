// client/src/panels/character.ts
import type { GameState } from '../state/game-state';

const SKILL_CATEGORIES: Record<string, string[]> = {
  combat: ['swordsmanship', 'archery', 'unarmed', 'blocking'],
  stealth: ['lockpicking', 'pickpocket', 'sneaking', 'disguise'],
  social: ['persuasion', 'intimidation', 'deception', 'insight'],
  survival: ['tracking', 'foraging', 'medicine', 'navigation'],
  arcane: ['spellcraft', 'alchemy', 'enchanting', 'lore'],
};

function renderSkills(skills: Record<string, number>): string {
  const entries = Object.entries(skills).filter(([, v]) => v > 0);
  if (entries.length === 0) return '';

  const lines = entries.map(([name, level]) => {
    const dots = '\u25CF'.repeat(level) + '\u25CB'.repeat(Math.max(0, 5 - level));
    return `<div class="skill-row"><span class="skill-name">${name}</span> <span class="skill-dots">${dots}</span></div>`;
  });
  return `<div class="skills-section">${lines.join('')}</div>`;
}

export function renderCharacterPanel(body: HTMLElement, state: GameState): void {
  const p = state.player;
  const hpPct = p.maxHealth > 0 ? Math.round((p.health / p.maxHealth) * 100) : 0;
  const xpPct = p.xpThreshold > 0 ? Math.round((p.xp / p.xpThreshold) * 100) : 0;
  const hpFill = Math.round(hpPct / 10);
  const xpFill = Math.round(xpPct / 10);

  const archLabel = p.archetype ? `<div class="archetype-label">${p.archetype}</div>` : '';
  const skillsHtml = renderSkills(p.skills);

  body.innerHTML = `
    ${archLabel}
    <div><span class="stat-label">HP</span> <span class="bar-fill-hp">${'\u2588'.repeat(hpFill)}</span><span class="bar-empty">${'\u2591'.repeat(10 - hpFill)}</span> <span style="color:var(--text-dim)">${p.health}/${p.maxHealth}</span></div>
    <div><span class="stat-label">XP</span> <span class="bar-fill-xp">${'\u2588'.repeat(xpFill)}</span><span class="bar-empty">${'\u2591'.repeat(10 - xpFill)}</span> <span style="color:var(--text-dim)">${p.xp}/${p.xpThreshold}</span></div>
    <div><span class="stat-label">Lv</span> ${p.level}</div>
    ${skillsHtml}
  `;
}
