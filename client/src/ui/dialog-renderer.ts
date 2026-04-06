// src/ui/dialog-renderer.ts
/**
 * CharCell-based dialog renderer with typewriter animation.
 * Replaces the DOM-based dialog.ts.
 */

import type { CharCell } from '../renderer/canvas-text';
import { ATTR_BOLD } from '../renderer/canvas-text';
import type { PanelResult } from '../canvas/types';
import type { ModalManager } from '../canvas/modal-manager';
import { theme } from '../renderer/theme';
import { textRow, emptyRow, coloredRow } from '../panels/panel-utils';

const MODAL_NAME = 'dialog';
const CHAR_DELAY = 25;
const QUEST_CHAR_DELAY = 15;

/** Word-wrap text to fit within `cols` characters. */
function wordWrap(text: string, cols: number): string[] {
  const lines: string[] = [];
  for (const paragraph of text.split('\n')) {
    if (paragraph.length === 0) {
      lines.push('');
      continue;
    }
    const words = paragraph.split(/\s+/);
    let current = '';
    for (const word of words) {
      if (current.length === 0) {
        current = word;
      } else if (current.length + 1 + word.length <= cols) {
        current += ' ' + word;
      } else {
        lines.push(current);
        current = word;
      }
    }
    if (current.length > 0) lines.push(current);
  }
  return lines;
}

/** Render dialog content as CharCell[][]. If visibleChars is set, truncate for typewriter. */
function renderDialogContent(
  cols: number,
  npcName: string,
  npcRole: string,
  wrappedLines: string[],
  visibleChars?: number,
): PanelResult {
  const cells: CharCell[][] = [];

  // Row 0: NPC name + role
  const titleText = npcRole ? `${npcName} \u2014 ${npcRole}` : npcName;
  cells.push(
    coloredRow(
      [{ text: titleText, fg: theme.colors.npc, attrs: ATTR_BOLD }],
      cols,
    ),
  );

  // Row 1: separator
  const sepLen = Math.min(titleText.length + 2, cols);
  cells.push(
    coloredRow(
      [{ text: '\u2500'.repeat(sepLen), fg: theme.colors.dim }],
      cols,
    ),
  );

  // Row 2: blank
  cells.push(emptyRow(cols));

  // Rows 3+: word-wrapped text with optional typewriter truncation
  let charsShown = 0;
  const totalVisible = visibleChars ?? Infinity;

  for (const line of wrappedLines) {
    if (charsShown >= totalVisible && visibleChars !== undefined) break;
    const row: CharCell[] = [];
    for (let i = 0; i < line.length; i++) {
      if (charsShown < totalVisible) {
        row.push({ char: line[i], fg: theme.colors.primary });
        charsShown++;
      }
    }
    // Pad to cols
    while (row.length < cols) {
      row.push({ char: ' ', fg: theme.colors.primary });
    }
    cells.push(row);
  }

  // Add cursor if typewriter is still going
  if (visibleChars !== undefined && charsShown < totalCharsInLines(wrappedLines)) {
    // Find the last non-empty row and add a blinking cursor char
    for (let r = cells.length - 1; r >= 3; r--) {
      const lastCharIdx = cells[r].findIndex(
        (c, i) => i > 0 && cells[r][i - 1].char !== ' ' && c.char === ' ',
      );
      if (lastCharIdx > 0) {
        cells[r][lastCharIdx] = { char: '\u2588', fg: theme.colors.accent };
        break;
      } else if (cells[r].some(c => c.char !== ' ')) {
        // Row is full or last char is at end
        const len = cells[r].filter(c => c.char !== ' ').length;
        if (len < cols) {
          cells[r][len] = { char: '\u2588', fg: theme.colors.accent };
        }
        break;
      }
    }
  }

  // Bottom: dismiss hint
  cells.push(emptyRow(cols));
  cells.push(
    coloredRow(
      [{ text: '[Esc] dismiss  [click] skip', fg: theme.colors.dim }],
      cols,
    ),
  );

  return { cells };
}

function totalCharsInLines(lines: string[]): number {
  let total = 0;
  for (const line of lines) total += line.length;
  return total;
}

/** Render quest dialog content. */
function renderQuestContent(
  cols: number,
  quest: { name: string; description: string; currentStage: number; totalStages: number; giver: string; completed: boolean },
  wrappedLines: string[],
  visibleChars?: number,
): PanelResult {
  const cells: CharCell[][] = [];

  // Title
  const status = quest.completed ? ' [COMPLETE]' : '';
  const titleText = `${quest.name}${status}`;
  cells.push(
    coloredRow(
      [{ text: titleText, fg: theme.colors.accent, attrs: ATTR_BOLD }],
      cols,
    ),
  );

  // Separator
  const sepLen = Math.min(titleText.length + 2, cols);
  cells.push(
    coloredRow(
      [{ text: '\u2500'.repeat(sepLen), fg: theme.colors.dim }],
      cols,
    ),
  );
  cells.push(emptyRow(cols));

  // Content with typewriter
  let charsShown = 0;
  const totalVisible = visibleChars ?? Infinity;

  for (const line of wrappedLines) {
    if (charsShown >= totalVisible && visibleChars !== undefined) break;
    const row: CharCell[] = [];
    for (let i = 0; i < line.length; i++) {
      if (charsShown < totalVisible) {
        // Color the progress bar characters
        const isBarChar = line[i] === '\u2588' || line[i] === '\u2591';
        const fg = isBarChar
          ? line[i] === '\u2588'
            ? theme.colors.heal
            : theme.colors.dim
          : theme.colors.primary;
        row.push({ char: line[i], fg });
        charsShown++;
      }
    }
    while (row.length < cols) {
      row.push({ char: ' ', fg: theme.colors.primary });
    }
    cells.push(row);
  }

  cells.push(emptyRow(cols));
  cells.push(
    coloredRow(
      [{ text: '[Esc] dismiss', fg: theme.colors.dim }],
      cols,
    ),
  );

  return { cells };
}

// ── Dialog Controller ───────────────────────────────────────────

export interface DialogController {
  show(npcName: string, npcRole: string, text: string): void;
  showQuest(quest: {
    name: string;
    description: string;
    currentStage: number;
    totalStages: number;
    giver: string;
    completed: boolean;
  }): void;
  dismiss(): void;
  readonly active: boolean;
  /** For message-handler compatibility */
  refreshEntityArt?: undefined;
  refresh?: undefined;
}

export function createDialogController(mm: ModalManager): DialogController {
  let _timer: ReturnType<typeof setInterval> | null = null;
  let _visibleChars = 0;
  let _totalChars = 0;
  let _animating = false;

  function stopAnimation(): void {
    if (_timer) {
      clearInterval(_timer);
      _timer = null;
    }
    _animating = false;
  }

  function skipAnimation(): void {
    if (!_animating) return;
    stopAnimation();
    _visibleChars = _totalChars;
    // Re-render with all chars visible
    const modal = mm.getStack().find(m => m.name === MODAL_NAME);
    if (modal?.renderFn) {
      mm.setContent(MODAL_NAME, modal.renderFn());
    }
  }

  function dismiss(): void {
    stopAnimation();
    mm.close(MODAL_NAME);
  }

  function show(npcName: string, npcRole: string, text: string): void {
    stopAnimation();

    const state = mm.open(MODAL_NAME, 0.5, 0.4);
    const contentCols = state.region.cols - 2;

    const wrappedLines = wordWrap(text, contentCols);
    _totalChars = totalCharsInLines(wrappedLines);
    _visibleChars = 0;
    _animating = true;

    const renderFn = () =>
      renderDialogContent(contentCols, npcName, npcRole, wrappedLines, _animating ? _visibleChars : undefined);

    state.renderFn = renderFn;
    mm.setContent(MODAL_NAME, renderFn());

    _timer = setInterval(() => {
      _visibleChars++;
      if (_visibleChars >= _totalChars) {
        stopAnimation();
      }
      mm.setContent(MODAL_NAME, renderFn());
    }, CHAR_DELAY);
  }

  function showQuest(quest: {
    name: string;
    description: string;
    currentStage: number;
    totalStages: number;
    giver: string;
    completed: boolean;
  }): void {
    stopAnimation();

    const state = mm.open(MODAL_NAME, 0.5, 0.4);
    const contentCols = state.region.cols - 2;

    // Build quest text
    const lines: string[] = [];
    if (quest.giver) lines.push(`Quest giver: ${quest.giver}`);
    lines.push('');
    lines.push(quest.description);
    lines.push('');
    const filled =
      quest.totalStages > 0
        ? Math.round((quest.currentStage / quest.totalStages) * 10)
        : 0;
    const bar =
      '\u2588'.repeat(Math.min(10, filled)) +
      '\u2591'.repeat(10 - Math.min(10, filled));
    lines.push(`Progress: ${bar} ${quest.currentStage}/${quest.totalStages}`);

    const wrappedLines = wordWrap(lines.join('\n'), contentCols);
    _totalChars = totalCharsInLines(wrappedLines);
    _visibleChars = 0;
    _animating = true;

    const renderFn = () =>
      renderQuestContent(contentCols, quest, wrappedLines, _animating ? _visibleChars : undefined);

    state.renderFn = renderFn;
    mm.setContent(MODAL_NAME, renderFn());

    _timer = setInterval(() => {
      _visibleChars++;
      if (_visibleChars >= _totalChars) {
        stopAnimation();
      }
      mm.setContent(MODAL_NAME, renderFn());
    }, QUEST_CHAR_DELAY);
  }

  // Handle Escape and click-to-skip within the modal
  // (wired externally via hotkeys or app.ts click handler)

  return {
    show,
    showQuest,
    dismiss,
    get active() {
      return mm.isOpen(MODAL_NAME);
    },
  };
}
