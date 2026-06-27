// Opening-arc WebSocket adapter: translate persona server messages onto the
// typewriter render surfaces. The router is pure (testable without a socket);
// connectOpeningWs is a thin wrapper that opens the player's WS and forwards
// parsed messages to it. The opening UI stays fully playable if the WS never
// connects — personas are additive.
import { WS_URL } from "./session";

export interface OpeningSurfaces {
  prose: {
    enqueue: (seg: { kind: string; text: string; speaker?: string }) => void;
  };
  redrawProse: () => void;
  viewport: {
    setContents: (
      roomUuid: string,
      things: { uuid: string; name: string }[],
    ) => void;
    currentThings: () => { uuid: string; name: string }[];
  };
  roomUuid: () => string;
}

export function routeOpeningMessage(
  msg: Record<string, unknown>,
  s: OpeningSurfaces,
): void {
  switch (msg?.type) {
    case "tool_event":
      if (msg.tool === "mm_npc_response" && msg.npc) {
        s.prose.enqueue({
          kind: "npc-dialogue",
          text: (msg.summary as string) ?? "",
          speaker: msg.npc as string,
        });
        s.redrawProse();
      }
      break;
    case "npc_joined": {
      if (!msg.npc_name) break;
      const things = s.viewport.currentThings();
      if (things.some((t) => t.uuid === msg.npc_id || t.name === msg.npc_name))
        break;
      s.viewport.setContents(s.roomUuid(), [
        ...things,
        { uuid: (msg.npc_id as string) ?? "", name: msg.npc_name as string },
      ]);
      break;
    }
    case "npc_left": {
      const things = s.viewport.currentThings();
      s.viewport.setContents(
        s.roomUuid(),
        things.filter((t) => t.uuid !== msg.npc_id && t.name !== msg.npc_name),
      );
      break;
    }
    case "cxn_fired":
      s.prose.enqueue({
        kind: "catch",
        text: `◇ caught: ${(msg.cxn as string) ?? ""}`,
      });
      s.redrawProse();
      break;
    default:
      break; // presence / player_* / unknown → ignored
  }
}

export function connectOpeningWs(
  playerId: string,
  onMessage: (msg: Record<string, unknown>) => void,
): WebSocket {
  const ws = new WebSocket(`${WS_URL}/${playerId}`);
  ws.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data as string) as Record<string, unknown>);
    } catch {
      // ignore unparseable frames
    }
  };
  return ws;
}
