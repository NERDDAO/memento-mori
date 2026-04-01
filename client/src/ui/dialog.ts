// client/src/ui/dialog.ts
import { createTypewriter, type TypewriterController } from './typewriter';

export interface Dialog {
  el: HTMLElement;
  show(npcName: string, npcRole: string, text: string): void;
  dismiss(): void;
  readonly active: boolean;
}

const DIALOG_FONT = '15px Georgia, "Times New Roman", serif';
const DIALOG_MAX_WIDTH = 440; // px, inner content width

export function createDialog(): Dialog {
  const backdrop = document.createElement('div');
  backdrop.className = 'dialog-backdrop';
  backdrop.style.display = 'none';

  const win = document.createElement('div');
  win.className = 'dialog-win';

  const titleBar = document.createElement('div');
  titleBar.className = 'win-title dialog-title';

  const body = document.createElement('div');
  body.className = 'win-body dialog-body';

  win.appendChild(titleBar);
  win.appendChild(body);
  backdrop.appendChild(win);

  let currentTw: TypewriterController | null = null;

  function dismiss() {
    if (currentTw) {
      currentTw.cancel();
      currentTw = null;
    }
    backdrop.style.display = 'none';
    body.innerHTML = '';
  }

  // Escape to skip animation or dismiss
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || backdrop.style.display === 'none') return;
    if (currentTw) {
      currentTw.skip();
      currentTw = null;
    } else {
      dismiss();
    }
  });

  // Click backdrop to dismiss
  backdrop.addEventListener('click', (e) => {
    if (e.target === backdrop) dismiss();
  });

  // Click dialog body to skip typewriter
  body.addEventListener('click', () => {
    if (currentTw) {
      currentTw.skip();
      currentTw = null;
    }
  });

  return {
    el: backdrop,
    show(npcName: string, npcRole: string, text: string) {
      if (currentTw) currentTw.cancel();

      titleBar.textContent = `\u2500 ${npcName}${npcRole ? ` \u2014 ${npcRole}` : ''} \u2500`;
      body.innerHTML = '';
      backdrop.style.display = '';

      currentTw = createTypewriter({
        text,
        font: DIALOG_FONT,
        maxWidth: DIALOG_MAX_WIDTH,
        container: body,
        charDelay: 25,
        lineClass: 'tw-line',
        cursorClass: 'tw-cursor',
      });
      currentTw.onComplete(() => { currentTw = null; });
      currentTw.start();
    },
    dismiss,
    get active() {
      return backdrop.style.display !== 'none';
    },
  };
}
