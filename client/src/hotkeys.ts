// src/hotkeys.ts
/** Keyboard bindings — hotkeys for panel toggles and modals. */

import { getLastNpcMessage } from './message-handler';

export interface HotkeyRefs {
  exitsWin: { toggle: () => void; visible: boolean };
  questWin: { toggle: () => void; visible: boolean };
  factionWin: { toggle: () => void; visible: boolean };
  invModal: { active: boolean; open: () => void; close: () => void };
  codex: { active: boolean; open: (entityId?: string) => void; close: () => void };
  npcDialog: { show: (npcName: string, npcRole: string, text: string) => void };
  narrative: { canvas: HTMLCanvasElement };
}

export function initHotkeys(refs: HotkeyRefs): void {
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (document.activeElement?.tagName === 'INPUT') return;
    switch (e.key) {
      case 'm':
        // Map is always visible in the unified layout — m toggles world/exits overlay
        refs.exitsWin.toggle();
        break;
      case 'w':
        refs.exitsWin.toggle();
        break;
      case 'q':
        refs.questWin.toggle();
        break;
      case 'f':
        refs.factionWin.toggle();
        break;
      case 'i':
        if (refs.invModal.active) refs.invModal.close();
        else refs.invModal.open();
        break;
      case 'k':
        if (refs.codex.active) refs.codex.close();
        else refs.codex.open();
        break;
      case 'Escape':
        // Dismiss any open overlay or modal (priority: modals first, then overlays)
        if (refs.invModal.active) refs.invModal.close();
        else if (refs.codex.active) refs.codex.close();
        else if (refs.exitsWin.visible) refs.exitsWin.toggle();
        else if (refs.questWin.visible) refs.questWin.toggle();
        else if (refs.factionWin.visible) refs.factionWin.toggle();
        break;
    }
  });

  refs.narrative.canvas.addEventListener('narrative-entity-click', (e: Event) => {
    const { entityId } = (e as CustomEvent).detail;
    refs.codex.open(entityId || undefined);
  });

  refs.narrative.canvas.addEventListener('npc-name-click', (e: Event) => {
    const { npcName } = (e as CustomEvent).detail;
    const lastMsg = getLastNpcMessage(npcName);
    if (lastMsg) refs.npcDialog.show(npcName, '', lastMsg);
  });
}
