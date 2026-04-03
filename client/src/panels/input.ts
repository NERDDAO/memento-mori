// src/panels/input.ts
/** Input panel — text input with command history, round-phase locking, @mention autocomplete. */

import { onRoundStateChange, type RoundState } from '../state/round-state';
import { createMentionDropdown, type MentionSuggestion } from '../ui/mention-dropdown';

export function initInput(
  inputEl: HTMLInputElement,
  onSubmit: (action: string) => void,
  getContext?: () => { npcs: Array<{name: string}>; players: Array<{name: string}> },
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

  // --- @mention autocomplete ---
  const dropdown = createMentionDropdown();
  let mentionActive = false;
  let mentionStart = -1;

  function getMentionSuggestions(): MentionSuggestion[] {
    if (!getContext) return [];
    const ctx = getContext();
    const suggestions: MentionSuggestion[] = [];
    for (const npc of ctx.npcs) {
      const name = typeof npc === 'string' ? npc : npc.name;
      suggestions.push({ name, type: 'npc' });
    }
    for (const p of ctx.players) {
      const name = typeof p === 'string' ? p : p.name;
      suggestions.push({ name, type: 'player' });
    }
    return suggestions;
  }

  dropdown.onSelect = (name: string) => {
    const before = inputEl.value.slice(0, mentionStart);
    const after = inputEl.value.slice(inputEl.selectionStart || inputEl.value.length);
    inputEl.value = `${before}@${name} ${after}`;
    inputEl.focus();
    mentionActive = false;
    mentionStart = -1;
  };

  inputEl.addEventListener('keydown', (e: KeyboardEvent) => {
    if (locked) return;
    if (mentionActive && dropdown.handleKey(e)) return;

    if (e.key === 'Enter') {
      if (mentionActive) { dropdown.hide(); mentionActive = false; }
      const action = inputEl.value.trim();
      if (action) {
        history.unshift(action);
        historyIndex = -1;
        onSubmit(action);
        inputEl.value = '';
      }
    } else if (e.key === 'ArrowUp' && !mentionActive) {
      e.preventDefault();
      if (historyIndex < history.length - 1) {
        historyIndex++;
        inputEl.value = history[historyIndex];
      }
    } else if (e.key === 'ArrowDown' && !mentionActive) {
      e.preventDefault();
      if (historyIndex > 0) {
        historyIndex--;
        inputEl.value = history[historyIndex];
      } else {
        historyIndex = -1;
        inputEl.value = '';
      }
    } else if (e.key === 'Escape' && mentionActive) {
      dropdown.hide();
      mentionActive = false;
    }
  });

  inputEl.addEventListener('input', () => {
    const val = inputEl.value;
    const cursor = inputEl.selectionStart || val.length;

    if (!mentionActive) {
      if (cursor > 0 && val[cursor - 1] === '@') {
        const charBefore = cursor > 1 ? val[cursor - 2] : ' ';
        if (charBefore === ' ' || charBefore === undefined || cursor === 1) {
          mentionActive = true;
          mentionStart = cursor - 1;
          const suggestions = getMentionSuggestions();
          dropdown.show(suggestions, inputEl);
          dropdown.filter('');
        }
      }
    } else {
      const query = val.slice(mentionStart + 1, cursor);
      if (query.includes(' ') || cursor <= mentionStart) {
        dropdown.hide();
        mentionActive = false;
      } else {
        dropdown.filter(query);
      }
    }
  });
}
