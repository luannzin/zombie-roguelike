/**
 * Top-right HUD minimap: cached tile bitmap + live player dots.
 * Palette mirrors renderer.ts floor/wall colors.
 */

import { WALL, type TileMap } from '../game/world';

const FLOOR_COLORS = ['#23232c', '#262630', '#202029'];
const WALL_BODY = '#3a3a4e';
const WALL_TOP = '#565673';
const MAX_SIDE = 160;
const DOT_R = 2.5;
const LOCAL_RING_R = 4;

export interface MinimapPlayer {
  id: string;
  x: number;
  y: number;
  color: string;
  alive: boolean;
}

export class Minimap {
  private readonly ctx: CanvasRenderingContext2D;
  private world: TileMap | null = null;
  private cache: HTMLCanvasElement | null = null;

  constructor(private readonly canvas: HTMLCanvasElement) {
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('minimap: 2d context unavailable');
    this.ctx = ctx;
    this.ctx.imageSmoothingEnabled = false;
  }

  setWorld(world: TileMap | null): void {
    this.world = world;
    this.cache = null;
    if (!world) {
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      this.canvas.style.visibility = 'hidden';
      return;
    }
    this.canvas.style.visibility = 'visible';
    this.cache = this.buildCache(world);
    this.fitCanvas(world);
    this.paint([]);
  }

  draw(players: MinimapPlayer[], localId: string): void {
    if (!this.world || !this.cache) return;
    this.paint(players, localId);
  }

  private fitCanvas(world: TileMap): void {
    const scale = Math.min(MAX_SIDE / world.width, MAX_SIDE / world.height);
    const w = Math.max(1, Math.round(world.width * scale));
    const h = Math.max(1, Math.round(world.height * scale));
    this.canvas.width = w;
    this.canvas.height = h;
    this.canvas.style.width = `${w}px`;
    this.canvas.style.height = `${h}px`;
    this.ctx.imageSmoothingEnabled = false;
  }

  private buildCache(world: TileMap): HTMLCanvasElement {
    const canvas = document.createElement('canvas');
    canvas.width = world.width;
    canvas.height = world.height;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('minimap: cache 2d context unavailable');
    for (let ty = 0; ty < world.height; ty++) {
      for (let tx = 0; tx < world.width; tx++) {
        if (world.tiles[ty][tx] === WALL) {
          ctx.fillStyle = WALL_BODY;
          ctx.fillRect(tx, ty, 1, 1);
          // cheap top-edge hint so walls read like main view
          if (ty === 0 || world.tiles[ty - 1][tx] !== WALL) {
            ctx.fillStyle = WALL_TOP;
            ctx.fillRect(tx, ty, 1, 1);
          }
        } else {
          ctx.fillStyle = FLOOR_COLORS[(tx * 7 + ty * 13) % FLOOR_COLORS.length];
          ctx.fillRect(tx, ty, 1, 1);
        }
      }
    }
    return canvas;
  }

  private paint(players: MinimapPlayer[], localId = ''): void {
    const world = this.world;
    const cache = this.cache;
    if (!world || !cache) return;
    const ctx = this.ctx;
    const { width, height } = this.canvas;

    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, width, height);
    ctx.drawImage(cache, 0, 0, width, height);

    const sx = width / world.pixelWidth;
    const sy = height / world.pixelHeight;

    for (const player of players) {
      const px = player.x * sx;
      const py = player.y * sy;
      const isLocal = player.id === localId;

      ctx.globalAlpha = player.alive ? 1 : 0.35;

      if (isLocal) {
        ctx.beginPath();
        ctx.arc(px, py, LOCAL_RING_R, 0, Math.PI * 2);
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      ctx.beginPath();
      ctx.arc(px, py, DOT_R, 0, Math.PI * 2);
      ctx.fillStyle = player.color;
      ctx.fill();
    }

    ctx.globalAlpha = 1;
  }
}
