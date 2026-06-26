import { test, expect } from "bun:test";
import { computeOpeningRegions } from "./region-manager";
test("opening layout has prose, kgmap, input, status with sane bounds", () => {
  const r = computeOpeningRegions(80, 24);
  for (const name of ["prose", "kgmap", "input", "status"]) expect(r.has(name)).toBe(true);
  const prose = r.get("prose")!, map = r.get("kgmap")!;
  expect(prose.col).toBeLessThan(map.col);
  expect(prose.cols).toBeGreaterThan(map.cols * 0.8);
  expect(prose.row).toBeGreaterThanOrEqual(1);
});
