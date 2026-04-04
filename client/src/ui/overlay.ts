/**
 * Named overlay manager — controls visibility of full-screen overlays.
 * Only one overlay is visible at a time.
 */

export interface OverlayManager {
  show(name: string): void;
  dismiss(name: string): void;
  onDismiss(name: string, cb: () => void): void;
  current(): string | null;
}

export function createOverlayManager(names: string[]): OverlayManager {
  const elements = new Map<string, HTMLElement>();
  const callbacks = new Map<string, Array<() => void>>();
  let currentName: string | null = null;

  for (const name of names) {
    const el = document.getElementById(`${name}-overlay`);
    if (el) elements.set(name, el);
    callbacks.set(name, []);
  }

  function show(name: string): void {
    // Hide current overlay if any
    if (currentName && currentName !== name) {
      const prev = elements.get(currentName);
      if (prev) prev.classList.add('hidden');
    }
    const el = elements.get(name);
    if (el) {
      el.classList.remove('hidden');
      currentName = name;
    }
  }

  function dismiss(name: string): void {
    const el = elements.get(name);
    if (el) el.classList.add('hidden');
    if (currentName === name) currentName = null;
    for (const cb of callbacks.get(name) || []) cb();
  }

  function onDismiss(name: string, cb: () => void): void {
    const list = callbacks.get(name);
    if (list) list.push(cb);
  }

  return {
    show,
    dismiss,
    onDismiss,
    current: () => currentName,
  };
}
