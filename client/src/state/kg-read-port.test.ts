import { test, expect, mock } from "bun:test";

// Setup window mock BEFORE any imports that touch session.ts
(globalThis as any).window = {
  location: { protocol: "http:", hostname: "localhost", port: "8081" }
};

// Dynamic imports after window mock is in place
const sessionModule = await import("./session");
const GATEWAY_URL = sessionModule.GATEWAY_URL;

function fakeFetch(status: number, json: unknown) {
  return mock(async (_url: string, _init?: any) =>
    ({ ok: status < 400, status, json: async () => json, text: async () => JSON.stringify(json) }) as any);
}

test("getRoomContents returns things array and hits correct URL", async () => {
  const fetchMock = fakeFetch(200, { things: [{ uuid: "e1", name: "an iron blade" }] });
  (globalThis as any).fetch = fetchMock;

  const mod = await import("./kg-read-port");
  const result = await mod.httpKgReadPort.getRoomContents("p1", "r1");

  expect(result).toEqual([{ uuid: "e1", name: "an iron blade" }]);
  expect(fetchMock.mock.calls[0][0]).toBe(
    `${GATEWAY_URL}/api/opening/room/r1/contents?player_id=p1`
  );
});

test("getRoomContents degrades to [] on 500 (does not throw)", async () => {
  (globalThis as any).fetch = fakeFetch(500, { detail: "server error" });

  const mod = await import("./kg-read-port");
  const result = await mod.httpKgReadPort.getRoomContents("p1", "r1");

  expect(result).toEqual([]);
});
