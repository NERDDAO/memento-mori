// src/boot/opening-shell.ts
/**
 * Opening-shell boot entry.
 *
 * Assembles the layered baseline:
 *   ProseLayer  → prose region  (typewriter, left pane)
 *   MapLayer    → kgmap region  (KG-backed room box, right pane)
 *   OpeningLoop → drives both layers via the gateway + KG read port
 *
 * This is the new default build entry (bun build src/boot/opening-shell.ts).
 * The old full-panel boot remains buildable via `bun run build:full`.
 */

import { UnifiedCanvas } from "../canvas/unified-canvas";
import { computeOpeningRegions } from "../canvas/region-manager";
import { ProseLayer } from "../layers/prose-layer";
import { MapLayer } from "../layers/map-layer";
import { OpeningLoop, httpGateway } from "../state/opening-loop";
import { httpKgReadPort } from "../state/kg-read-port";
import { initInput } from "../panels/input";
import { textRow } from "../panels/panel-utils";
import { theme } from "../renderer/theme";

document.addEventListener("DOMContentLoaded", () => {
  // 1. Mount the unified canvas with the opening two-pane layout.
  const tuiMain = document.getElementById("tui-main")!;
  const uc = new UnifiedCanvas(tuiMain, computeOpeningRegions);

  // 2. Instantiate layers.
  const prose = new ProseLayer();
  const map   = new MapLayer();

  // 3. redraw() — push both layers into their UC regions.
  function redraw(): void {
    // Prose pane
    const proseRegion = uc.getRegion("prose");
    if (proseRegion) {
      uc.setRegionContent("prose", prose.render(proseRegion.cols, proseRegion.rows));
      uc.markDirty("prose");
    }

    // KG map pane
    const kgmapRegion = uc.getRegion("kgmap");
    if (kgmapRegion) {
      uc.setRegionContent("kgmap", map.render(kgmapRegion.cols, kgmapRegion.rows));
      uc.markDirty("kgmap");
    }
  }

  // 4. renderChips() — write clarify chips into the status row as a single line.
  function renderChips(chips: string[]): void {
    const statusRegion = uc.getRegion("status");
    if (!statusRegion) return;
    const line = chips.join("  ·  ");
    uc.setRegionContent("status", {
      cells: [textRow(line, theme.colors.primary, statusRegion.cols)],
    });
    uc.markDirty("status");
  }

  // 5. Wire the opening loop.
  const loop = new OpeningLoop(prose, map, httpGateway, httpKgReadPort, renderChips, redraw);

  // 6. Wire the action input.
  const actionInput = document.getElementById("action-input") as HTMLInputElement;
  initInput(actionInput, (t) => { void loop.submit(t); });

  // 7. Skip-on-keydown: any keypress outside the input box skips the typewriter.
  //    Mirror the INPUT-focus guard from hotkeys.ts:15 — when #action-input has
  //    focus (which it holds during normal play) this listener is a no-op, so
  //    skip is reachable only when focus leaves the box.  Acceptable for Phase 1
  //    since the 25 ms tick auto-reveals prose continuously.
  document.addEventListener("keydown", () => {
    if (document.activeElement?.tagName === "INPUT") return;
    prose.skip();
    redraw();
  });

  // 8. Typewriter tick: advance one character every 25 ms, repaint when still running.
  setInterval(() => {
    if (prose.tick()) redraw();
  }, 25);

  // 9. Kick off the opening sequence.
  void loop.start();
});
