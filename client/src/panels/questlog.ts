// client/src/panels/questlog.ts
import type { GameState } from '../state/game-state';

export interface QuestEntry {
  name: string;
  description: string;
  currentStage: number;
  totalStages: number;
  giver: string;
  completed: boolean;
}

export function renderQuestLogPanel(body: HTMLElement, quests: QuestEntry[]): void {
  if (!quests || quests.length === 0) {
    body.innerHTML = '<div class="empty-msg">No active quests</div>';
    return;
  }

  const html = quests.map(q => {
    const progress = q.totalStages > 0
      ? Math.round((q.currentStage / q.totalStages) * 10)
      : 0;
    const progressBar = '\u2588'.repeat(progress) + '\u2591'.repeat(10 - progress);
    const statusLabel = q.completed ? '<span class="quest-done">[DONE]</span>' : '';

    return `
      <div class="quest-entry${q.completed ? ' completed' : ''}">
        <div class="quest-name">${q.name} ${statusLabel}</div>
        ${q.giver ? `<div class="quest-giver">from ${q.giver}</div>` : ''}
        <div class="quest-progress">
          <span class="bar-fill-xp">${progressBar}</span>
          <span class="quest-stage">${q.currentStage}/${q.totalStages}</span>
        </div>
        ${q.description ? `<div class="quest-desc">${q.description.slice(0, 120)}${q.description.length > 120 ? '...' : ''}</div>` : ''}
      </div>
    `;
  }).join('');

  body.innerHTML = html;
}
