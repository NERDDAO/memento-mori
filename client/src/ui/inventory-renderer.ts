// src/ui/inventory-renderer.ts
/**
 * CharCell-based inventory modal renderer.
 * Replaces the DOM-based inventory-modal.ts.
 */

import type { CharCell } from '../renderer/canvas-text';
import { ATTR_BOLD } from '../renderer/canvas-text';
import type { PanelResult, LocalHitRegion } from '../canvas/types';
import type { ModalManager } from '../canvas/modal-manager';
import type { GameState, InventoryItem } from '../state/game-state';
import { equipItem, unequipItem, dropItem, useItem, pickupItem } from '../state/inventory-api';
import { theme } from '../renderer/theme';
import { textRow, emptyRow, coloredRow } from '../panels/panel-utils';

const MODAL_NAME = 'inventory';

const RARITY_COLORS: Record<string, string> = {
  common: '#808080',
  uncommon: '#1eff00',
  rare: '#0070dd',
  epic: '#a335ee',
  legendary: '#ff8000',
};

const SLOT_ORDER = ['weapon', 'armor', 'accessory', 'ring'] as const;
const SLOT_LABELS: Record<string, string> = {
  weapon: 'WPN',
  armor: 'ARM',
  accessory: 'ACC',
  ring: 'RNG',
};

function itemColor(item: InventoryItem): string {
  return RARITY_COLORS[item.rarity] || '#808080';
}

/** Render the full inventory modal content. */
function renderInventoryContent(
  cols: number,
  rows: number,
  state: GameState,
): PanelResult {
  const cells: CharCell[][] = [];
  const hitRegions: LocalHitRegion[] = [];

  const total = state.inventory.length;
  const weight = total * 5;

  // Header row
  cells.push(
    coloredRow(
      [
        { text: 'INVENTORY', fg: theme.colors.accent, attrs: ATTR_BOLD },
        { text: `  ${weight}/50 wt \u00B7 ${total} items`, fg: theme.colors.dim },
        { text: '  ', fg: theme.colors.dim },
        { text: '[\u00D7]', fg: theme.colors.damage },
      ],
      cols,
    ),
  );

  // Close button hit region
  const closeStart = 'INVENTORY'.length + `  ${weight}/50 wt \u00B7 ${total} items`.length + 2;
  hitRegions.push({
    col: closeStart,
    row: 0,
    width: 3,
    height: 1,
    data: { modalAction: 'close', modal: MODAL_NAME },
  });

  cells.push(
    coloredRow([{ text: '\u2500'.repeat(cols), fg: theme.colors.dim }], cols),
  );

  // Two-column layout: equipment (left half) | backpack (right half)
  const leftCols = Math.floor(cols / 2) - 1;
  const rightCols = cols - leftCols - 1; // 1 col for divider

  // Build left column (equipment) and right column (backpack) separately
  const leftRows: CharCell[][] = [];
  const rightRows: CharCell[][] = [];
  const leftHits: LocalHitRegion[] = [];
  const rightHits: LocalHitRegion[] = [];

  // ── Left: Equipment Slots ──
  leftRows.push(
    coloredRow([{ text: 'EQUIPMENT SLOTS', fg: theme.colors.dim }], leftCols),
  );
  leftRows.push(emptyRow(leftCols));

  for (const slot of SLOT_ORDER) {
    const label = SLOT_LABELS[slot];
    const item = state.inventory.find(i => i.equipped && i.slot_type === slot);

    if (item) {
      const color = itemColor(item);
      leftRows.push(
        coloredRow(
          [
            { text: `${label} `, fg: theme.colors.dim },
            { text: item.name, fg: color },
          ],
          leftCols,
        ),
      );

      // Details line with unequip action
      const detailParts: Array<{ text: string; fg: string }> = [];
      if (item.effects.length) {
        detailParts.push({ text: item.effects[0], fg: theme.colors.dim });
        detailParts.push({ text: ' \u00B7 ', fg: theme.colors.dim });
      }
      detailParts.push({ text: item.rarity, fg: theme.colors.dim });
      detailParts.push({ text: ' \u00B7 ', fg: theme.colors.dim });
      detailParts.push({ text: 'unequip', fg: theme.colors.damage });

      const detailRow = coloredRow(detailParts, leftCols);
      const unequipCol = detailRow.findIndex(
        (c, i) =>
          c.char === 'u' &&
          detailRow[i + 1]?.char === 'n' &&
          detailRow[i + 2]?.char === 'e',
      );
      if (unequipCol >= 0) {
        leftHits.push({
          col: unequipCol,
          row: leftRows.length,
          width: 7,
          height: 1,
          data: { inventoryAction: 'unequip', slot },
        });
      }
      leftRows.push(detailRow);
    } else {
      leftRows.push(
        coloredRow(
          [
            { text: `${label} `, fg: theme.colors.dim },
            { text: '\u2014 empty \u2014', fg: '#3a3a48' },
          ],
          leftCols,
        ),
      );
    }
    leftRows.push(emptyRow(leftCols));
  }

  // ── Right: Backpack ──
  const backpack = state.inventory.filter(i => !i.equipped);

  rightRows.push(
    coloredRow(
      [{ text: `BACKPACK (${backpack.length}/10)`, fg: theme.colors.dim }],
      rightCols,
    ),
  );
  rightRows.push(emptyRow(rightCols));

  if (backpack.length === 0) {
    rightRows.push(
      coloredRow([{ text: 'Empty', fg: '#3a3a48' }], rightCols),
    );
  } else {
    for (const item of backpack) {
      const color = itemColor(item);
      const nameParts: Array<{ text: string; fg: string }> = [
        { text: item.name, fg: color },
      ];
      if (item.quantity > 1) {
        nameParts.push({ text: ` \u00D7${item.quantity}`, fg: theme.colors.heal });
      }
      if (item.slot_type) {
        nameParts.push({ text: ` ${item.slot_type}`, fg: theme.colors.dim });
      }
      rightRows.push(coloredRow(nameParts, rightCols));

      // Action row
      const actionParts: Array<{ text: string; fg: string }> = [];
      if (item.effects.length) {
        actionParts.push({ text: item.effects[0], fg: theme.colors.dim });
        actionParts.push({ text: ' \u00B7 ', fg: theme.colors.dim });
      }

      const actionRow: Array<{ text: string; fg: string; action?: string }> = [...actionParts];
      if (item.slot_type) {
        actionRow.push({ text: 'equip', fg: theme.colors.accent, action: 'equip' });
        actionRow.push({ text: ' \u00B7 ', fg: theme.colors.dim });
      }
      if (item.is_consumable) {
        actionRow.push({ text: 'use', fg: theme.colors.heal, action: 'use' });
        actionRow.push({ text: ' \u00B7 ', fg: theme.colors.dim });
      }
      if (!item.is_quest_item) {
        actionRow.push({ text: 'drop', fg: theme.colors.damage, action: 'drop' });
      }

      const rowCells = coloredRow(
        actionRow.map(a => ({ text: a.text, fg: a.fg })),
        rightCols,
      );
      rightRows.push(rowCells);

      // Register hit regions for actions
      let offset = 0;
      for (const part of actionRow) {
        if ('action' in part && part.action) {
          rightHits.push({
            col: offset + leftCols + 1, // right column offset
            row: rightRows.length - 1,
            width: part.text.length,
            height: 1,
            data: { inventoryAction: part.action, itemId: item.id, slot: item.slot_type },
          });
        }
        offset += part.text.length;
      }

      rightRows.push(emptyRow(rightCols));
    }
  }

  // Ground items
  const groundItems = state.location.items;
  if (groundItems.length > 0) {
    rightRows.push(
      coloredRow(
        [{ text: '\u2500'.repeat(rightCols), fg: theme.colors.dim }],
        rightCols,
      ),
    );
    rightRows.push(
      coloredRow(
        [{ text: 'GROUND (this room)', fg: theme.colors.dim }],
        rightCols,
      ),
    );
    rightRows.push(emptyRow(rightCols));

    for (const gi of groundItems) {
      const row = coloredRow(
        [
          { text: gi.name, fg: '#808080' },
          { text: ' ', fg: theme.colors.dim },
          { text: 'pickup', fg: theme.colors.heal },
        ],
        rightCols,
      );
      rightRows.push(row);

      // Hit region for pickup
      const pickupCol = gi.name.length + 1;
      rightHits.push({
        col: pickupCol + leftCols + 1,
        row: rightRows.length - 1,
        width: 6,
        height: 1,
        data: { inventoryAction: 'pickup', itemId: gi.id },
      });
    }
  }

  // Merge left + divider + right into combined rows
  const maxRows = Math.max(leftRows.length, rightRows.length);
  const dividerChar: CharCell = { char: '\u2502', fg: theme.colors.dim };

  for (let r = 0; r < maxRows; r++) {
    const left = leftRows[r] || emptyRow(leftCols);
    const right = rightRows[r] || emptyRow(rightCols);
    const combinedRow: CharCell[] = [
      ...left.slice(0, leftCols),
      dividerChar,
      ...right.slice(0, rightCols),
    ];
    // Pad to cols if needed
    while (combinedRow.length < cols) {
      combinedRow.push({ char: ' ', fg: theme.colors.primary });
    }
    cells.push(combinedRow);
  }

  // Adjust hit region rows: left hits are relative to the merged area (start after header)
  const headerRowCount = 2; // header + separator
  for (const h of leftHits) {
    h.row += headerRowCount;
  }
  for (const h of rightHits) {
    h.row += headerRowCount;
  }
  hitRegions.push(...leftHits, ...rightHits);

  return { cells, hitRegions };
}

// ── Inventory Controller ────────────────────────────────────────

export interface InventoryModalController {
  open(): void;
  close(): void;
  refresh(): void;
  readonly active: boolean;
}

export function createInventoryController(
  mm: ModalManager,
  getState: () => GameState,
  renderAllPanels: () => void,
  addEvent: (text: string, style: string) => void,
): InventoryModalController {
  function refresh(): void {
    if (!mm.isOpen(MODAL_NAME)) return;
    const state = getState();
    const modal = mm.getStack().find(m => m.name === MODAL_NAME);
    if (!modal) return;
    const contentCols = modal.region.cols - 2;
    const contentRows = modal.region.rows - 2;
    mm.setContent(MODAL_NAME, renderInventoryContent(contentCols, contentRows, state));
  }

  function open(): void {
    mm.open(MODAL_NAME, 0.6, 0.6);
    refresh();
  }

  function close(): void {
    mm.close(MODAL_NAME);
  }

  return {
    open,
    close,
    refresh,
    get active() {
      return mm.isOpen(MODAL_NAME);
    },
  };
}

/** Handle inventory action clicks dispatched from the hit registry. */
export async function handleInventoryAction(
  data: Record<string, unknown>,
  refreshFn: () => void,
): Promise<void> {
  const action = data.inventoryAction as string;
  let err: string | null = null;

  switch (action) {
    case 'equip':
      err = await equipItem(data.itemId as string, data.slot as string);
      break;
    case 'unequip':
      err = await unequipItem(data.slot as string);
      break;
    case 'drop':
      err = await dropItem(data.itemId as string);
      break;
    case 'use':
      err = await useItem(data.itemId as string);
      break;
    case 'pickup':
      err = await pickupItem(data.itemId as string);
      break;
  }

  if (err) {
    console.warn(`Inventory ${action} failed:`, err);
  } else {
    refreshFn();
  }
}
