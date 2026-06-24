import type { PanelResult } from "../canvas/types";
import type { Layer } from "../canvas/layer";
import { textRow, emptyRow } from "../panels/panel-utils";
import { theme } from "../renderer/theme";

export type Segment = {
  text: string;
  kind: "epigraph" | "location" | "description" | "narration" | "prompt";
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
    const prefix = this.fullStream.slice(0, this.revealed);
    // Trim trailing whitespace/newlines from the revealed prefix before wrapping
    // so that partial trailing \n\n separators don't produce phantom blank lines.
    const trimmed = prefix.trimEnd();
    const wrapped = trimmed === "" ? [] : wordWrap(trimmed, cols);
    // Keep only the last `rows` lines.
    const visible = wrapped.slice(-rows);
    // Pad the top with empty rows so result is exactly `rows` tall.
    const cells: ReturnType<typeof textRow>[] = [];
    const padCount = rows - visible.length;
    for (let i = 0; i < padCount; i++) {
      cells.push(emptyRow(cols));
    }
    for (const line of visible) {
      cells.push(textRow(line, theme.colors.primary, cols));
    }
    return { cells };
  }
}
