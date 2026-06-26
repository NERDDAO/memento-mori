import { test, expect } from "bun:test";
import { ProseLayer } from "./prose-layer";
import { theme } from "../renderer/theme";
import type { CharCell } from "../renderer/canvas-text";

const joinCells = (r: { cells: { char: string }[][] }) =>
  r.cells.map(row => row.map(c => c.char).join("").trimEnd()).join("\n").trim();

// Reveal everything so the typewriter prefix doesn't truncate the assertion.
function fullyRevealed(layer: ProseLayer): ProseLayer {
  layer.skip();
  return layer;
}

// Pull the fg color of the first non-space character in a rendered result.
// PanelResult.cells is CharCell[][] — each element is a CharCell[] row,
// and each CharCell has .char and .fg directly (no nested .cells wrapper).
function firstInkColor(cells: CharCell[][]): string | undefined {
  for (const row of cells) {
    for (const cell of row) {
      if (cell.char && cell.char !== " ") return cell.fg;
    }
  }
  return undefined;
}

test("enqueue + skip reveals full text wrapped to cols", () => {
  const p = new ProseLayer();
  p.enqueue({ text: "the blade lies still", kind: "narration" });
  p.skip();
  expect(joinCells(p.render(10, 6)).replace(/\n/g, " ")).toContain("the blade lies still");
  expect(p.tick()).toBe(false);
});
test("tick reveals one char at a time", () => {
  const p = new ProseLayer();
  p.enqueue({ text: "ab", kind: "narration" });
  expect(joinCells(p.render(20, 4))).toBe("");
  expect(p.tick()).toBe(true);
  expect(joinCells(p.render(20, 4))).toBe("a");
  p.tick();
  expect(joinCells(p.render(20, 4))).toBe("ab");
});

test("npc-dialogue renders in the NPC color", () => {
  const layer = new ProseLayer();
  layer.enqueue({ text: "You may pass.", kind: "npc-dialogue", speaker: "a dying adventurer" });
  fullyRevealed(layer);
  const color = firstInkColor(layer.render(40, 10).cells);
  expect(color).toBe(theme.colors.npc);
});

test("narration stays in the primary color", () => {
  const layer = new ProseLayer();
  layer.enqueue({ text: "The roads are dark.", kind: "narration" });
  fullyRevealed(layer);
  const color = firstInkColor(layer.render(40, 10).cells);
  expect(color).toBe(theme.colors.primary);
});
