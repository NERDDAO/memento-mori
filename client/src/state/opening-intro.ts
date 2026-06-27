// src/state/opening-intro.ts
/**
 * Cinematic opening intro — Memento Mori epigraph fade + name box.
 *
 * Exported:
 *   OPENING_EPIGRAPH   — the epigraph string rendered in the title card
 *   mountOpeningIntro  — mount the overlay, then call onName(name) once the
 *                        player submits their name (or "wanderer" if the markup
 *                        is absent / input is blank)
 */

export const OPENING_EPIGRAPH =
  "Remember that you must die.\nEnter, wanderer, if you dare.";

/**
 * Mount the #opening-intro overlay (if present) and call `onName` exactly
 * once with the player's chosen name, then hide the overlay.
 *
 * Degrade path: if the #opening-intro element is absent (e.g. in tests),
 * call `onName("wanderer")` synchronously and return.
 */
export function mountOpeningIntro(onName: (name: string) => void): void {
  const overlay = document.getElementById("opening-intro");
  if (!overlay) {
    onName("wanderer");
    return;
  }

  // Populate epigraph text lines (newline → <br>).
  const epigraphEl = overlay.querySelector<HTMLElement>(".opening-epigraph");
  if (epigraphEl) {
    epigraphEl.innerHTML = OPENING_EPIGRAPH.replace(/\n/g, "<br>");
  }

  // Show overlay (remove hidden class).
  overlay.classList.remove("hidden");

  // After the CSS fade-in completes (1.6 s), reveal the name box.
  const nameSection = overlay.querySelector<HTMLElement>(
    ".opening-name-section",
  );
  const nameInput = overlay.querySelector<HTMLInputElement>(
    "#opening-name-input",
  );
  const nameBtn = overlay.querySelector<HTMLElement>("#opening-name-btn");

  let called = false;

  function submit(): void {
    if (called) return;
    called = true;
    const raw = nameInput?.value.trim() ?? "";
    const name = raw.length > 0 ? raw : "wanderer";
    overlay!.classList.add("hidden");
    onName(name);
  }

  // Reveal the name box after the title/epigraph has had time to breathe.
  setTimeout(() => {
    if (nameSection) {
      nameSection.classList.remove("hidden");
      nameInput?.focus();
    }
  }, 2400);

  // Wire Enter key on the input.
  if (nameInput) {
    nameInput.addEventListener("keydown", (e: KeyboardEvent) => {
      if (e.key === "Enter") submit();
    });
  }

  // Wire the Enter button.
  if (nameBtn) {
    nameBtn.addEventListener("click", () => submit());
  }
}
