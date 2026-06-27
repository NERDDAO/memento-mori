// src/renderer/theme.ts
var theme = {
  colors: {
    primary: "#c8c8d0",
    dim: "#6a6a78",
    npc: "#d4a574",
    damage: "#e05050",
    heal: "#50c878",
    system: "#5a5a70",
    location: "#7aa2d4",
    accent: "#8b5cf6",
    bg: "#0a0a0f"
  },
  fonts: {
    narrative: "'Georgia', 'Times New Roman', serif",
    ui: "system-ui, -apple-system, sans-serif",
    mono: "'Fira Code', 'Cascadia Code', monospace"
  },
  sizes: {
    narrativeText: 16,
    uiText: 13,
    lineHeight: 1.7
  }
};

// src/renderer/canvas-text.ts
var ATTR_BOLD = 1;
var ATTR_ITALIC = 2;
var ATTR_UNDERLINE = 4;
var MONO_FONT = "13px monospace";
function fontForAttrs(baseFont, attrs) {
  if (!attrs)
    return baseFont;
  const sizeMatch = baseFont.match(/(\d+px\s+.+)$/);
  const sizeAndFamily = sizeMatch ? sizeMatch[1] : baseFont;
  const parts = [];
  if (attrs & ATTR_ITALIC)
    parts.push("italic");
  if (attrs & ATTR_BOLD)
    parts.push("bold");
  parts.push(sizeAndFamily);
  return parts.join(" ");
}
function measureChar(ctx, font) {
  ctx.font = font;
  const metrics = ctx.measureText("M");
  const width = metrics.width;
  const ascent = metrics.actualBoundingBoxAscent ?? 0;
  const descent = metrics.actualBoundingBoxDescent ?? 0;
  const measured = ascent + descent;
  const height = measured > 0 ? Math.ceil(measured * 1.38) : 18;
  return { width, height };
}
function fillCell(ctx, col, row, cell, charSize) {
  const px = col * charSize.width;
  const py = row * charSize.height;
  if (cell.bg) {
    ctx.fillStyle = cell.bg;
    ctx.fillRect(px, py, charSize.width, charSize.height);
  }
  if (cell.char && cell.char !== " ") {
    ctx.font = fontForAttrs(MONO_FONT, cell.attrs);
    ctx.fillStyle = cell.fg;
    ctx.textBaseline = "top";
    ctx.textAlign = "left";
    const fontSize = parseInt(ctx.font.replace(/^[^\d]*/, "")) || 13;
    const yOffset = (charSize.height - fontSize) * 0.35;
    ctx.fillText(cell.char, px, py + yOffset);
  }
  if (cell.attrs && cell.attrs & ATTR_UNDERLINE) {
    ctx.strokeStyle = cell.fg;
    ctx.lineWidth = 1;
    const underY = py + charSize.height - 2;
    ctx.beginPath();
    ctx.moveTo(px, underY);
    ctx.lineTo(px + charSize.width, underY);
    ctx.stroke();
  }
}

// src/canvas/region-manager.ts
var PRESENT_COLS = 20;
var SIDEBAR_COLS = 32;
function computeRegions(totalCols, totalRows) {
  const regions = new Map;
  const innerCols = totalCols - 2;
  const presentCols = Math.min(PRESENT_COLS, Math.floor(innerCols * 0.2));
  const sidebarCols = Math.min(SIDEBAR_COLS, Math.floor(innerCols * 0.25));
  const viewportCols = innerCols - presentCols - sidebarCols - 2;
  const colPresent = 1;
  const colVDiv0 = colPresent + presentCols;
  const colViewport = colVDiv0 + 1;
  const colVDiv1 = colViewport + viewportCols;
  const colSidebar = colVDiv1 + 1;
  const contentZoneRows = Math.max(totalRows - 9, 2);
  const topZoneRows = Math.max(Math.floor(contentZoneRows * 2 / 3), 3);
  const bottomZoneRows = Math.max(contentZoneRows - topZoneRows, 1);
  const rowHeader = 1;
  const rowHDiv0 = 2;
  const rowTopStart = 3;
  const rowHDiv1 = rowTopStart + topZoneRows;
  const rowBotStart = rowHDiv1 + 1;
  const rowHDiv2 = rowBotStart + bottomZoneRows;
  const rowInput = rowHDiv2 + 1;
  const rowHDiv3 = rowInput + 1;
  const rowStatus = rowHDiv3 + 1;
  const sidebarContentRows = topZoneRows - 2;
  const charRows = Math.max(Math.floor(sidebarContentRows * 2 / 7), 1);
  const questRows = Math.max(Math.floor(sidebarContentRows * 2 / 7), 1);
  const inventoryRows = Math.max(sidebarContentRows - charRows - questRows, 1);
  const rowSDiv0 = rowTopStart + charRows;
  const rowSDiv1 = rowSDiv0 + 1 + inventoryRows;
  function add(r) {
    regions.set(r.name, r);
  }
  add({
    name: "header",
    col: colPresent,
    row: rowHeader,
    cols: innerCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "input",
    col: colPresent,
    row: rowInput,
    cols: innerCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "status",
    col: colPresent,
    row: rowStatus,
    cols: innerCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "present",
    col: colPresent,
    row: rowTopStart,
    cols: presentCols,
    rows: topZoneRows,
    type: "grid",
    scrollOffset: 0
  });
  const CARDS_COLS = 52;
  const cardsCols = Math.min(CARDS_COLS, Math.floor(viewportCols * 0.55));
  const mapCols = viewportCols - cardsCols - 1;
  const colCards = colViewport + mapCols + 1;
  const colMapVDiv = colViewport + mapCols;
  add({
    name: "map",
    col: colViewport,
    row: rowTopStart,
    cols: mapCols,
    rows: topZoneRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "cards",
    col: colCards,
    row: rowTopStart,
    cols: cardsCols,
    rows: topZoneRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "_vDivMap",
    col: colMapVDiv,
    row: rowTopStart,
    cols: 1,
    rows: topZoneRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "character",
    col: colSidebar,
    row: rowTopStart,
    cols: sidebarCols,
    rows: charRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "inventory",
    col: colSidebar,
    row: rowSDiv0 + 1,
    cols: sidebarCols,
    rows: inventoryRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "quests",
    col: colSidebar,
    row: rowSDiv1 + 1,
    cols: sidebarCols,
    rows: questRows,
    type: "grid",
    scrollOffset: 0
  });
  const VIEWER_COLS = 28;
  const viewerCols = Math.min(VIEWER_COLS, Math.floor((presentCols + 1 + viewportCols) / 2));
  const narrativeCols = presentCols + 1 + viewportCols - viewerCols - 1;
  const colViewer = colPresent + narrativeCols + 1;
  const colBotVDiv = colPresent + narrativeCols;
  add({
    name: "narrative",
    col: colPresent,
    row: rowBotStart,
    cols: narrativeCols,
    rows: bottomZoneRows,
    type: "pixel",
    scrollOffset: 0
  });
  add({
    name: "viewer",
    col: colViewer,
    row: rowBotStart,
    cols: viewerCols,
    rows: bottomZoneRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "events",
    col: colSidebar,
    row: rowBotStart,
    cols: sidebarCols,
    rows: bottomZoneRows,
    type: "pixel",
    scrollOffset: 0
  });
  add({
    name: "_vDiv2",
    col: colBotVDiv,
    row: rowBotStart,
    cols: 1,
    rows: bottomZoneRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "_hDiv0",
    col: colPresent,
    row: rowHDiv0,
    cols: innerCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "_hDiv1",
    col: colPresent,
    row: rowHDiv1,
    cols: innerCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "_hDiv2",
    col: colPresent,
    row: rowHDiv2,
    cols: innerCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "_hDiv3",
    col: colPresent,
    row: rowHDiv3,
    cols: innerCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "_vDiv0",
    col: colVDiv0,
    row: rowTopStart,
    cols: 1,
    rows: topZoneRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "_vDiv1",
    col: colVDiv1,
    row: rowTopStart,
    cols: 1,
    rows: topZoneRows + 1 + bottomZoneRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "_sDiv0",
    col: colSidebar,
    row: rowSDiv0,
    cols: sidebarCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "_sDiv1",
    col: colSidebar,
    row: rowSDiv1,
    cols: sidebarCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  return regions;
}
function computeOpeningRegions(totalCols, totalRows) {
  const regions = new Map;
  function add(r) {
    regions.set(r.name, r);
  }
  const innerCols = totalCols - 2;
  const proseCols = Math.max(Math.floor(innerCols * 0.6), 10);
  const kgmapCols = Math.max(innerCols - proseCols - 1, 5);
  const colProse = 1;
  const colVDiv = colProse + proseCols;
  const colKgmap = colVDiv + 1;
  const rowInput = totalRows - 3;
  const rowStatus = totalRows - 2;
  const rowBodyStart = 1;
  const bodyRows = rowInput - rowBodyStart;
  add({
    name: "prose",
    col: colProse,
    row: rowBodyStart,
    cols: proseCols,
    rows: bodyRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "_vDivOpening",
    col: colVDiv,
    row: rowBodyStart,
    cols: 1,
    rows: bodyRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "kgmap",
    col: colKgmap,
    row: rowBodyStart,
    cols: kgmapCols,
    rows: bodyRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "input",
    col: colProse,
    row: rowInput,
    cols: innerCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "status",
    col: colProse,
    row: rowStatus,
    cols: innerCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  return regions;
}

// src/canvas/border-renderer.ts
var D_TL = "╔";
var D_TR = "╗";
var D_BL = "╚";
var D_BR = "╝";
var D_H = "═";
var D_V = "║";
var D_ML = "╠";
var D_MR = "╣";
var S_H = "─";
var S_V = "│";
var S_ML = "├";
var M_SH_DV_R = "╡";
var M_SV_DH_T = "╥";
var M_SV_DH_B = "╨";
function setCell(grid, row, col, char, fg) {
  if (row < 0 || col < 0 || row >= grid.length || col >= (grid[0]?.length ?? 0))
    return;
  grid[row][col] = { char, fg };
}
function hLine(grid, row, colStart, colEnd, char, fg) {
  for (let c = colStart;c <= colEnd; c++)
    setCell(grid, row, c, char, fg);
}
function vLine(grid, col, rowStart, rowEnd, char, fg) {
  for (let r = rowStart;r <= rowEnd; r++)
    setCell(grid, r, col, char, fg);
}
function drawBorders(grid, regions, totalCols, totalRows) {
  const fg = theme.colors.dim;
  const hDiv0 = regions.get("_hDiv0");
  const hDiv1 = regions.get("_hDiv1");
  const hDiv2 = regions.get("_hDiv2");
  const hDiv3 = regions.get("_hDiv3");
  const vDiv0 = regions.get("_vDiv0");
  const vDiv1 = regions.get("_vDiv1");
  const sDiv0 = regions.get("_sDiv0");
  const sDiv1 = regions.get("_sDiv1");
  const vDiv2 = regions.get("_vDiv2");
  const vDivMap = regions.get("_vDivMap");
  if (!hDiv0 || !hDiv1 || !hDiv2 || !hDiv3 || !vDiv0 || !vDiv1 || !sDiv0 || !sDiv1) {
    console.warn("[border-renderer] Missing divider metadata regions — skipping border draw");
    return;
  }
  const vd0 = vDiv0;
  const vd1 = vDiv1;
  const lastCol = totalCols - 1;
  const lastRow = totalRows - 1;
  const innerColStart = 1;
  const innerColEnd = lastCol - 1;
  setCell(grid, 0, 0, D_TL, fg);
  setCell(grid, 0, lastCol, D_TR, fg);
  setCell(grid, lastRow, 0, D_BL, fg);
  setCell(grid, lastRow, lastCol, D_BR, fg);
  hLine(grid, 0, 1, lastCol - 1, D_H, fg);
  hLine(grid, lastRow, 1, lastCol - 1, D_H, fg);
  vLine(grid, 0, 1, lastRow - 1, D_V, fg);
  vLine(grid, lastCol, 1, lastRow - 1, D_V, fg);
  function drawHDiv(row) {
    setCell(grid, row, 0, D_ML, fg);
    setCell(grid, row, lastCol, D_MR, fg);
    hLine(grid, row, innerColStart, innerColEnd, D_H, fg);
    if (row >= vd0.row && row < vd0.row + vd0.rows) {
      setCell(grid, row, vd0.col, "╪", fg);
    }
    if (row >= vd1.row && row < vd1.row + vd1.rows) {
      setCell(grid, row, vd1.col, "╪", fg);
    }
    if (vDiv2 && row >= vDiv2.row && row < vDiv2.row + vDiv2.rows) {
      setCell(grid, row, vDiv2.col, "╪", fg);
    }
    if (vDivMap && row >= vDivMap.row && row < vDivMap.row + vDivMap.rows) {
      setCell(grid, row, vDivMap.col, "╪", fg);
    }
  }
  drawHDiv(hDiv0.row);
  drawHDiv(hDiv1.row);
  drawHDiv(hDiv2.row);
  drawHDiv(hDiv3.row);
  setCell(grid, hDiv2.row, vDiv0.col, "╧", fg);
  setCell(grid, hDiv2.row, vDiv1.col, "╪", fg);
  vLine(grid, vDiv0.col, vDiv0.row, vDiv0.row + vDiv0.rows - 1, S_V, fg);
  vLine(grid, vDiv1.col, vDiv1.row, vDiv1.row + vDiv1.rows - 1, S_V, fg);
  const vDivCols = [vDiv0.col, vDiv1.col];
  const hDivRows = [hDiv0.row, hDiv1.row, hDiv3.row];
  for (const vc of vDivCols) {
    for (const hr of hDivRows) {
      const vr = vc === vDiv0.col ? vDiv0 : vDiv1;
      if (hr >= vr.row && hr < vr.row + vr.rows) {
        setCell(grid, hr, vc, "╪", fg);
      }
    }
  }
  const sCol = sDiv0.col;
  const sEnd = sDiv0.col + sDiv0.cols - 1;
  setCell(grid, sDiv0.row, vDiv1.col, S_ML, fg);
  hLine(grid, sDiv0.row, sCol, sEnd, S_H, fg);
  setCell(grid, sDiv0.row, lastCol, M_SH_DV_R, fg);
  setCell(grid, sDiv1.row, vDiv1.col, S_ML, fg);
  hLine(grid, sDiv1.row, sCol, sEnd, S_H, fg);
  setCell(grid, sDiv1.row, lastCol, M_SH_DV_R, fg);
  setCell(grid, hDiv3.row, vDiv1.col, "╧", fg);
  if (vDivMap) {
    vLine(grid, vDivMap.col, vDivMap.row, vDivMap.row + vDivMap.rows - 1, S_V, fg);
    setCell(grid, hDiv0.row, vDivMap.col, M_SV_DH_T, fg);
    setCell(grid, hDiv1.row, vDivMap.col, "╧", fg);
  }
  if (vDiv2) {
    vLine(grid, vDiv2.col, vDiv2.row, vDiv2.row + vDiv2.rows - 1, S_V, fg);
    setCell(grid, hDiv1.row, vDiv2.col, M_SV_DH_T, fg);
    setCell(grid, hDiv2.row, vDiv2.col, M_SV_DH_B, fg);
  }
}

// src/canvas/hit-registry.ts
class HitRegistry {
  entries = [];
  clear(z) {
    if (z === undefined) {
      this.entries = [];
    } else {
      this.entries = this.entries.filter((e) => e.z !== z);
    }
  }
  clearRegion(regionName, z) {
    this.entries = this.entries.filter((e) => !(e.region === regionName && e.z === z));
  }
  registerPanel(regionName, region, localRegions, z = 0) {
    for (const local of localRegions) {
      this.entries.push({
        region: regionName,
        col: region.col + local.col,
        row: region.row + local.row,
        width: local.width,
        height: local.height,
        z,
        data: local.data
      });
    }
  }
  register(entry) {
    this.entries.push(entry);
  }
  hitTest(col, row) {
    let best = null;
    for (const e of this.entries) {
      if (col >= e.col && col < e.col + e.width && row >= e.row && row < e.row + e.height) {
        if (best === null || e.z > best.z) {
          best = e;
        }
      }
    }
    if (best === null)
      return null;
    return { region: best.region, data: best.data };
  }
  hasModalLayer() {
    return this.entries.some((e) => e.z > 0);
  }
}

// src/canvas/modal-manager.ts
class ModalManager {
  stack = [];
  uc;
  constructor(uc) {
    this.uc = uc;
  }
  open(name, widthPct, heightPct) {
    this.close(name);
    const totalCols = this.uc.totalCols;
    const totalRows = this.uc.totalRows;
    const innerCols = Math.floor((totalCols - 2) * widthPct);
    const innerRows = Math.floor((totalRows - 2) * heightPct);
    const cols = innerCols + 2;
    const rows = innerRows + 2;
    const col = Math.floor((totalCols - cols) / 2);
    const row = Math.floor((totalRows - rows) / 2);
    const z = this.stack.length + 1;
    const state = {
      name,
      region: { name: `modal_${name}`, col, row, cols, rows, type: "grid", scrollOffset: 0 },
      z,
      cells: [],
      hitRegions: [],
      scrollOffset: 0,
      totalContentRows: 0
    };
    this.stack.push(state);
    this.uc.markAllDirty();
    return state;
  }
  setContent(name, result) {
    const modal = this.stack.find((m) => m.name === name);
    if (!modal)
      return;
    modal.cells = result.cells;
    modal.hitRegions = result.hitRegions || [];
    modal.totalContentRows = result.cells.length;
    this.uc.hitRegistry.clear(modal.z);
    if (modal.hitRegions.length > 0) {
      const contentRegion = {
        ...modal.region,
        name: `modal_${name}_content`,
        col: modal.region.col + 1,
        row: modal.region.row + 1,
        cols: modal.region.cols - 2,
        rows: modal.region.rows - 2
      };
      this.uc.hitRegistry.registerPanel(`modal_${name}`, contentRegion, modal.hitRegions, modal.z);
    }
    this.uc.markAllDirty();
  }
  close(name) {
    const idx = this.stack.findIndex((m) => m.name === name);
    if (idx === -1)
      return;
    const modal = this.stack[idx];
    this.uc.hitRegistry.clear(modal.z);
    this.stack.splice(idx, 1);
    this.uc.markAllDirty();
  }
  closeTopmost() {
    if (this.stack.length === 0)
      return null;
    const top = this.stack.pop();
    this.uc.hitRegistry.clear(top.z);
    this.uc.markAllDirty();
    return top.name;
  }
  get active() {
    return this.stack.length > 0;
  }
  get topmost() {
    return this.stack[this.stack.length - 1] || null;
  }
  getStack() {
    return this.stack;
  }
  isOpen(name) {
    return this.stack.some((m) => m.name === name);
  }
  renderInto(grid, totalCols, totalRows) {
    for (const modal of this.stack) {
      const { region, cells, scrollOffset } = modal;
      for (let r = 0;r < totalRows; r++) {
        for (let c = 0;c < totalCols; c++) {
          if (r >= region.row && r < region.row + region.rows && c >= region.col && c < region.col + region.cols)
            continue;
          if (grid[r] && grid[r][c]) {
            grid[r][c] = { ...grid[r][c], fg: theme.colors.dim, bg: undefined };
          }
        }
      }
      const D = {
        H: "═",
        V: "║",
        TL: "╔",
        TR: "╗",
        BL: "╚",
        BR: "╝"
      };
      const borderFg = theme.colors.accent;
      const bg = theme.colors.bg;
      if (region.row < totalRows && region.col + region.cols <= totalCols) {
        grid[region.row][region.col] = { char: D.TL, fg: borderFg, bg };
        for (let c = 1;c < region.cols - 1; c++) {
          grid[region.row][region.col + c] = { char: D.H, fg: borderFg, bg };
        }
        grid[region.row][region.col + region.cols - 1] = { char: D.TR, fg: borderFg, bg };
      }
      const botRow = region.row + region.rows - 1;
      if (botRow < totalRows && region.col + region.cols <= totalCols) {
        grid[botRow][region.col] = { char: D.BL, fg: borderFg, bg };
        for (let c = 1;c < region.cols - 1; c++) {
          grid[botRow][region.col + c] = { char: D.H, fg: borderFg, bg };
        }
        grid[botRow][region.col + region.cols - 1] = { char: D.BR, fg: borderFg, bg };
      }
      for (let r = 1;r < region.rows - 1; r++) {
        const gr = region.row + r;
        if (gr >= totalRows)
          break;
        grid[gr][region.col] = { char: D.V, fg: borderFg, bg };
        grid[gr][region.col + region.cols - 1] = { char: D.V, fg: borderFg, bg };
        for (let c = 1;c < region.cols - 1; c++) {
          grid[gr][region.col + c] = { char: " ", fg: theme.colors.primary, bg };
        }
      }
      const contentCol = region.col + 1;
      const contentRow = region.row + 1;
      const contentCols = region.cols - 2;
      const contentRows = region.rows - 2;
      for (let r = 0;r < contentRows; r++) {
        const srcRow = r + scrollOffset;
        if (srcRow >= cells.length)
          break;
        const srcRowCells = cells[srcRow];
        if (!srcRowCells)
          continue;
        for (let c = 0;c < Math.min(srcRowCells.length, contentCols); c++) {
          const gr = contentRow + r;
          const gc = contentCol + c;
          if (gr < totalRows && gc < totalCols) {
            grid[gr][gc] = { ...srcRowCells[c], bg };
          }
        }
      }
    }
  }
  scroll(deltaRows) {
    const modal = this.topmost;
    if (!modal)
      return;
    const maxScroll = Math.max(0, modal.totalContentRows - (modal.region.rows - 2));
    modal.scrollOffset = Math.max(0, Math.min(modal.scrollOffset + deltaRows, maxScroll));
    this.uc.markAllDirty();
  }
}

// src/canvas/unified-canvas.ts
class UnifiedCanvas {
  canvas;
  regions;
  hitRegistry;
  modalManager;
  totalCols;
  totalRows;
  ctx;
  charSize;
  grid;
  borderGrid;
  dirtySet = new Set;
  allDirty = true;
  renderScheduled = false;
  clickHandlers = [];
  wheelHandlers = [];
  pixelRenderers = [];
  offscreenSlots = [];
  observer;
  computeRegionsFn;
  constructor(container, computeRegionsFn = computeRegions) {
    this.computeRegionsFn = computeRegionsFn;
    this.canvas = document.createElement("canvas");
    this.canvas.style.display = "block";
    this.canvas.style.width = "100%";
    this.canvas.style.height = "100%";
    container.appendChild(this.canvas);
    const ctx = this.canvas.getContext("2d");
    if (!ctx)
      throw new Error("UnifiedCanvas: failed to get 2d context");
    this.ctx = ctx;
    this.charSize = measureChar(this.ctx, MONO_FONT);
    this.totalCols = 1;
    this.totalRows = 1;
    this.grid = [[{ char: " ", fg: theme.colors.primary }]];
    this.borderGrid = [[{ char: " ", fg: theme.colors.primary }]];
    this.regions = new Map;
    this.hitRegistry = new HitRegistry;
    this.modalManager = new ModalManager(this);
    this.canvas.addEventListener("click", this._onClick.bind(this));
    this.canvas.addEventListener("mousemove", this._onMouseMove.bind(this));
    this.canvas.addEventListener("mouseleave", this._onMouseLeave.bind(this));
    this.canvas.addEventListener("wheel", this._onWheel.bind(this), { passive: false });
    this.observer = new ResizeObserver(() => this._resize());
    this.observer.observe(container);
    this._resize();
  }
  _resize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0)
      return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = Math.floor(rect.width * dpr);
    this.canvas.height = Math.floor(rect.height * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.charSize = measureChar(this.ctx, MONO_FONT);
    const { width: cw, height: ch } = this.charSize;
    this.totalCols = Math.max(Math.floor(rect.width / cw), 10);
    this.totalRows = Math.max(Math.floor(rect.height / ch), 5);
    this.grid = this._allocGrid(this.totalRows, this.totalCols);
    this.borderGrid = this._allocGrid(this.totalRows, this.totalCols);
    this.regions = this.computeRegionsFn(this.totalCols, this.totalRows);
    drawBorders(this.borderGrid, this.regions, this.totalCols, this.totalRows);
    this.markAllDirty();
  }
  _allocGrid(rows, cols) {
    const empty = { char: " ", fg: theme.colors.primary };
    return Array.from({ length: rows }, () => Array.from({ length: cols }, () => ({ ...empty })));
  }
  setRegionContent(name, result) {
    const region = this.regions.get(name);
    if (!region)
      return;
    const { cells, hitRegions } = result;
    for (let r = 0;r < cells.length && r < region.rows; r++) {
      const row = cells[r];
      for (let c = 0;c < row.length && c < region.cols; c++) {
        const gr = region.row + r;
        const gc = region.col + c;
        if (gr < this.totalRows && gc < this.totalCols) {
          this.grid[gr][gc] = row[c];
        }
      }
    }
    this.hitRegistry.clearRegion(name, 0);
    if (hitRegions && hitRegions.length > 0) {
      this.hitRegistry.registerPanel(name, region, hitRegions, 0);
    }
    this.markDirty(name);
  }
  setOffscreen(regionName, offscreenCanvas) {
    const existing = this.offscreenSlots.findIndex((s) => s.regionName === regionName);
    if (existing >= 0) {
      this.offscreenSlots[existing] = { regionName, canvas: offscreenCanvas };
    } else {
      this.offscreenSlots.push({ regionName, canvas: offscreenCanvas });
    }
    this.markDirty(regionName);
  }
  setPixelRenderer(regionName, renderer) {
    const existing = this.pixelRenderers.findIndex((p) => p.regionName === regionName);
    if (existing >= 0) {
      this.pixelRenderers[existing] = { regionName, renderer };
    } else {
      this.pixelRenderers.push({ regionName, renderer });
    }
    this.markDirty(regionName);
  }
  onClick(handler) {
    this.clickHandlers.push(handler);
  }
  onWheel(handler) {
    this.wheelHandlers.push(handler);
  }
  markDirty(name) {
    this.dirtySet.add(name);
    this._scheduleRender();
  }
  markAllDirty() {
    this.allDirty = true;
    this._scheduleRender();
  }
  _scheduleRender() {
    if (this.renderScheduled)
      return;
    this.renderScheduled = true;
    requestAnimationFrame(() => {
      this.renderScheduled = false;
      this._paint();
    });
  }
  getRegion(name) {
    return this.regions.get(name);
  }
  getCharSize() {
    return this.charSize;
  }
  _paint() {
    const ctx = this.ctx;
    const cs = this.charSize;
    if (this.allDirty) {
      ctx.fillStyle = theme.colors.bg;
      ctx.fillRect(0, 0, this.totalCols * cs.width, this.totalRows * cs.height);
      for (let r = 0;r < this.totalRows; r++) {
        for (let c = 0;c < this.totalCols; c++) {
          const cell = this.borderGrid[r][c];
          if (cell.char !== " ")
            fillCell(ctx, c, r, cell, cs);
        }
      }
      for (const region of this.regions.values()) {
        if (region.name.startsWith("_") || region.type !== "grid")
          continue;
        this._paintGridRegion(region);
      }
      for (const entry of this.pixelRenderers) {
        const region = this.regions.get(entry.regionName);
        if (!region)
          continue;
        this._paintPixelRegion(region, entry.renderer);
      }
      for (const slot of this.offscreenSlots) {
        const region = this.regions.get(slot.regionName);
        if (!region)
          continue;
        this._blitOffscreen(region, slot.canvas);
      }
      if (this.modalManager.active) {
        this.modalManager.renderInto(this.grid, this.totalCols, this.totalRows);
        ctx.fillStyle = theme.colors.bg;
        ctx.fillRect(0, 0, this.totalCols * cs.width, this.totalRows * cs.height);
        for (let r = 0;r < this.totalRows; r++) {
          for (let c = 0;c < this.totalCols; c++) {
            const bc = this.borderGrid[r][c];
            if (bc.char !== " ") {
              fillCell(ctx, c, r, { ...bc, fg: theme.colors.dim }, cs);
            }
          }
        }
        for (let r = 0;r < this.totalRows; r++) {
          for (let c = 0;c < this.totalCols; c++) {
            const cell = this.grid[r][c];
            if (cell.char !== " " || cell.bg) {
              fillCell(ctx, c, r, cell, cs);
            }
          }
        }
        const modalRegions = this.modalManager.getStack().map((m) => m.region);
        for (const entry of this.pixelRenderers) {
          const region = this.regions.get(entry.regionName);
          if (region) {
            ctx.save();
            ctx.beginPath();
            const rpx = region.col * cs.width;
            const rpy = region.row * cs.height;
            const rpw = region.cols * cs.width;
            const rph = region.rows * cs.height;
            ctx.rect(rpx, rpy, rpw, rph);
            for (const mr of modalRegions) {
              ctx.rect(mr.col * cs.width, mr.row * cs.height, mr.cols * cs.width, mr.rows * cs.height);
            }
            ctx.clip("evenodd");
            entry.renderer(ctx, region, cs);
            ctx.restore();
          }
        }
        for (const slot of this.offscreenSlots) {
          const region = this.regions.get(slot.regionName);
          if (region) {
            ctx.save();
            ctx.beginPath();
            const rpx = region.col * cs.width;
            const rpy = region.row * cs.height;
            const rpw = region.cols * cs.width;
            const rph = region.rows * cs.height;
            ctx.rect(rpx, rpy, rpw, rph);
            for (const mr of modalRegions) {
              ctx.rect(mr.col * cs.width, mr.row * cs.height, mr.cols * cs.width, mr.rows * cs.height);
            }
            ctx.clip("evenodd");
            this._blitOffscreen(region, slot.canvas);
            ctx.restore();
          }
        }
      }
      this.allDirty = false;
      this.dirtySet.clear();
    } else if (this.modalManager.active) {
      this.allDirty = true;
      this.dirtySet.clear();
      this._paint();
      return;
    } else {
      for (const name of this.dirtySet) {
        const region = this.regions.get(name);
        if (!region || region.name.startsWith("_"))
          continue;
        const px = region.col * cs.width;
        const py = region.row * cs.height;
        const pw = region.cols * cs.width;
        const ph = region.rows * cs.height;
        ctx.fillStyle = theme.colors.bg;
        ctx.fillRect(px, py, pw, ph);
        for (let r = region.row;r < region.row + region.rows && r < this.totalRows; r++) {
          for (let c = region.col;c < region.col + region.cols && c < this.totalCols; c++) {
            const cell = this.borderGrid[r][c];
            if (cell.char !== " ")
              fillCell(ctx, c, r, cell, cs);
          }
        }
        if (region.type === "grid") {
          this._paintGridRegion(region);
        }
        const pixEntry = this.pixelRenderers.find((p) => p.regionName === name);
        if (pixEntry)
          this._paintPixelRegion(region, pixEntry.renderer);
        const offEntry = this.offscreenSlots.find((s) => s.regionName === name);
        if (offEntry)
          this._blitOffscreen(region, offEntry.canvas);
      }
      this.dirtySet.clear();
    }
  }
  _paintGridRegion(region) {
    const ctx = this.ctx;
    const cs = this.charSize;
    for (let r = 0;r < region.rows; r++) {
      for (let c = 0;c < region.cols; c++) {
        const gr = region.row + r;
        const gc = region.col + c;
        if (gr >= this.totalRows || gc >= this.totalCols)
          continue;
        const cell = this.grid[gr][gc];
        if (cell.char !== " " || cell.bg) {
          fillCell(ctx, gc, gr, cell, cs);
        }
      }
    }
  }
  _paintPixelRegion(region, renderer) {
    const ctx = this.ctx;
    const cs = this.charSize;
    const px = region.col * cs.width;
    const py = region.row * cs.height;
    const pw = region.cols * cs.width;
    const ph = region.rows * cs.height;
    ctx.save();
    ctx.beginPath();
    ctx.rect(px, py, pw, ph);
    ctx.clip();
    renderer(ctx, region, cs);
    ctx.restore();
  }
  _blitOffscreen(region, offscreen) {
    const ctx = this.ctx;
    const cs = this.charSize;
    const px = region.col * cs.width;
    const py = region.row * cs.height;
    const pw = region.cols * cs.width;
    const ph = region.rows * cs.height;
    ctx.drawImage(offscreen, px, py, pw, ph);
  }
  _pixelToGrid(clientX, clientY) {
    const rect = this.canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    return {
      col: Math.floor(x / this.charSize.width),
      row: Math.floor(y / this.charSize.height)
    };
  }
  _pointToRegion(col, row) {
    for (const region of this.regions.values()) {
      if (region.name.startsWith("_"))
        continue;
      if (col >= region.col && col < region.col + region.cols && row >= region.row && row < region.row + region.rows) {
        return region.name;
      }
    }
    return null;
  }
  _onClick(e) {
    const { col, row } = this._pixelToGrid(e.clientX, e.clientY);
    const hit = this.hitRegistry.hitTest(col, row);
    if (hit) {
      for (const h of this.clickHandlers)
        h(hit.region, hit.data);
    }
  }
  _onMouseMove(e) {
    const { col, row } = this._pixelToGrid(e.clientX, e.clientY);
    const hit = this.hitRegistry.hitTest(col, row);
    this.canvas.style.cursor = hit ? "pointer" : "default";
  }
  _onMouseLeave(_e) {
    this.canvas.style.cursor = "default";
  }
  _onWheel(e) {
    e.preventDefault();
    if (this.modalManager.active) {
      const delta = e.deltaY > 0 ? 3 : -3;
      this.modalManager.scroll(delta);
      return;
    }
    const { col, row } = this._pixelToGrid(e.clientX, e.clientY);
    const regionName = this._pointToRegion(col, row);
    if (regionName) {
      for (const h of this.wheelHandlers)
        h(regionName, e.deltaY);
    }
  }
}

// src/panels/panel-utils.ts
function textRow(text, fg, cols, attrs) {
  const row = [];
  for (let i = 0;i < cols; i++) {
    row.push({ char: i < text.length ? text[i] : " ", fg, attrs });
  }
  return row;
}
function emptyRow(cols) {
  return Array.from({ length: cols }, () => ({ char: " ", fg: theme.colors.primary }));
}

// src/layers/prose-layer.ts
function wordWrap(text, cols) {
  const lines = [];
  const paragraphs = text.split(`
`);
  for (const para of paragraphs) {
    if (para === "") {
      lines.push("");
      continue;
    }
    const words = para.split(" ");
    let current = "";
    for (const word of words) {
      if (word === "") {
        if (current.length > 0)
          current += " ";
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
    if (current !== "")
      lines.push(current);
  }
  return lines;
}

class ProseLayer {
  id = "prose";
  regionName = "prose";
  segments = [];
  revealed = 0;
  get fullStream() {
    return this.segments.map((s) => s.text + `

`).join("");
  }
  enqueue(seg) {
    this.segments.push(seg);
  }
  skip() {
    this.revealed = this.fullStream.length;
  }
  tick() {
    const full = this.fullStream;
    if (this.revealed < full.length) {
      this.revealed++;
    }
    return this.revealed < full.length;
  }
  render(cols, rows) {
    const lineColors = [];
    let consumed = 0;
    for (const seg of this.segments) {
      const segText = seg.text + `

`;
      const visibleChars = Math.max(0, Math.min(segText.length, this.revealed - consumed));
      consumed += segText.length;
      if (visibleChars === 0)
        continue;
      const shown = segText.slice(0, visibleChars).trimEnd();
      if (shown === "")
        continue;
      const color = seg.kind === "catch" ? theme.colors.accent : seg.kind === "npc-name" || seg.kind === "npc-dialogue" ? theme.colors.npc : theme.colors.primary;
      for (const line of wordWrap(shown, cols)) {
        lineColors.push({ line, color });
      }
    }
    const visible = lineColors.slice(-rows);
    const cells = [];
    const padCount = rows - visible.length;
    for (let i = 0;i < padCount; i++)
      cells.push(emptyRow(cols));
    for (const { line, color } of visible)
      cells.push(textRow(line, color, cols));
    return { cells };
  }
}

// src/map/colors.ts
var TILE_COLORS = {
  "#": ["#3a3a48", "#1a1a22"],
  ".": ["#2a2a35", "#0a0a0f"],
  "+": ["#50c8c8", "#0a0a0f"],
  T: ["#8b6914", "#0a0a0f"],
  B: ["#8b6914", "#0a0a0f"],
  "~": ["#3060c0", "#0a0a0f"],
  ",": ["#2a5a2a", "#0a0a0f"],
  ":": ["#555550", "#0a0a0f"],
  "=": ["#666660", "#0a0a0f"],
  "^": ["#888880", "#0a0a0f"],
  " ": ["#0a0a0f", "#0a0a0f"]
};
var DEFAULT_COLORS = ["#555555", "#0a0a0f"];
function tileColors(ch) {
  return TILE_COLORS[ch] || DEFAULT_COLORS;
}
var ENTITY_COLORS = {
  player: "#ffd700",
  npc: "#d4a574",
  item: "#a335ee",
  exit: "#50c8c8"
};

// src/map/renderer.ts
var TILE_W = 14;
var TILE_H = 18;
var FONT = "15px monospace";

class MapRenderer {
  canvas;
  ctx;
  dpr;
  constructor(container) {
    this.dpr = Math.min(devicePixelRatio, 2);
    this.canvas = document.createElement("canvas");
    this.canvas.style.display = "block";
    this.canvas.style.background = "#0a0a0f";
    this.ctx = this.canvas.getContext("2d");
    container.appendChild(this.canvas);
  }
  get element() {
    return this.canvas;
  }
  render(map, playerX, playerY) {
    const mapW = map.width * TILE_W;
    const mapH = map.height * TILE_H;
    this.canvas.width = mapW * this.dpr;
    this.canvas.height = mapH * this.dpr;
    this.canvas.style.width = `${mapW}px`;
    this.canvas.style.height = `${mapH}px`;
    const ctx = this.ctx;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.fillStyle = "#0a0a0f";
    ctx.fillRect(0, 0, mapW, mapH);
    ctx.font = FONT;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (let y = 0;y < map.height; y++) {
      for (let x = 0;x < map.width; x++) {
        const ch = map.tiles[y * map.width + x] || " ";
        const [fg, bg] = tileColors(ch);
        ctx.fillStyle = bg;
        ctx.fillRect(x * TILE_W, y * TILE_H, TILE_W, TILE_H);
        if (ch !== " ") {
          ctx.fillStyle = fg;
          ctx.fillText(ch, x * TILE_W + TILE_W / 2, y * TILE_H + TILE_H / 2);
        }
      }
    }
    for (const exit of map.exits) {
      this.drawEntity(exit.x, exit.y, exit.ch || "+", ENTITY_COLORS.exit);
    }
    for (const item of map.items) {
      this.drawEntity(item.x, item.y, item.ch, ENTITY_COLORS.item);
    }
    for (const npc of map.npcs) {
      this.drawEntity(npc.x, npc.y, npc.ch, ENTITY_COLORS.npc);
    }
    this.drawEntity(playerX, playerY, "@", ENTITY_COLORS.player);
  }
  drawEntity(x, y, ch, color) {
    const ctx = this.ctx;
    ctx.fillStyle = "#0a0a0f";
    ctx.fillRect(x * TILE_W, y * TILE_H, TILE_W, TILE_H);
    ctx.fillStyle = color;
    ctx.font = FONT;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(ch, x * TILE_W + TILE_W / 2, y * TILE_H + TILE_H / 2);
  }
  gridToScreen(gridX, gridY) {
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: rect.left + gridX * TILE_W + TILE_W / 2,
      y: rect.top + gridY * TILE_H
    };
  }
}

// src/map/movement.ts
class PlayerController {
  x;
  y;
  map;
  onInteract;
  onProximity;
  lastProximity = "";
  constructor(map, onInteract, onProximity) {
    this.x = map.spawn?.x ?? Math.floor(map.width / 2);
    this.y = map.spawn?.y ?? Math.floor(map.height / 2);
    this.map = map;
    this.onInteract = onInteract;
    this.onProximity = onProximity;
  }
  move(dx, dy) {
    const nx = this.x + dx;
    const ny = this.y + dy;
    if (!this.isWalkable(nx, ny))
      return false;
    this.x = nx;
    this.y = ny;
    this.checkProximity();
    return true;
  }
  interact() {
    const dirs = [[0, 0], [0, -1], [0, 1], [-1, 0], [1, 0]];
    for (const [dx, dy] of dirs) {
      const tx = this.x + dx;
      const ty = this.y + dy;
      const exit = this.map.exits.find((e) => e.x === tx && e.y === ty);
      if (exit) {
        this.onInteract("exit", exit);
        this.syncPosition();
        return;
      }
      const npc = this.map.npcs.find((n) => n.x === tx && n.y === ty);
      if (npc) {
        this.onInteract("npc", npc);
        this.syncPosition();
        return;
      }
      const item = this.map.items.find((i) => i.x === tx && i.y === ty);
      if (item) {
        this.onInteract("item", item);
        this.syncPosition();
        return;
      }
    }
  }
  checkProximity() {
    const dirs = [[0, -1], [0, 1], [-1, 0], [1, 0]];
    for (const [dx, dy] of dirs) {
      const tx = this.x + dx;
      const ty = this.y + dy;
      const npc = this.map.npcs.find((n) => n.x === tx && n.y === ty);
      if (npc && this.lastProximity !== npc.id) {
        this.lastProximity = npc.id;
        this.onProximity("npc", npc);
        return;
      }
      const item = this.map.items.find((i) => i.x === tx && i.y === ty);
      if (item && this.lastProximity !== item.id) {
        this.lastProximity = item.id;
        this.onProximity("item", item);
        return;
      }
      const exit = this.map.exits.find((e) => e.x === tx && e.y === ty);
      if (exit) {
        const exitId = `exit-${exit.direction}`;
        if (this.lastProximity !== exitId) {
          this.lastProximity = exitId;
          this.onProximity("exit", exit);
          return;
        }
      }
    }
    if (this.lastProximity !== "") {
      this.lastProximity = "";
      this.onProximity(null, null);
    }
  }
  isWalkable(x, y) {
    if (x < 0 || x >= this.map.width || y < 0 || y >= this.map.height)
      return false;
    const ch = this.map.tiles[y * this.map.width + x];
    return ch !== "#" && ch !== undefined && ch !== " ";
  }
  syncPosition() {
    const pid = window.__mmPlayerId;
    if (!pid)
      return;
    fetch("/api/position/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_id: pid, x: this.x, y: this.y })
    }).catch(() => {});
  }
  loadMap(map) {
    this.map = map;
    this.x = map.spawn?.x ?? Math.floor(map.width / 2);
    this.y = map.spawn?.y ?? Math.floor(map.height / 2);
    this.lastProximity = "";
  }
}
var MOVE_KEYS = {
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
  w: [0, -1],
  s: [0, 1],
  a: [-1, 0],
  d: [1, 0],
  k: [0, -1],
  j: [0, 1],
  h: [-1, 0],
  l: [1, 0]
};
function setupMapInput(controller, renderer, map, onMapUpdate) {
  const handler = (e) => {
    if (e.target?.tagName === "INPUT")
      return;
    const delta = MOVE_KEYS[e.key];
    if (delta) {
      e.preventDefault();
      if (controller.move(delta[0], delta[1]) && map.current) {
        renderer.render(map.current, controller.x, controller.y);
        onMapUpdate?.();
      }
    } else if (e.key === "Enter" || e.key === " ") {
      if (e.target?.tagName === "INPUT")
        return;
      e.preventDefault();
      controller.interact();
    }
  };
  document.addEventListener("keydown", handler);
  return () => document.removeEventListener("keydown", handler);
}

// src/state/room-map-builder.ts
var SIDE_BY_DIR = {
  north: "top",
  up: "top",
  n: "top",
  u: "top",
  south: "bottom",
  down: "bottom",
  s: "bottom",
  d: "bottom",
  east: "right",
  e: "right",
  west: "left",
  w: "left"
};
function hashStr(s) {
  let h = 2166136261;
  for (let i = 0;i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}
function buildRoomMap(room, exits, things, width = 28, height = 16) {
  const W = Math.max(12, Math.min(Math.round(width), 48));
  const H = Math.max(8, Math.min(Math.round(height), 24));
  const idx = (x, y) => y * W + x;
  const tiles = new Array(W * H);
  for (let y = 0;y < H; y++) {
    for (let x = 0;x < W; x++) {
      const edge = x === 0 || y === 0 || x === W - 1 || y === H - 1;
      tiles[idx(x, y)] = edge ? "#" : ".";
    }
  }
  const FALLBACK = ["bottom", "top", "right", "left"];
  const usedSides = new Set;
  const exitCells = [];
  for (const ex of exits) {
    let side = SIDE_BY_DIR[(ex.direction || "").toLowerCase()];
    if (side === undefined || usedSides.has(side)) {
      side = FALLBACK.find((s) => !usedSides.has(s)) ?? "bottom";
    }
    usedSides.add(side);
    let ex_x;
    let ex_y;
    if (side === "top") {
      ex_x = W / 2 | 0;
      ex_y = 0;
    } else if (side === "bottom") {
      ex_x = W / 2 | 0;
      ex_y = H - 1;
    } else if (side === "left") {
      ex_x = 0;
      ex_y = H / 2 | 0;
    } else {
      ex_x = W - 1;
      ex_y = H / 2 | 0;
    }
    tiles[idx(ex_x, ex_y)] = ".";
    exitCells.push({ x: ex_x, y: ex_y, ch: "+", direction: ex.direction, target: ex.target_id });
  }
  const spawn = { x: W / 2 | 0, y: H / 2 | 0 };
  tiles[idx(spawn.x, spawn.y)] = ".";
  const occupied = new Set([idx(spawn.x, spawn.y), ...exitCells.map((e) => idx(e.x, e.y))]);
  const npcs = [];
  const iw = W - 2;
  const ih = H - 2;
  for (const t of things) {
    const base = hashStr(t.uuid);
    for (let attempt = 0;attempt < iw * ih; attempt++) {
      const k = base + attempt * 2654435761 >>> 0;
      const x = 1 + k % iw;
      const y = 1 + Math.floor(k / iw) % ih;
      const cell = idx(x, y);
      if (!occupied.has(cell) && tiles[cell] === ".") {
        occupied.add(cell);
        const glyph = (t.name.trim()[0] || "?").toUpperCase();
        npcs.push({ x, y, ch: glyph, name: t.name, id: t.uuid });
        break;
      }
    }
  }
  return { id: room.uuid, name: room.name, width: W, height: H, tiles, npcs, items: [], exits: exitCells, spawn };
}

// src/layers/room-viewport.ts
var ROOM_W = 28;
var ROOM_H = 16;

class RoomViewportAdapter {
  renderer;
  controller;
  mapRef;
  room = { uuid: "", name: "" };
  exits = [];
  things = [];
  onChange;
  constructor(onChange) {
    this.onChange = onChange;
    const holder = document.createElement("div");
    this.renderer = new MapRenderer(holder);
    const empty = buildRoomMap(this.room, [], [], ROOM_W, ROOM_H);
    this.mapRef = { current: empty };
    this.controller = new PlayerController(empty, () => {}, () => {});
  }
  get canvas() {
    return this.renderer.element;
  }
  attachInput() {
    return setupMapInput(this.controller, this.renderer, this.mapRef, this.onChange);
  }
  visitRoom(room, exits) {
    this.room = room;
    this.exits = exits;
    this.things = [];
    this.rebuild();
  }
  setContents(roomUuid, things) {
    if (roomUuid !== this.room.uuid)
      return;
    this.things = things;
    this.rebuild();
  }
  currentExits() {
    return this.exits.map((e) => ({ direction: e.direction, targetId: e.target_id }));
  }
  currentThings() {
    return this.things;
  }
  rebuild() {
    const map = buildRoomMap(this.room, this.exits, this.things, ROOM_W, ROOM_H);
    this.mapRef.current = map;
    this.controller.loadMap(map);
    this.render();
  }
  render() {
    if (!this.mapRef.current)
      return;
    this.renderer.render(this.mapRef.current, this.controller.x, this.controller.y);
    this.onChange();
  }
}

// src/state/session.ts
var GATEWAY_PORT = window.location.port || "8081";
var GATEWAY_URL = `${window.location.protocol}//${window.location.hostname}:${GATEWAY_PORT}`;
var WS_URL = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.hostname}:${GATEWAY_PORT}/ws`;

// src/state/api.ts
async function handle(res) {
  if (!res.ok)
    throw new Error(`API ${res.status}: ${await res.text()}`);
  return await res.json();
}
async function apiPost(path, body) {
  return handle(await fetch(`${GATEWAY_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  }));
}
async function apiGet(path) {
  return handle(await fetch(`${GATEWAY_URL}${path}`));
}

// src/state/opening-loop.ts
var httpGateway = {
  start(playerName) {
    return apiPost("/api/opening/start", {
      player_name: playerName || "wanderer",
      wallet_address: "0x0000000000000000000000000000000000000000"
    });
  },
  act(playerId, text) {
    return apiPost("/api/opening/act", { player_id: playerId, text });
  },
  look(playerId) {
    return apiPost("/api/opening/look", { player_id: playerId });
  }
};

// src/state/kg-read-port.ts
var httpKgReadPort = {
  async getRoomContents(playerId, roomUuid) {
    try {
      const resp = await apiGet(`/api/opening/room/${encodeURIComponent(roomUuid)}/contents?player_id=${encodeURIComponent(playerId)}`);
      return resp.things;
    } catch {
      return [];
    }
  }
};

// src/state/round-state.ts
var listeners = [];
function onRoundStateChange(listener) {
  listeners.push(listener);
  return () => {
    const idx = listeners.indexOf(listener);
    if (idx >= 0)
      listeners.splice(idx, 1);
  };
}

// src/ui/mention-dropdown.ts
function createMentionDropdown() {
  const el = document.createElement("div");
  el.className = "mention-dropdown";
  el.style.display = "none";
  document.body.appendChild(el);
  let items = [];
  let filtered = [];
  let selectedIndex = 0;
  let selectCallback = null;
  function render() {
    el.innerHTML = filtered.map((s, i) => {
      const icon = s.type === "npc" ? "◆" : "@";
      const cls = i === selectedIndex ? "mention-item selected" : "mention-item";
      const typeCls = s.type === "npc" ? "mention-npc" : "mention-player";
      return `<div class="${cls} ${typeCls}" data-index="${i}"><span class="mention-icon">${icon}</span>${s.name}</div>`;
    }).join("");
    el.querySelectorAll(".mention-item").forEach((row) => {
      row.addEventListener("click", () => {
        const idx = parseInt(row.dataset.index || "0", 10);
        if (filtered[idx] && selectCallback)
          selectCallback(filtered[idx].name);
        dropdown.hide();
      });
    });
  }
  const dropdown = {
    el,
    onSelect: null,
    show(suggestions, anchor) {
      items = suggestions;
      filtered = [...items];
      selectedIndex = 0;
      selectCallback = this.onSelect;
      const rect = anchor.getBoundingClientRect();
      el.style.position = "fixed";
      el.style.bottom = `${window.innerHeight - rect.top + 4}px`;
      el.style.left = `${rect.left}px`;
      el.style.display = "";
      render();
    },
    hide() {
      el.style.display = "none";
      items = [];
      filtered = [];
    },
    isVisible() {
      return el.style.display !== "none";
    },
    filter(query) {
      const q = query.toLowerCase();
      filtered = q ? items.filter((s) => s.name.toLowerCase().startsWith(q)) : [...items];
      selectedIndex = 0;
      render();
      el.style.display = filtered.length > 0 ? "" : "none";
    },
    handleKey(e) {
      if (!this.isVisible())
        return false;
      if (e.key === "ArrowUp") {
        e.preventDefault();
        selectedIndex = Math.max(0, selectedIndex - 1);
        render();
        return true;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        selectedIndex = Math.min(filtered.length - 1, selectedIndex + 1);
        render();
        return true;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        if (filtered[selectedIndex] && selectCallback) {
          e.preventDefault();
          selectCallback(filtered[selectedIndex].name);
          this.hide();
          return true;
        }
      }
      if (e.key === "Escape") {
        this.hide();
        return true;
      }
      return false;
    }
  };
  return dropdown;
}

// src/panels/input.ts
function initInput(inputEl, onSubmit, getContext) {
  const history = [];
  let historyIndex = -1;
  let locked = false;
  const defaultPlaceholder = inputEl.placeholder || "What do you do?";
  function setLocked(isLocked) {
    locked = isLocked;
    inputEl.disabled = isLocked;
    inputEl.classList.toggle("input-locked", isLocked);
  }
  onRoundStateChange((rs) => {
    switch (rs.phase) {
      case "ready":
        setLocked(false);
        inputEl.placeholder = defaultPlaceholder;
        break;
      case "collecting": {
        setLocked(false);
        const timer = rs.secondsLeft != null ? `${rs.secondsLeft}s left to act...` : "Round open...";
        inputEl.placeholder = timer;
        break;
      }
      case "resolving":
        setLocked(true);
        inputEl.placeholder = "Resolving...";
        break;
      case "npc_response":
        setLocked(true);
        inputEl.placeholder = "NPCs responding...";
        break;
    }
  });
  const dropdown = createMentionDropdown();
  let mentionActive = false;
  let mentionStart = -1;
  function getMentionSuggestions() {
    if (!getContext)
      return [];
    const ctx = getContext();
    const suggestions = [];
    for (const npc of ctx.npcs) {
      const name = typeof npc === "string" ? npc : npc.name;
      suggestions.push({ name, type: "npc" });
    }
    for (const p of ctx.players) {
      const name = typeof p === "string" ? p : p.name;
      suggestions.push({ name, type: "player" });
    }
    return suggestions;
  }
  dropdown.onSelect = (name) => {
    const before = inputEl.value.slice(0, mentionStart);
    const after = inputEl.value.slice(inputEl.selectionStart || inputEl.value.length);
    inputEl.value = `${before}@${name} ${after}`;
    inputEl.focus();
    mentionActive = false;
    mentionStart = -1;
  };
  inputEl.addEventListener("keydown", (e) => {
    if (locked)
      return;
    if (mentionActive && dropdown.handleKey(e))
      return;
    if (e.key === "Enter") {
      if (mentionActive) {
        dropdown.hide();
        mentionActive = false;
      }
      const action = inputEl.value.trim();
      if (action) {
        history.unshift(action);
        historyIndex = -1;
        onSubmit(action);
        inputEl.value = "";
      }
    } else if (e.key === "ArrowUp" && !mentionActive) {
      e.preventDefault();
      if (historyIndex < history.length - 1) {
        historyIndex++;
        inputEl.value = history[historyIndex];
      }
    } else if (e.key === "ArrowDown" && !mentionActive) {
      e.preventDefault();
      if (historyIndex > 0) {
        historyIndex--;
        inputEl.value = history[historyIndex];
      } else {
        historyIndex = -1;
        inputEl.value = "";
      }
    } else if (e.key === "Escape" && mentionActive) {
      dropdown.hide();
      mentionActive = false;
    }
  });
  inputEl.addEventListener("input", () => {
    const val = inputEl.value;
    const cursor = inputEl.selectionStart || val.length;
    if (!mentionActive) {
      if (cursor > 0 && val[cursor - 1] === "@") {
        const charBefore = cursor > 1 ? val[cursor - 2] : " ";
        if (charBefore === " " || charBefore === undefined || cursor === 1) {
          mentionActive = true;
          mentionStart = cursor - 1;
          const suggestions = getMentionSuggestions();
          dropdown.show(suggestions, inputEl);
          dropdown.filter("");
        }
      }
    } else {
      const query = val.slice(mentionStart + 1, cursor);
      if (query.includes(" ") || cursor <= mentionStart) {
        dropdown.hide();
        mentionActive = false;
      } else {
        dropdown.filter(query);
      }
    }
  });
}

// src/state/opening-ws.ts
function routeOpeningMessage(msg, s) {
  switch (msg?.type) {
    case "tool_event":
      if (msg.tool === "mm_npc_response" && msg.npc) {
        s.prose.enqueue({
          kind: "npc-dialogue",
          text: msg.summary ?? "",
          speaker: msg.npc
        });
        s.redrawProse();
      }
      break;
    case "npc_joined": {
      if (!msg.npc_name)
        break;
      const things = s.viewport.currentThings();
      if (things.some((t) => t.uuid === msg.npc_id || t.name === msg.npc_name))
        break;
      s.viewport.setContents(s.roomUuid(), [
        ...things,
        { uuid: msg.npc_id ?? "", name: msg.npc_name }
      ]);
      break;
    }
    case "npc_left": {
      const things = s.viewport.currentThings();
      s.viewport.setContents(s.roomUuid(), things.filter((t) => t.uuid !== msg.npc_id && t.name !== msg.npc_name));
      break;
    }
    case "room_draw": {
      if (msg.kind !== "revealed")
        break;
      const entity = msg.entity;
      if (!entity || !entity.name)
        break;
      const things = s.viewport.currentThings();
      if (things.some((t) => t.uuid === entity.uuid || t.name === entity.name))
        break;
      s.viewport.setContents(s.roomUuid(), [
        ...things,
        { uuid: entity.uuid ?? "", name: entity.name }
      ]);
      break;
    }
    case "cxn_fired":
      s.prose.enqueue({
        kind: "catch",
        text: `◇ caught: ${msg.cxn ?? ""}`
      });
      s.redrawProse();
      break;
    default:
      break;
  }
}
function connectOpeningWs(playerId, onMessage) {
  const ws = new WebSocket(`${WS_URL}/${playerId}`);
  ws.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data));
    } catch {}
  };
  return ws;
}

// src/state/opening-intro.ts
var OPENING_EPIGRAPH = `Remember that you must die.
Enter, wanderer, if you dare.`;
function mountOpeningIntro(onName) {
  const overlay = document.getElementById("opening-intro");
  const epigraphEl = overlay?.querySelector(".opening-epigraph");
  const nameSection = overlay?.querySelector(".opening-name-section");
  const nameInput = overlay?.querySelector("#opening-name-input");
  const nameBtn = overlay?.querySelector("#opening-name-btn");
  if (!overlay || !epigraphEl || !nameSection || !nameInput || !nameBtn) {
    onName("wanderer");
    return;
  }
  epigraphEl.innerHTML = OPENING_EPIGRAPH.replace(/\n/g, "<br>");
  overlay.classList.remove("hidden");
  let called = false;
  function submit() {
    if (called)
      return;
    called = true;
    const raw = nameInput.value.trim();
    const name = (raw.length > 0 ? raw : "wanderer").slice(0, 30);
    overlay.classList.add("hidden");
    onName(name);
  }
  setTimeout(() => {
    nameSection.classList.remove("hidden");
    nameInput.focus();
  }, 2400);
  nameInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter")
      submit();
  });
  nameBtn.addEventListener("click", () => submit());
}

// src/boot/opening-shell.ts
document.addEventListener("DOMContentLoaded", () => {
  const tuiMain = document.getElementById("tui-main");
  const uc = new UnifiedCanvas(tuiMain, computeOpeningRegions);
  const prose = new ProseLayer;
  const viewport = new RoomViewportAdapter(() => {
    uc.setOffscreen("kgmap", viewport.canvas);
    uc.markDirty("kgmap");
  });
  function redrawProse() {
    const region = uc.getRegion("prose");
    if (region) {
      uc.setRegionContent("prose", prose.render(region.cols, region.rows));
      uc.markDirty("prose");
    }
  }
  let playerId = "";
  let currentRoom = "";
  let ended = false;
  async function refreshContents() {
    const things = await httpKgReadPort.getRoomContents(playerId, currentRoom);
    viewport.setContents(currentRoom, things);
  }
  async function start(playerName) {
    const s = await httpGateway.start(playerName);
    playerId = s.player_id;
    currentRoom = s.location_id;
    window.__mmPlayerId = playerId;
    prose.enqueue({ text: s.epigraph, kind: "epigraph" });
    prose.enqueue({ text: s.location_name, kind: "location" });
    prose.enqueue({ text: s.description, kind: "description" });
    redrawProse();
    viewport.visitRoom({ uuid: s.location_id, name: s.location_name }, s.exits);
    await refreshContents();
    const surfaces = {
      prose,
      redrawProse,
      viewport,
      roomUuid: () => currentRoom
    };
    connectOpeningWs(playerId, (msg) => routeOpeningMessage(msg, surfaces));
    httpGateway.look(playerId).catch(() => {});
  }
  async function look() {
    prose.enqueue({ text: "You look around.", kind: "narration" });
    redrawProse();
    await refreshContents();
  }
  async function act(text) {
    let r;
    try {
      r = await httpGateway.act(playerId, text);
    } catch {
      return;
    }
    const line = r.narration ?? r.message ?? "";
    if (line)
      prose.enqueue({
        text: line,
        kind: r.status === "clarify" ? "prompt" : "narration"
      });
    if (r.won)
      ended = true;
    redrawProse();
    if (!ended)
      await refreshContents();
  }
  function submit(text) {
    if (ended)
      return;
    if (/^\s*look\b/i.test(text)) {
      look();
      return;
    }
    act(text);
  }
  const actionInput = document.getElementById("action-input");
  initInput(actionInput, submit);
  viewport.attachInput();
  document.addEventListener("keydown", () => {
    if (document.activeElement?.tagName === "INPUT")
      return;
    prose.skip();
    redrawProse();
  });
  setInterval(() => {
    if (prose.tick())
      redrawProse();
  }, 25);
  viewport.render();
  mountOpeningIntro((name) => {
    start(name);
  });
});
