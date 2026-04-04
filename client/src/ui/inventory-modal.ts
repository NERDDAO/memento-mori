// client/src/ui/inventory-modal.ts
/**
 * Two-column inventory modal — equipment slots (left) + backpack (right).
 * Actions fire optimistic REST calls via inventory-api.
 */

import type { GameState, InventoryItem } from '../state/game-state';
import { equipItem, unequipItem, dropItem, useItem, pickupItem } from '../state/inventory-api';

export interface InventoryModal {
  el: HTMLElement;
  open(): void;
  close(): void;
  refresh(): void;
  readonly active: boolean;
}

const RARITY_COLORS: Record<string, string> = {
  common: '#808080', uncommon: '#1eff00', rare: '#0070dd', epic: '#a335ee', legendary: '#ff8000',
};

const SLOT_LABELS: Record<string, string> = {
  weapon: 'WPN', armor: 'ARM', accessory: 'ACC', ring: 'RNG',
};

const SLOT_ORDER = ['weapon', 'armor', 'accessory', 'ring'] as const;

export function createInventoryModal(getState: () => GameState): InventoryModal {
  const backdrop = document.createElement('div');
  backdrop.className = 'dialog-backdrop';
  backdrop.style.display = 'none';

  const win = document.createElement('div');
  win.className = 'dialog-win';
  win.style.maxWidth = '600px';
  win.style.width = '90vw';

  backdrop.appendChild(win);

  // Close on backdrop click
  backdrop.addEventListener('click', (e) => {
    if (e.target === backdrop) close();
  });

  // Close on Escape (but not 'i' — that's the open key, handled by app.ts)
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && backdrop.style.display !== 'none') close();
  });

  function close() {
    backdrop.style.display = 'none';
  }

  function open() {
    backdrop.style.display = '';
    refresh();
  }

  function refresh() {
    const state = getState();
    win.innerHTML = '';

    // ── Header ──
    const header = document.createElement('div');
    header.className = 'win-title dialog-title';
    header.style.display = 'flex';
    header.style.justifyContent = 'space-between';
    header.style.alignItems = 'center';

    const title = document.createElement('span');
    title.style.color = '#8b5cf6';
    title.textContent = 'INVENTORY';

    const meta = document.createElement('span');
    meta.style.color = '#6a6a78';
    meta.style.fontSize = '12px';
    const total = state.inventory.length;
    const weight = total * 5;
    meta.textContent = `${weight}/50 wt \u00B7 ${total} items`;

    const closeBtn = document.createElement('span');
    closeBtn.textContent = '[\u00D7]';
    closeBtn.style.color = '#e05050';
    closeBtn.style.cursor = 'pointer';
    closeBtn.onclick = close;

    header.appendChild(title);
    const rightSpan = document.createElement('span');
    rightSpan.appendChild(meta);
    rightSpan.appendChild(document.createTextNode(' '));
    rightSpan.appendChild(closeBtn);
    header.appendChild(rightSpan);
    win.appendChild(header);

    // ── Two-column body ──
    const body = document.createElement('div');
    body.className = 'win-body';
    body.style.display = 'flex';
    body.style.gap = '16px';
    body.style.fontFamily = "'Fira Code', monospace";
    body.style.fontSize = '12px';
    body.style.lineHeight = '1.6';

    // Left: Equipment Slots
    const slotsCol = document.createElement('div');
    slotsCol.style.flex = '1';
    slotsCol.style.minWidth = '0';

    const slotsLabel = document.createElement('div');
    slotsLabel.style.color = '#6a6a78';
    slotsLabel.style.fontSize = '11px';
    slotsLabel.style.marginBottom = '6px';
    slotsLabel.textContent = 'EQUIPMENT SLOTS';
    slotsCol.appendChild(slotsLabel);

    for (const slot of SLOT_ORDER) {
      const label = SLOT_LABELS[slot];
      const item = state.inventory.find(i => i.equipped && i.slot_type === slot);
      const card = createSlotCard(label, slot, item);
      slotsCol.appendChild(card);
    }

    // Right: Backpack
    const packCol = document.createElement('div');
    packCol.style.flex = '1';
    packCol.style.minWidth = '0';

    const backpack = state.inventory.filter(i => !i.equipped);
    const packLabel = document.createElement('div');
    packLabel.style.color = '#6a6a78';
    packLabel.style.fontSize = '11px';
    packLabel.style.marginBottom = '6px';
    packLabel.textContent = `BACKPACK (${backpack.length}/10)`;
    packCol.appendChild(packLabel);

    if (backpack.length === 0) {
      const empty = document.createElement('div');
      empty.style.color = '#3a3a48';
      empty.style.padding = '8px';
      empty.textContent = 'Empty';
      packCol.appendChild(empty);
    } else {
      for (const item of backpack) {
        packCol.appendChild(createBackpackCard(item));
      }
    }

    // Ground items section
    const groundItems = state.location.items;
    if (groundItems.length > 0) {
      const divider = document.createElement('div');
      divider.style.borderTop = '1px solid #1a1a24';
      divider.style.marginTop = '8px';
      divider.style.paddingTop = '8px';
      packCol.appendChild(divider);

      const groundLabel = document.createElement('div');
      groundLabel.style.color = '#6a6a78';
      groundLabel.style.fontSize = '10px';
      groundLabel.textContent = 'GROUND (this room)';
      packCol.appendChild(groundLabel);

      for (const gi of groundItems) {
        const row = document.createElement('div');
        row.style.marginTop = '4px';
        const name = document.createElement('span');
        name.style.color = '#808080';
        name.textContent = gi.name;
        row.appendChild(name);

        const pickup = createActionLink('pickup', '#50c878', async () => {
          const err = await pickupItem(gi.id);
          if (err) console.warn('Pickup failed:', err);
          else refresh();
        });
        row.appendChild(document.createTextNode(' '));
        row.appendChild(pickup);
        packCol.appendChild(row);
      }
    }

    body.appendChild(slotsCol);
    body.appendChild(packCol);
    win.appendChild(body);
  }

  function createSlotCard(label: string, slot: string, item: InventoryItem | undefined): HTMLElement {
    const card = document.createElement('div');
    card.style.border = '1px solid #1a1a24';
    card.style.padding = '8px';
    card.style.marginBottom = '6px';
    card.style.borderRadius = '3px';
    card.style.background = item ? '#12121a' : '#0a0a0f';

    if (item) {
      const color = RARITY_COLORS[item.rarity] || '#808080';
      const top = document.createElement('div');
      top.innerHTML = `<span style="color:#6a6a78">${label}</span> <span style="color:${color}">${item.name}</span>`;
      card.appendChild(top);

      const details = document.createElement('div');
      details.style.color = '#6a6a78';
      details.style.fontSize = '10px';
      details.style.marginTop = '2px';

      const parts = [];
      if (item.effects.length) parts.push(item.effects[0]);
      parts.push(item.rarity);

      const unequipLink = createActionLink('unequip', '#e05050', async () => {
        const err = await unequipItem(slot);
        if (err) console.warn('Unequip failed:', err);
        else refresh();
      });

      details.textContent = parts.join(' \u00B7 ') + ' \u00B7 ';
      details.appendChild(unequipLink);
      card.appendChild(details);
    } else {
      card.innerHTML = `<span style="color:#6a6a78">${label}</span> <span style="color:#3a3a48">\u2014 empty \u2014</span>`;
    }

    return card;
  }

  function createBackpackCard(item: InventoryItem): HTMLElement {
    const card = document.createElement('div');
    card.style.border = '1px solid #1a1a24';
    card.style.padding = '8px';
    card.style.marginBottom = '6px';
    card.style.borderRadius = '3px';
    card.style.background = '#12121a';

    const color = RARITY_COLORS[item.rarity] || '#808080';
    const top = document.createElement('div');
    const nameSpan = `<span style="color:${color}">${item.name}</span>`;
    const qty = item.quantity > 1 ? ` <span style="color:#50c878;font-size:10px">\u00D7${item.quantity}</span>` : '';
    const tag = item.slot_type ? ` <span style="color:#6a6a78;font-size:10px">${item.slot_type}</span>` : '';
    top.innerHTML = nameSpan + qty + tag;
    card.appendChild(top);

    const actions = document.createElement('div');
    actions.style.color = '#6a6a78';
    actions.style.fontSize = '10px';
    actions.style.marginTop = '2px';

    const parts = [];
    if (item.effects.length) parts.push(item.effects[0]);

    actions.textContent = parts.length ? parts.join(' \u00B7 ') + ' \u00B7 ' : '';

    if (item.slot_type) {
      actions.appendChild(createActionLink('equip', '#8b5cf6', async () => {
        const err = await equipItem(item.id, item.slot_type);
        if (err) console.warn('Equip failed:', err);
        else refresh();
      }));
      actions.appendChild(document.createTextNode(' \u00B7 '));
    }

    if (item.is_consumable) {
      actions.appendChild(createActionLink('use', '#50c878', async () => {
        const err = await useItem(item.id);
        if (err) console.warn('Use failed:', err);
        else refresh();
      }));
      actions.appendChild(document.createTextNode(' \u00B7 '));
    }

    if (!item.is_quest_item) {
      actions.appendChild(createActionLink('drop', '#e05050', async () => {
        const err = await dropItem(item.id);
        if (err) console.warn('Drop failed:', err);
        else refresh();
      }));
    }

    card.appendChild(actions);
    return card;
  }

  function createActionLink(text: string, color: string, onClick: () => void): HTMLElement {
    const link = document.createElement('span');
    link.textContent = text;
    link.style.color = color;
    link.style.cursor = 'pointer';
    link.addEventListener('click', (e) => {
      e.stopPropagation();
      onClick();
    });
    return link;
  }

  return {
    el: backdrop,
    open,
    close,
    refresh,
    get active() {
      return backdrop.style.display !== 'none';
    },
  };
}
