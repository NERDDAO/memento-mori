// src/panels/input.ts
/** Input panel — text input with command history navigation and round-phase locking. */

import { onRoundStateChange, type RoundState } from '../state/round-state';

export function initInput(
  inputEl: HTMLInputElement,
  onSubmit: (action: string) => void,
): void {
  const history: string[] = [];
  let historyIndex = -1;
  let locked = false;
  const defaultPlaceholder = inputEl.placeholder || 'What do you do?';

  function setLocked(isLocked: boolean): void {
    locked = isLocked;
    inputEl.disabled = isLocked;
    inputEl.classList.toggle('input-locked', isLocked);
  }

  onRoundStateChange((rs: RoundState) => {
    switch (rs.phase) {
      case 'ready':
        setLocked(false);
        inputEl.placeholder = defaultPlaceholder;
        break;
      case 'collecting': {
        setLocked(false);
        const timer = rs.secondsLeft != null ? `${rs.secondsLeft}s left to act...` : 'Round open...';
        inputEl.placeholder = timer;
        break;
      }
      case 'resolving':
        setLocked(true);
        inputEl.placeholder = 'Resolving...';
        break;
      case 'npc_response':
        setLocked(true);
        inputEl.placeholder = 'NPCs responding...';
        break;
    }
  });

  inputEl.addEventListener('keydown', (e: KeyboardEvent) => {
    if (locked) return;
    if (e.key === 'Enter') {
      const action = inputEl.value.trim();
      if (action) {
        history.unshift(action);
        historyIndex = -1;
        onSubmit(action);
        inputEl.value = '';
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (historyIndex < history.length - 1) {
        historyIndex++;
        inputEl.value = history[historyIndex];
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyIndex > 0) {
        historyIndex--;
        inputEl.value = history[historyIndex];
      } else {
        historyIndex = -1;
        inputEl.value = '';
      }
    }
  });
}
