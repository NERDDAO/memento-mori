/**
 * Inventory API — structured actions with optimistic updates.
 *
 * Pattern: apply optimistic state immediately → fire REST call →
 * if error, revert. Server broadcasts state_update via WebSocket
 * which replaces the optimistic state with confirmed state.
 */

import type { GameState, InventoryItem } from './game-state';

const API_BASE = '/api/inventory';

type RenderCallback = () => void;

let _state: GameState | null = null;
let _playerId = '';
let _onRender: RenderCallback | null = null;

export function initInventoryApi(
  state: GameState,
  playerId: string,
  onRender: RenderCallback,
): void {
  _state = state;
  _playerId = playerId;
  _onRender = onRender;
}

function rerender(): void {
  if (_onRender) _onRender();
}

/** Snapshot current inventory for rollback on error. */
function snapshot(): InventoryItem[] {
  return _state ? _state.inventory.map(i => ({ ...i })) : [];
}

function rollback(saved: InventoryItem[]): void {
  if (_state) {
    _state.inventory = saved;
    rerender();
  }
}

async function post(path: string, body: Record<string, unknown>): Promise<{ ok: boolean; detail?: string }> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      return { ok: false, detail: err.detail || `HTTP ${res.status}` };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, detail: String(e) };
  }
}


// ── Public Actions ──


export async function equipItem(itemId: string, slot: string): Promise<string | null> {
  if (!_state) return 'Not initialized';
  const saved = snapshot();

  // Optimistic: move item to equipped
  const item = _state.inventory.find(i => i.id === itemId);
  if (!item) return 'Item not found';

  // Unequip current occupant of slot
  const current = _state.inventory.find(i => i.equipped && i.slot_type === slot);
  if (current) current.equipped = false;

  item.equipped = true;
  item.slot_type = slot;
  rerender();

  const result = await post('/equip', { player_id: _playerId, item_id: itemId, slot });
  if (!result.ok) {
    rollback(saved);
    return result.detail || 'Equip failed';
  }
  return null;
}


export async function unequipItem(slot: string): Promise<string | null> {
  if (!_state) return 'Not initialized';
  const saved = snapshot();

  const item = _state.inventory.find(i => i.equipped && i.slot_type === slot);
  if (!item) return 'No item in slot';

  item.equipped = false;
  rerender();

  const result = await post('/unequip', { player_id: _playerId, slot });
  if (!result.ok) {
    rollback(saved);
    return result.detail || 'Unequip failed';
  }
  return null;
}


export async function dropItem(itemId: string, quantity?: number): Promise<string | null> {
  if (!_state) return 'Not initialized';
  const saved = snapshot();

  // Optimistic: remove from inventory
  const idx = _state.inventory.findIndex(i => i.id === itemId);
  if (idx === -1) return 'Item not found';

  const item = _state.inventory[idx];
  if (quantity && item.quantity > quantity) {
    item.quantity -= quantity;
  } else {
    _state.inventory.splice(idx, 1);
  }
  rerender();

  const result = await post('/drop', { player_id: _playerId, item_id: itemId, quantity });
  if (!result.ok) {
    rollback(saved);
    return result.detail || 'Drop failed';
  }
  return null;
}


export async function useItem(itemId: string): Promise<string | null> {
  if (!_state) return 'Not initialized';
  const saved = snapshot();

  const idx = _state.inventory.findIndex(i => i.id === itemId);
  if (idx === -1) return 'Item not found';

  const item = _state.inventory[idx];
  if (item.quantity > 1) {
    item.quantity -= 1;
  } else {
    _state.inventory.splice(idx, 1);
  }
  rerender();

  const result = await post('/use', { player_id: _playerId, item_id: itemId });
  if (!result.ok) {
    rollback(saved);
    return result.detail || 'Use failed';
  }
  return null;
}


export async function pickupItem(itemId: string): Promise<string | null> {
  if (!_state) return 'Not initialized';
  const saved = snapshot();

  // Optimistic: add to inventory (we don't have full metadata yet,
  // but the WebSocket state_update will replace with real data)
  _state.inventory.push({
    id: itemId,
    name: '...',  // placeholder until state_update arrives
    rarity: 'common',
    slot_type: '',
    equipped: false,
    is_consumable: false,
    is_quest_item: false,
    effects: [],
    quantity: 1,
  });
  rerender();

  const result = await post('/pickup', { player_id: _playerId, item_id: itemId });
  if (!result.ok) {
    rollback(saved);
    return result.detail || 'Pickup failed';
  }
  return null;
}
