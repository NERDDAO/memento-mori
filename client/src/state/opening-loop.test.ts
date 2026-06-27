import { test, expect, mock } from "bun:test";

// Setup window mock BEFORE any imports that touch session.ts → api.ts
(globalThis as any).window = {
  location: { protocol: "http:", hostname: "localhost", port: "8081" },
};

// Dynamic imports after window mock is in place
const { ProseLayer } = await import("../layers/prose-layer");
const { MapLayer } = await import("../layers/map-layer");
const { OpeningLoop, httpGateway } = await import("./opening-loop");

function fakeFetch(json: unknown) {
  return mock(
    async (_url: string, _init?: any) =>
      ({
        ok: true,
        status: 200,
        json: async () => json,
        text: async () => JSON.stringify(json),
      }) as any,
  );
}

const startResp = {
  player_id: "p1",
  epigraph: "E",
  location_id: "r1",
  location_name: "deep roads",
  description: "D",
  exits: [{ direction: "down", target_id: "r2" }],
};
function harness(act: any) {
  const prose = new ProseLayer(),
    map = new MapLayer();
  const chips: string[][] = [];
  let actCalls = 0;
  const gateway = {
    start: async () => startResp,
    act: async () => {
      actCalls++;
      return act;
    },
  };
  const kg = {
    getRoomContents: async () => [{ uuid: "e1", name: "an iron blade" }],
  };
  return {
    prose,
    map,
    chips,
    actCalls: () => actCalls,
    loop: new OpeningLoop(
      prose,
      map,
      gateway as any,
      kg as any,
      (c) => chips.push(c),
      () => {},
    ),
  };
}
test("start seeds prose + map + contents", async () => {
  const h = harness({});
  await h.loop.start();
  expect(h.map.currentExits()).toEqual([{ direction: "down", targetId: "r2" }]);
  expect(h.map.currentThings().map((t) => t.name)).toContain("an iron blade");
});
test("clarify produces chips from exits + things", async () => {
  const h = harness({ status: "clarify", reason: "no_match" });
  await h.loop.start();
  await h.loop.submit("flarble");
  const last = h.chips.at(-1)!;
  expect(last).toContain("go down");
  expect(last).toContain("take an iron blade");
});
test("won ends the loop; a later submit is a no-op (no second act call)", async () => {
  const h = harness({ status: "executed", won: true, narration: "you ascend" });
  await h.loop.start();
  await h.loop.submit("go on");
  expect(h.actCalls()).toBe(1);
  await h.loop.submit("again"); // post-win submit must be ignored
  expect(h.actCalls()).toBe(1); // gateway.act not called again
});

test("httpGateway.look POSTs /api/opening/look with the player id", async () => {
  const f = fakeFetch({ ok: true, fired_cxns: [], response_text: "" });
  (globalThis as any).fetch = f;
  await httpGateway.look("p1");
  const [url, init] = f.mock.calls[0];
  expect(url).toContain("/api/opening/look");
  expect(JSON.parse(init.body)).toEqual({ player_id: "p1" });
});

test("httpGateway.start sends the given player name", async () => {
  const f = fakeFetch({
    player_id: "p2",
    epigraph: "",
    location_id: "r1",
    location_name: "",
    description: "",
    exits: [],
  });
  (globalThis as any).fetch = f;
  await httpGateway.start("Aria");
  const [, init] = f.mock.calls[0];
  expect(JSON.parse(init.body).player_name).toBe("Aria");
});

test("httpGateway.start defaults the name to wanderer", async () => {
  const f = fakeFetch({
    player_id: "p3",
    epigraph: "",
    location_id: "r1",
    location_name: "",
    description: "",
    exits: [],
  });
  (globalThis as any).fetch = f;
  await httpGateway.start();
  const [, init] = f.mock.calls[0];
  expect(JSON.parse(init.body).player_name).toBe("wanderer");
});
