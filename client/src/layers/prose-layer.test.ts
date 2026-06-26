import { test, expect } from "bun:test";
import { ProseLayer } from "./prose-layer";
const joinCells = (r: { cells: { char: string }[][] }) =>
  r.cells.map(row => row.map(c => c.char).join("").trimEnd()).join("\n").trim();

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
