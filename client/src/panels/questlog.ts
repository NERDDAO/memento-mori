// client/src/panels/questlog.ts
import type { TerminalPanel } from '../ui/terminal-panel';
import type { CharCell } from '../renderer/canvas-text';
import { theme } from '../renderer/theme';

export interface QuestEntry {
  name: string;
  description: string;
  currentStage: number;
  totalStages: number;
  giver: string;
  completed: boolean;
}

function coloredRow(segments: Array<{ text: string; fg: string; attrs?: number }>, cols: number): CharCell[] {
  const row: CharCell[] = [];
  for (const seg of segments) {
    for (const ch of seg.text) {
      row.push({ char: ch, fg: seg.fg, attrs: seg.attrs });
    }
  }
  while (row.length < cols) {
    row.push({ char: ' ', fg: theme.colors.primary });
  }
  return row;
}

function textRow(text: string, fg: string, cols: number): CharCell[] {
  const row: CharCell[] = [];
  for (let i = 0; i < cols; i++) {
    row.push({ char: i < text.length ? text[i] : ' ', fg });
  }
  return row;
}

function emptyRow(cols: number): CharCell[] {
  return Array(cols).fill({ char: ' ', fg: theme.colors.primary });
}

export function renderQuestLogPanel(panel: TerminalPanel, quests: QuestEntry[]): void {
  const cols = panel.cols;
  const cells: CharCell[][] = [];

  if (!quests || quests.length === 0) {
    cells.push(textRow('No active quests', theme.colors.dim, cols));
    panel.paint(cells);
    return;
  }

  for (let i = 0; i < quests.length; i++) {
    const q = quests[i];
    if (i > 0) cells.push(emptyRow(cols));

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
  }

  panel.paint(cells);
}
