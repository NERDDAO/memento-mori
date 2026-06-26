import { test, expect, mock } from "bun:test";

// Setup window mock for session.ts import
(globalThis as any).window = {
  location: { protocol: "http:", hostname: "localhost", port: "8081" }
};

// Now import after window is available
const apiModule = await import("./api");
const sessionModule = await import("./session");
const apiPost = apiModule.apiPost;
const apiGet = apiModule.apiGet;
const GATEWAY_URL = sessionModule.GATEWAY_URL;

function fakeFetch(status: number, json: unknown) {
  return mock(async (_url: string, _init?: any) =>
    ({ ok: status < 400, status, json: async () => json, text: async () => JSON.stringify(json) }) as any);
}

test("apiPost hits GATEWAY_URL + path with JSON body and returns parsed json", async () => {
  const f = fakeFetch(200, { player_id: "p1" }); (globalThis as any).fetch = f;
  const out = await apiPost<{ player_id: string }>("/api/opening/start", { x: 1 });
  expect(f.mock.calls[0][0]).toBe(`${GATEWAY_URL}/api/opening/start`);
  expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ x: 1 });
  expect(out.player_id).toBe("p1");
});
test("apiGet returns parsed json", async () => {
  (globalThis as any).fetch = fakeFetch(200, { things: [] });
  expect(await apiGet<{ things: unknown[] }>("/api/x")).toEqual({ things: [] });
});
test("non-ok throws with status", async () => {
  (globalThis as any).fetch = fakeFetch(404, { detail: "nope" });
  await expect(apiGet("/api/missing")).rejects.toThrow(/404/);
});
