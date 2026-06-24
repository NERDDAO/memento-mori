import type { PanelResult } from "../canvas/types";
import type { Layer } from "../canvas/layer";
import { textRow, emptyRow } from "../panels/panel-utils";
import { theme } from "../renderer/theme";

export type Thing = { uuid: string; name: string };

type Room = {
  uuid: string;
  name: string;
  things: Thing[];
  entered: boolean;
};

type Exit = { direction: string; target_id: string };

export class MapLayer implements Layer {
  readonly id = "kgmap";
  readonly regionName = "kgmap";

  private rooms = new Map<string, Room>();
  private exits: Exit[] = [];
  private current: string | null = null;

  visitRoom(room: { uuid: string; name: string }, exits: Exit[]): void {
    // Upsert the current room as entered (never downgrade an already-entered room).
    const existing = this.rooms.get(room.uuid);
    if (!existing || !existing.entered) {
      this.rooms.set(room.uuid, {
        uuid: room.uuid,
        name: room.name,
        things: existing?.things ?? [],
        entered: true,
      });
    }
    this.exits = exits;
    this.current = room.uuid;

    // Register unentered stub neighbors for unknown exit targets.
    for (const exit of exits) {
      if (!this.rooms.has(exit.target_id)) {
        this.rooms.set(exit.target_id, {
          uuid: exit.target_id,
          name: "?",
          things: [],
          entered: false,
        });
      }
    }
  }

  setContents(roomUuid: string, things: Thing[]): void {
    const room = this.rooms.get(roomUuid);
    if (room) {
      room.things = things;
    }
  }

  currentExits(): { direction: string; targetId: string }[] {
    return this.exits.map(e => ({ direction: e.direction, targetId: e.target_id }));
  }

  currentThings(): Thing[] {
    if (this.current === null) return [];
    return this.rooms.get(this.current)?.things ?? [];
  }

  render(cols: number, rows: number): PanelResult {
    const lines: string[] = [];

    if (this.current !== null) {
      const room = this.rooms.get(this.current);
      if (room) {
        // Top border
        const inner = cols - 2;
        lines.push("┌" + "─".repeat(inner) + "┐");

        // Room name line
        const nameLine = " " + room.name;
        lines.push("│" + nameLine.padEnd(inner).slice(0, inner) + "│");

        // Things
        for (const thing of room.things) {
          const thingLine = " * " + thing.name;
          lines.push("│" + thingLine.padEnd(inner).slice(0, inner) + "│");
        }

        // Exits line
        if (this.exits.length > 0) {
          const exitList = this.exits.map(e => e.direction).join(", ");
          const exitsLine = " exits: " + exitList;
          lines.push("│" + exitsLine.padEnd(inner).slice(0, inner) + "│");
        }

        // Bottom border
        lines.push("└" + "─".repeat(inner) + "┘");
      }
    }

    // Render other known rooms compactly below the current room box.
    for (const [uuid, room] of this.rooms) {
      if (uuid === this.current) continue;
      const marker = room.entered ? room.name : "?";
      lines.push("  " + marker);
    }

    // Build the cells array: exactly `rows` rows, each exactly `cols` wide.
    const cells: ReturnType<typeof emptyRow>[] = [];
    const visibleLines = lines.slice(0, rows);
    for (const line of visibleLines) {
      cells.push(textRow(line, theme.colors.primary, cols));
    }
    while (cells.length < rows) {
      cells.push(emptyRow(cols));
    }

    return { cells };
  }
}
