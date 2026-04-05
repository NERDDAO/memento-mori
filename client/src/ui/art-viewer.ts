// src/ui/art-viewer.ts
/**
 * Fullscreen ASCII art viewer overlay.
 * Opens on top of the codex modal (z-index 200 > codex 100).
 */

export interface ArtViewer {
  el: HTMLElement;
  open(entityName: string, artText: string, color: string): void;
  close(): void;
  readonly active: boolean;
}

export function createArtViewer(): ArtViewer {
  const backdrop = document.createElement('div');
  backdrop.style.cssText =
    'position:fixed;inset:0;background:rgba(0,0,0,0.85);' +
    'display:none;align-items:center;justify-content:center;z-index:200;' +
    'flex-direction:column;cursor:pointer;';

  const container = document.createElement('div');
  container.style.cssText =
    'display:flex;flex-direction:column;align-items:center;' +
    'max-width:90vw;max-height:90vh;';

  const title = document.createElement('div');
  title.style.cssText =
    'font-size:14px;letter-spacing:2px;margin-bottom:12px;text-align:center;';

  const pre = document.createElement('pre');
  pre.style.cssText =
    'font-family:"Fira Code",Consolas,"Courier New",monospace;' +
    'font-size:15px;line-height:1.2;margin:0;padding:16px;' +
    'border-radius:3px;white-space:pre;overflow:auto;' +
    'max-height:80vh;';

  const hint = document.createElement('div');
  hint.style.cssText =
    'color:#4a4a58;font-size:11px;margin-top:12px;text-align:center;';
  hint.textContent = '[ESC] or click to close';

  container.appendChild(title);
  container.appendChild(pre);
  container.appendChild(hint);
  backdrop.appendChild(container);

  function close() {
    backdrop.style.display = 'none';
    pre.textContent = '';
  }

  backdrop.addEventListener('click', close);
  container.addEventListener('click', (e) => {
    e.stopPropagation();
    e.preventDefault();
  });

  // Use capture phase so this fires BEFORE codex/dialog ESC handlers,
  // preventing them from closing when the art viewer is on top.
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && backdrop.style.display !== 'none') {
      e.stopImmediatePropagation();
      e.preventDefault();
      close();
    }
  }, true);

  return {
    el: backdrop,
    open(entityName: string, artText: string, color: string) {
      title.textContent = `\u2500 ${entityName} \u2500`;
      title.style.color = color;
      pre.textContent = artText;
      pre.style.color = color;
      pre.style.border = `1px solid ${color}33`;
      backdrop.style.display = 'flex';
    },
    close,
    get active() {
      return backdrop.style.display !== 'none';
    },
  };
}
