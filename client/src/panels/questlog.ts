// client/src/panels/questlog.ts
import type { CharCell } from '../renderer/canvas-text';
import type { PanelResult, LocalHitRegion } from '../canvas/types';
import { theme } from '../renderer/theme';
import { textRow, coloredRow, emptyRow } from './panel-utils';

export interface QuestEntry {
  name: string;
  description: string;
  currentStage: number;
  totalStages: number;
  giver: string;
  completed: boolean;
}


export function renderQuestLogPanel(cols: number, _rows: number, quests: QuestEntry[]): PanelResult {
  const cells: CharCell[][] = [];
  const hitRegions: LocalHitRegion[] = [];

  if (!quests || quests.length === 0) {
    cells.push(textRow('No active quests', theme.colors.dim, cols));
    return { cells };
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
    hitRegions.push({
      col: 0,
      row: questStartRow,
      width: cols,
      height: questEndRow - questStartRow,
      data: { questName: q.name },
    });
  }

  return { cells, hitRegions };
}
