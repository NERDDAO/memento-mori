import { test, expect } from "bun:test";
import { MapLayer } from "./map-layer";
const flat = (r: { cells: { char: string }[][] }) => r.cells.map(row => row.map(c => c.char).join("")).join("\n");

test("visited room shows name, things and exits", () => {
  const m = new MapLayer();
  m.visitRoom({ uuid: "r1", name: "the deep roads" }, [{ direction: "down", target_id: "r2" }]);
  m.setContents("r1", [{ uuid: "e1", name: "a dying adventurer" }, { uuid: "e2", name: "an iron blade" }]);
  const out = flat(m.render(40, 20));
  expect(out).toContain("the deep roads");
  expect(out).toContain("a dying adventurer");
  expect(out).toContain("an iron blade");
  expect(m.currentExits()).toEqual([{ direction: "down", targetId: "r2" }]);
});
test("unentered neighbor renders as ?", () => {
  const m = new MapLayer();
  m.visitRoom({ uuid: "r1", name: "deep roads" }, [{ direction: "down", target_id: "r2" }]);
  expect(flat(m.render(40, 20))).toContain("?");
});
