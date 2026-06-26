import { apiGet } from "./api";
import type { Thing } from "../layers/map-layer";

export type { Thing } from "../layers/map-layer";

export interface KgReadPort {
  getRoomContents(playerId: string, roomUuid: string): Promise<Thing[]>;
}

export const httpKgReadPort: KgReadPort = {
  async getRoomContents(playerId: string, roomUuid: string): Promise<Thing[]> {
    try {
      const resp = await apiGet<{ things: Thing[] }>(
        `/api/opening/room/${encodeURIComponent(roomUuid)}/contents?player_id=${encodeURIComponent(playerId)}`
      );
      return resp.things;
    } catch {
      return [];
    }
  },
};
