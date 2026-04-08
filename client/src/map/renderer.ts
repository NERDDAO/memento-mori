// src/map/renderer.ts

import type { RoomMap } from './types';
import { tileColors, ENTITY_COLORS } from './colors';

const TILE_W = 14;
const TILE_H = 18;
const FONT = '15px monospace';

export class MapRenderer {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private dpr: number;

  constructor(container: HTMLElement) {
    this.dpr = Math.min(devicePixelRatio, 2);
    this.canvas = document.createElement('canvas');
    this.canvas.style.display = 'block';
    this.canvas.style.background = '#0a0a0f';
    this.ctx = this.canvas.getContext('2d')!;
    container.appendChild(this.canvas);
  }

  get element(): HTMLCanvasElement {
    return this.canvas;
  }

  render(map: RoomMap, playerX: number, playerY: number): void {
    const mapW = map.width * TILE_W;
    const mapH = map.height * TILE_H;

    this.canvas.width = mapW * this.dpr;
    this.canvas.height = mapH * this.dpr;
    this.canvas.style.width = `${mapW}px`;
    this.canvas.style.height = `${mapH}px`;

    const ctx = this.ctx;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);

    // Clear entire canvas
    ctx.fillStyle = '#0a0a0f';
    ctx.fillRect(0, 0, mapW, mapH);

    // Draw map tiles
    ctx.font = FONT;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    for (let y = 0; y < map.height; y++) {
      for (let x = 0; x < map.width; x++) {
        const ch = map.tiles[y * map.width + x] || ' ';
        const [fg, bg] = tileColors(ch);
        ctx.fillStyle = bg;
        ctx.fillRect(x * TILE_W, y * TILE_H, TILE_W, TILE_H);
        if (ch !== ' ') {
          ctx.fillStyle = fg;
          ctx.fillText(ch, x * TILE_W + TILE_W / 2, y * TILE_H + TILE_H / 2);
        }
      }
    }

    // Draw exits
    for (const exit of map.exits) {
      this.drawEntity(exit.x, exit.y, exit.ch || '+', ENTITY_COLORS.exit);
    }

    // Draw items
    for (const item of map.items) {
      this.drawEntity(item.x, item.y, item.ch, ENTITY_COLORS.item);
    }

    // Draw NPCs
    for (const npc of map.npcs) {
      this.drawEntity(npc.x, npc.y, npc.ch, ENTITY_COLORS.npc);
    }

    // Draw player
    this.drawEntity(playerX, playerY, '@', ENTITY_COLORS.player);
  }

  private drawEntity(x: number, y: number, ch: string, color: string): void {
    const ctx = this.ctx;
    ctx.fillStyle = '#0a0a0f';
    ctx.fillRect(x * TILE_W, y * TILE_H, TILE_W, TILE_H);
    ctx.fillStyle = color;
    ctx.font = FONT;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(ch, x * TILE_W + TILE_W / 2, y * TILE_H + TILE_H / 2);
  }

  /** Convert grid coordinates to screen pixel position. */
  gridToScreen(gridX: number, gridY: number): { x: number; y: number } {
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: rect.left + gridX * TILE_W + TILE_W / 2,
      y: rect.top + gridY * TILE_H,
    };
  }
}
