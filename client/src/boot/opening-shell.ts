// src/boot/opening-shell.ts
/**
 * Opening-shell boot entry — the new default build entry
 * (bun build src/boot/opening-shell.ts). The old full-panel boot remains
 * buildable via `bun run build:full`.
 *
 * Assembles the layered baseline:
 *   ProseLayer          → prose region (typewriter, left pane)
 *   RoomViewportAdapter → kgmap region (the EXISTING roguelike room renderer +
 *                         player movement, blitted in via uc.setOffscreen)
 *
 * The opening data path (/api/opening/{start,act} + /room/{uuid}/contents) is
 * orchestrated inline: `look` (re)builds the room viewport client-side, since
 * engine comprehension is currently degraded.
 */

import { UnifiedCanvas } from "../canvas/unified-canvas";
import { computeOpeningRegions } from "../canvas/region-manager";
import { ProseLayer } from "../layers/prose-layer";
import { RoomViewportAdapter } from "../layers/room-viewport";
import { httpGateway, type ActResp } from "../state/opening-loop";
import { httpKgReadPort } from "../state/kg-read-port";
import { initInput } from "../panels/input";
import { connectOpeningWs, routeOpeningMessage, type OpeningSurfaces } from "../state/opening-ws";

document.addEventListener("DOMContentLoaded", () => {
  // 1. Mount the unified canvas with the opening two-pane layout.
  const tuiMain = document.getElementById("tui-main")!;
  const uc = new UnifiedCanvas(tuiMain, computeOpeningRegions);

  // 2. Prose (CharCell typewriter) + the room viewport (pixel canvas blitted in).
  const prose = new ProseLayer();
  const viewport = new RoomViewportAdapter(() => {
    uc.setOffscreen("kgmap", viewport.canvas);
    uc.markDirty("kgmap");
  });

  // 3. redrawProse() — push the prose layer into its region.
  function redrawProse(): void {
    const region = uc.getRegion("prose");
    if (region) {
      uc.setRegionContent("prose", prose.render(region.cols, region.rows));
      uc.markDirty("prose");
    }
  }

  // 4. Opening-arc state + orchestration.
  let playerId = "";
  let currentRoom = "";
  let ended = false;

  async function refreshContents(): Promise<void> {
    const things = await httpKgReadPort.getRoomContents(playerId, currentRoom);
    viewport.setContents(currentRoom, things); // self-blits via onChange
  }

  async function start(): Promise<void> {
    const s = await httpGateway.start();
    playerId = s.player_id;
    currentRoom = s.location_id;
    (window as unknown as { __mmPlayerId?: string }).__mmPlayerId = playerId;

    prose.enqueue({ text: s.epigraph, kind: "epigraph" });
    prose.enqueue({ text: s.location_name, kind: "location" });
    prose.enqueue({ text: s.description, kind: "description" });
    redrawProse();

    viewport.visitRoom({ uuid: s.location_id, name: s.location_name }, s.exits);
    await refreshContents();

    const surfaces: OpeningSurfaces = {
      prose,
      redrawProse,
      viewport,
      roomUuid: () => currentRoom,
    };
    connectOpeningWs(playerId, (msg) => routeOpeningMessage(msg, surfaces));
  }

  // `look` rebuilds the room viewport client-side (comprehension is degraded).
  async function look(): Promise<void> {
    prose.enqueue({ text: "You look around.", kind: "narration" });
    redrawProse();
    await refreshContents();
  }

  async function act(text: string): Promise<void> {
    let r: ActResp;
    try {
      r = await httpGateway.act(playerId, text);
    } catch {
      return;
    }
    // clarify carries `message`; narrated/executed carry `narration`.
    const line = r.narration ?? (r as { message?: string }).message ?? "";
    if (line) prose.enqueue({ text: line, kind: r.status === "clarify" ? "prompt" : "narration" });
    if (r.won) ended = true;
    redrawProse();
    if (!ended) await refreshContents();
  }

  function submit(text: string): void {
    if (ended) return;
    if (/^\s*look\b/i.test(text)) { void look(); return; }
    void act(text);
  }

  // 5. Wire the action input.
  const actionInput = document.getElementById("action-input") as HTMLInputElement;
  initInput(actionInput, submit);

  // 6. WASD/hjkl/arrows move the player in the room (reuses the existing
  //    movement system; its own INPUT-focus guard ignores keys while typing).
  viewport.attachInput();

  // 7. Skip-on-keydown: a keypress outside the input box skips the typewriter.
  //    (Movement keys are handled by attachInput; this also skips, which is fine.)
  document.addEventListener("keydown", () => {
    if (document.activeElement?.tagName === "INPUT") return;
    prose.skip();
    redrawProse();
  });

  // 8. Typewriter tick: advance one character every 25 ms.
  setInterval(() => {
    if (prose.tick()) redrawProse();
  }, 25);

  // 9. Show the empty room shell immediately, then kick off the opening.
  viewport.render();
  void start();
});
