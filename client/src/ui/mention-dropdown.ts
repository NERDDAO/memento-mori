// src/ui/mention-dropdown.ts
/** Floating @mention autocomplete dropdown. */

export interface MentionSuggestion {
  name: string;
  type: 'npc' | 'player';
}

export interface MentionDropdown {
  el: HTMLElement;
  show(suggestions: MentionSuggestion[], anchor: HTMLElement): void;
  hide(): void;
  isVisible(): boolean;
  handleKey(e: KeyboardEvent): boolean;
  onSelect: ((name: string) => void) | null;
  filter(query: string): void;
}

export function createMentionDropdown(): MentionDropdown {
  const el = document.createElement('div');
  el.className = 'mention-dropdown';
  el.style.display = 'none';
  document.body.appendChild(el);

  let items: MentionSuggestion[] = [];
  let filtered: MentionSuggestion[] = [];
  let selectedIndex = 0;
  let selectCallback: ((name: string) => void) | null = null;

  function render(): void {
    el.innerHTML = filtered.map((s, i) => {
      const icon = s.type === 'npc' ? '\u25C6' : '@';
      const cls = i === selectedIndex ? 'mention-item selected' : 'mention-item';
      const typeCls = s.type === 'npc' ? 'mention-npc' : 'mention-player';
      return `<div class="${cls} ${typeCls}" data-index="${i}"><span class="mention-icon">${icon}</span>${s.name}</div>`;
    }).join('');

    el.querySelectorAll('.mention-item').forEach((row) => {
      row.addEventListener('click', () => {
        const idx = parseInt((row as HTMLElement).dataset.index || '0', 10);
        if (filtered[idx] && selectCallback) selectCallback(filtered[idx].name);
        dropdown.hide();
      });
    });
  }

  const dropdown: MentionDropdown = {
    el,
    onSelect: null,

    show(suggestions: MentionSuggestion[], anchor: HTMLElement) {
      items = suggestions;
      filtered = [...items];
      selectedIndex = 0;
      selectCallback = this.onSelect;
      const rect = anchor.getBoundingClientRect();
      el.style.position = 'fixed';
      el.style.bottom = `${window.innerHeight - rect.top + 4}px`;
      el.style.left = `${rect.left}px`;
      el.style.display = '';
      render();
    },

    hide() {
      el.style.display = 'none';
      items = [];
      filtered = [];
    },

    isVisible() {
      return el.style.display !== 'none';
    },

    filter(query: string) {
      const q = query.toLowerCase();
      filtered = q ? items.filter(s => s.name.toLowerCase().startsWith(q)) : [...items];
      selectedIndex = 0;
      render();
      el.style.display = filtered.length > 0 ? '' : 'none';
    },

    handleKey(e: KeyboardEvent): boolean {
      if (!this.isVisible()) return false;
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        selectedIndex = Math.max(0, selectedIndex - 1);
        render();
        return true;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        selectedIndex = Math.min(filtered.length - 1, selectedIndex + 1);
        render();
        return true;
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        if (filtered[selectedIndex] && selectCallback) {
          e.preventDefault();
          selectCallback(filtered[selectedIndex].name);
          this.hide();
          return true;
        }
      }
      if (e.key === 'Escape') {
        this.hide();
        return true;
      }
      return false;
    },
  };

  return dropdown;
}
