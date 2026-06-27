import { test, expect } from "bun:test";

// No real DOM is available under `bun test` (document is not defined).
// The happy path (getElementById, event dispatch, overlay hidden) requires a
// real DOM and is verified via `bun run build` + manual demo.
//
// We test only the degrade path: absent markup → onName("wanderer").

// Set up a minimal stub so mountOpeningIntro can call document.getElementById
// without throwing a ReferenceError, and have it return null (no overlay).
(globalThis as unknown as Record<string, unknown>).document = {
  getElementById: (_id: string) => null,
};

const { mountOpeningIntro, OPENING_EPIGRAPH } = await import("./opening-intro");

test("OPENING_EPIGRAPH is a non-empty string", () => {
  expect(typeof OPENING_EPIGRAPH).toBe("string");
  expect(OPENING_EPIGRAPH.length).toBeGreaterThan(0);
});

test("degrade path: absent #opening-intro → onName('wanderer') called synchronously", () => {
  const calls: string[] = [];
  mountOpeningIntro((name) => calls.push(name));
  expect(calls).toEqual(["wanderer"]);
});

test("degrade path: onName called exactly once", () => {
  let count = 0;
  mountOpeningIntro(() => count++);
  expect(count).toBe(1);
});
