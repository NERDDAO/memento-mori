import { type ProseLayer } from "../layers/prose-layer";
import { type MapLayer } from "../layers/map-layer";
import { apiPost } from "./api";
import type { KgReadPort } from "./kg-read-port";

export type StartResp = {
  player_id: string;
  epigraph: string;
  location_id: string;
  location_name: string;
  description: string;
  exits: { direction: string; target_id: string }[];
};

export type ActResp = {
  status: string;
  narration?: string | null;
  won?: boolean;
  reason?: string | null;
};

export type LookResp = {
  ok: boolean;
  fired_cxns: string[];
  response_text: string;
};

export interface Gateway {
  start(playerName?: string): Promise<StartResp>;
  act(playerId: string, text: string): Promise<ActResp>;
  look(playerId: string): Promise<LookResp>;
}

export const httpGateway: Gateway = {
  start(playerName?: string): Promise<StartResp> {
    // The opening arc is identity-light: the gateway uses player_name only as
    // the seed entity's display name and mints its own player uuid. Phase 1 has
    // no onboarding layer yet, so we send a default identity; a name-entry layer
    // replaces this later. wallet_address must be a 42-char string to pass the
    // gateway's StartOpeningRequest validation.
    return apiPost<StartResp>("/api/opening/start", {
      player_name: playerName || "wanderer",
      wallet_address: "0x0000000000000000000000000000000000000000",
    });
  },
  act(playerId: string, text: string): Promise<ActResp> {
    return apiPost<ActResp>("/api/opening/act", { player_id: playerId, text });
  },
  look(playerId: string): Promise<LookResp> {
    return apiPost<LookResp>("/api/opening/look", { player_id: playerId });
  },
};

export class OpeningLoop {
  private playerId = "";
  private currentRoom = "";
  private ended = false;

  constructor(
    private readonly prose: ProseLayer,
    private readonly map: MapLayer,
    private readonly gateway: Gateway,
    private readonly kg: KgReadPort,
    private readonly onChips: (chips: string[]) => void,
    private readonly redraw: () => void,
  ) {}

  async start(): Promise<void> {
    const s = await this.gateway.start();

    this.prose.enqueue({ text: s.epigraph, kind: "epigraph" });
    this.prose.enqueue({ text: s.location_name, kind: "location" });
    this.prose.enqueue({ text: s.description, kind: "description" });

    this.map.visitRoom({ uuid: s.location_id, name: s.location_name }, s.exits);

    this.playerId = s.player_id;
    this.currentRoom = s.location_id;

    const things = await this.kg
      .getRoomContents(s.player_id, s.location_id)
      .catch(() => []);
    this.map.setContents(s.location_id, things);

    this.redraw();
  }

  async submit(text: string): Promise<void> {
    if (this.ended) return;

    const r = await this.gateway.act(this.playerId, text);

    if (r.status === "narrated" || r.status === "executed") {
      if (r.narration) {
        this.prose.enqueue({ text: r.narration, kind: "narration" });
      }
      const things = await this.kg
        .getRoomContents(this.playerId, this.currentRoom)
        .catch(() => []);
      this.map.setContents(this.currentRoom, things);
      if (r.won) {
        this.ended = true;
      }
    } else if (r.status === "clarify") {
      this.prose.enqueue({ text: "What do you mean?", kind: "prompt" });
      const exits = this.map.currentExits().map((e) => `go ${e.direction}`);
      const things = this.map.currentThings().map((t) => `take ${t.name}`);
      this.onChips([...exits, ...things]);
    }
    // any other status: just redraw (no crash)

    this.redraw();
  }
}
