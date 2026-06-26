import type { PanelResult } from "../canvas/types";
import type { Layer } from "../canvas/layer";
import { textRow, emptyRow } from "../panels/panel-utils";
import { theme } from "../renderer/theme";

export type Segment = {
  text: string;
  kind: "epigraph" | "location" | "description" | "narration" | "prompt" | "npc-name" | "npc-dialogue";
  speaker?: string;
};

/** Word-wrap `text` into lines of at most `cols` characters.
 *  Explicit `\n` in the source always forces a new line.
 *  Words that exceed `cols` are broken at the column boundary. */
function wordWrap(text: string, cols: number): string[] {
  const lines: string[] = [];
  // Split on explicit newlines first.
  const paragraphs = text.split("\n");
  for (const para of paragraphs) {
    if (para === "") {
      lines.push("");
      continue;
    }
    // Wrap the paragraph at word boundaries.
    const words = para.split(" ");
    let current = "";
    for (const word of words) {
      if (word === "") {
        // Preserve multiple spaces as a single space in output.
        if (current.length > 0) current += " ";
        continue;
      }
      if (current === "") {
        current = word;
      } else if (current.length + 1 + word.length <= cols) {
        current += " " + word;
      } else {
        lines.push(current);
        current = word;
      }
    }
    if (current !== "") lines.push(current);
  }
  return lines;
}

export class ProseLayer implements Layer {
  readonly id = "prose";
  readonly regionName = "prose";

  private segments: Segment[] = [];
  private revealed = 0;

  private get fullStream(): string {
    return this.segments.map(s => s.text + "\n\n").join("");
  }

  enqueue(seg: Segment): void {
    this.segments.push(seg);
  }

  skip(): void {
    this.revealed = this.fullStream.length;
  }

  tick(): boolean {
    const full = this.fullStream;
    if (this.revealed < full.length) {
      this.revealed++;
    }
    return this.revealed < full.length;
  }

  render(cols: number, rows: number): PanelResult {
    // Build (line, color) pairs segment by segment, honoring the reveal cursor.
    const lineColors: { line: string; color: string }[] = [];
    let consumed = 0;
    for (const seg of this.segments) {
      const segText = seg.text + "\n\n";
      const visibleChars = Math.max(0, Math.min(segText.length, this.revealed - consumed));
      consumed += segText.length;
      if (visibleChars === 0) continue;
      const shown = segText.slice(0, visibleChars).trimEnd();
      if (shown === "") continue;
      const color =
        seg.kind === "npc-name" || seg.kind === "npc-dialogue"
          ? theme.colors.npc
          : theme.colors.primary;
      for (const line of wordWrap(shown, cols)) {
        lineColors.push({ line, color });
      }
    }
    const visible = lineColors.slice(-rows);
    const cells: ReturnType<typeof textRow>[] = [];
    const padCount = rows - visible.length;
    for (let i = 0; i < padCount; i++) cells.push(emptyRow(cols));
    for (const { line, color } of visible) cells.push(textRow(line, color, cols));
    return { cells };
  }
}
