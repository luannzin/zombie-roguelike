/**
 * HUD minimap: cached tile bitmap + live player dots.
 *
 * Colours and floor variation come from `theme/palette`, the same source the
 * main renderer uses, so the two views can never drift apart.
 *
 * Visibility is NOT managed here — the React HUD decides whether to mount this
 * canvas. This class only owns pixels.
 */

import { WALL, type TileMap } from '../game/world';
import { createSurface, get2d } from '../lib/canvas';
import { floorColor, palette } from '../theme/palette';

const MAX_SIDE = 160;
const DOT_R = 2.5;
/** Enemies read as a smaller swarm so players stay the thing you look for. */
const ENEMY_DOT_R = 1.6;
const LOCAL_RING_R = 4;

export interface MinimapPlayer {
  id: string;
  x: number;
  y: number;
  color: string;
  alive: boolean;
  kind?: 'player' | 'enemy';
}

export class Minimap {
  private readonly ctx: CanvasRenderingContext2D;
  private world: TileMap | null = null;
  private cache: HTMLCanvasElement | null = null;

  constructor(private readonly canvas: HTMLCanvasElement) {
    this.ctx = get2d(canvas, 'minimap');
  }

  setWorld(world: TileMap | null): void {
    this.world = world;
    this.cache = null;
    if (!world) {
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      return;
    }
    this.cache = buildTileCache(world);
    this.fitCanvas(world);
    this.paint([]);
  }

  draw(players: MinimapPlayer[], localId: string): void {
    if (!this.world || !this.cache) return;
    this.paint(players, localId);
  }

  /** Backing store is 1px per tile, scaled up to at most MAX_SIDE on screen. */
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

  private paint(players: MinimapPlayer[], localId = ''): void {
    const { world, cache, ctx } = this;
    if (!world || !cache) return;
    const { width, height } = this.canvas;

    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, width, height);
    ctx.drawImage(cache, 0, 0, width, height);

    const sx = width / world.pixelWidth;
    const sy = height / world.pixelHeight;

    for (const player of players) {
      const px = player.x * sx;
      const py = player.y * sy;

      ctx.globalAlpha = player.alive ? 1 : 0.35;

      if (player.kind === 'enemy') {
        ctx.beginPath();
        ctx.arc(px, py, ENEMY_DOT_R, 0, Math.PI * 2);
        ctx.fillStyle = player.color;
        ctx.fill();
        continue;
      }

      if (player.id === localId) {
        ctx.beginPath();
        ctx.arc(px, py, LOCAL_RING_R, 0, Math.PI * 2);
        ctx.strokeStyle = palette().minimap.localRing;
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

/** One pixel per tile; scaling to the display size happens at draw time. */
function buildTileCache(world: TileMap): HTMLCanvasElement {
  const { canvas, ctx } = createSurface(world.width, world.height, 'minimap/cache');
  const tiles = palette().tiles;

  for (let ty = 0; ty < world.height; ty++) {
    for (let tx = 0; tx < world.width; tx++) {
      if (world.tiles[ty][tx] === WALL) {
        // Cheap top-edge hint so walls read the same way as the main view.
        const exposed = ty === 0 || world.tiles[ty - 1][tx] !== WALL;
        ctx.fillStyle = exposed ? tiles.wallTop : tiles.wallBody;
      } else {
        ctx.fillStyle = floorColor(tx, ty);
      }
      ctx.fillRect(tx, ty, 1, 1);
    }
  }
  return canvas;
}
