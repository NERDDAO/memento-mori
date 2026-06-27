import { test, expect } from "bun:test";

// Mock window BEFORE any import that touches session.ts (which reads window.location at module load)
(globalThis as { window?: unknown }).window = {
  location: { protocol: "http:", hostname: "localhost", port: "8081" },
};

const { routeOpeningMessage } = await import("./opening-ws");

function makeSurfaces() {
  const enqueued: { kind: string; text: string; speaker?: string }[] = [];
  let things: { uuid: string; name: string }[] = [];
  let redraws = 0;
  return {
    surfaces: {
      prose: {
        enqueue: (s: { kind: string; text: string; speaker?: string }) =>
          enqueued.push(s),
      },
      redrawProse: () => {
        redraws++;
      },
      viewport: {
        setContents: (_room: string, t: { uuid: string; name: string }[]) => {
          things = t;
        },
        currentThings: () => things,
      },
      roomUuid: () => "507f1f77bcf86cd799439011",
    },
    get enqueued() {
      return enqueued;
    },
    get things() {
      return things;
    },
    get redraws() {
      return redraws;
    },
  };
}

test("mm_npc_response becomes an npc-dialogue prose segment", () => {
  const s = makeSurfaces();
  routeOpeningMessage(
    {
      type: "tool_event",
      tool: "mm_npc_response",
      npc: "a dying adventurer",
      summary: "You may pass.",
    },
    s.surfaces,
  );
  expect(s.enqueued).toEqual([
    {
      kind: "npc-dialogue",
      text: "You may pass.",
      speaker: "a dying adventurer",
    },
  ]);
  expect(s.redraws).toBe(1);
});

test("npc_joined adds the NPC as a room thing", () => {
  const s = makeSurfaces();
  routeOpeningMessage(
    {
      type: "npc_joined",
      npc_name: "a dying adventurer",
      npc_id: "opening-wanderer",
    },
    s.surfaces,
  );
  expect(s.things).toEqual([
    { uuid: "opening-wanderer", name: "a dying adventurer" },
  ]);
});

test("npc_left removes the NPC from room things", () => {
  const s = makeSurfaces();
  s.surfaces.viewport.setContents("507f1f77bcf86cd799439011", [
    { uuid: "opening-wanderer", name: "a dying adventurer" },
  ]);
  routeOpeningMessage(
    {
      type: "npc_left",
      npc_name: "a dying adventurer",
      npc_id: "opening-wanderer",
    },
    s.surfaces,
  );
  expect(s.things).toEqual([]);
});

test("a non-mm_npc_response tool_event is ignored", () => {
  const s = makeSurfaces();
  routeOpeningMessage(
    { type: "tool_event", tool: "mm_narrate", summary: "x" },
    s.surfaces,
  );
  expect(s.enqueued).toEqual([]);
});

test("cxn_fired becomes a catch prose segment", () => {
  const s = makeSurfaces();
  routeOpeningMessage(
    { type: "cxn_fired", cxn: "LOOK", construct_id: "mm.look.v1" },
    s.surfaces,
  );
  expect(s.enqueued).toEqual([{ kind: "catch", text: "◇ caught: LOOK" }]);
  expect(s.redraws).toBe(1);
});

test("presence and unknown messages are ignored", () => {
  const s = makeSurfaces();
  routeOpeningMessage({ type: "presence", players: [] }, s.surfaces);
  routeOpeningMessage({ type: "whatever" }, s.surfaces);
  expect(s.enqueued).toEqual([]);
  expect(s.things).toEqual([]);
});
