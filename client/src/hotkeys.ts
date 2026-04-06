// src/hotkeys.ts
/** Keyboard bindings — hotkeys for modals. */

import type { ModalManager } from './canvas/modal-manager';

export interface HotkeyRefs {
  invModal: { active: boolean; open: () => void; close: () => void };
  codex: { active: boolean; open: (entityId?: string) => void; close: () => void };
  npcDialog: { active: boolean; show: (npcName: string, npcRole: string, text: string) => void; dismiss: () => void };
  modalManager: ModalManager;
}

export function initHotkeys(refs: HotkeyRefs): void {
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (document.activeElement?.tagName === 'INPUT') return;
    switch (e.key) {
      case 'i':
        if (refs.invModal.active) refs.invModal.close();
        else refs.invModal.open();
        break;
      case 'k':
        if (refs.codex.active) refs.codex.close();
        else refs.codex.open();
        break;
      case 'Escape':
        // Close the topmost modal
        if (refs.modalManager.active) {
          refs.modalManager.closeTopmost();
        }
        break;
    }
  });
}
