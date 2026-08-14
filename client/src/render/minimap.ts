/**
 * HUD minimap: cached tile bitmap, fog overlay, live dots.
 *
 * Colours come from `theme/palette`, the same source the main renderer uses, so
 * the two views can never drift apart.
 *
 * The minimap obeys the same vision the world does. Ground nobody has walked
 * into is covered; ground the team has seen but cannot see now is dimmed to a
 * memory; and an enemy dot only appears where somebody currently has light on
 * it. Teammates are always shown — they are your team, you know where they are,
 * and the whole point of shared vision is that their light is your light.
 *
 * Visibility of the canvas itself is NOT managed here — the React HUD decides
 * whether to mount it. This class only owns pixels.
 */

import { FLOOR, TREE, VOID, type TileMap } from '../game/world';
import { createSurface, get2d } from '../lib/canvas';
import { floorColor, palette } from '../theme/palette';
import type { FovField } from './fov';

const MAX_SIDE = 160;
const DOT_R = 2.5;
/** Enemies read as a smaller swarm so players stay the thing you look for. */
const ENEMY_DOT_R = 1.6;
const LOCAL_RING_R = 4;
/** Light at or above this counts as "the team can see that". */
const SEEN_LIGHT = 0.12;

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
  private fog: HTMLCanvasElement | null = null;
  private fogCtx: CanvasRenderingContext2D | null = null;
  private fogData: ImageData | null = null;

  constructor(private readonly canvas: HTMLCanvasElement) {
    this.ctx = get2d(canvas, 'minimap');
  }

  setWorld(world: TileMap | null): void {
    this.world = world;
    this.cache = null;
    this.fog = null;
    this.fogCtx = null;
    this.fogData = null;
    if (!world) {
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      return;
    }
    this.cache = buildTileCache(world);
    const fog = createSurface(world.width, world.height, 'minimap/fog');
    this.fog = fog.canvas;
    this.fogCtx = fog.ctx;
    this.fogData = fog.ctx.createImageData(world.width, world.height);
    this.fitCanvas(world);
    this.paint([], '', null);
  }

  draw(players: MinimapPlayer[], localId: string, fov: FovField | null): void {
    if (!this.world || !this.cache) return;
    this.paint(players, localId, fov);
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

  private paint(players: MinimapPlayer[], localId: string, fov: FovField | null): void {
    const { world, cache, ctx } = this;
    if (!world || !cache) return;
    const { width, height } = this.canvas;

    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, width, height);
    ctx.drawImage(cache, 0, 0, width, height);
    if (fov) this.paintFog(fov, width, height);

    const sx = width / world.pixelWidth;
    const sy = height / world.pixelHeight;
    const ts = world.tileSize;

    for (const player of players) {
      // An enemy the team has no light on is not on the map. A teammate always
      // is, whether or not anyone can currently see them.
      if (player.kind === 'enemy' && fov) {
        const lit = fov.lightAt(Math.floor(player.x / ts), Math.floor(player.y / ts));
        if (lit < SEEN_LIGHT) continue;
      }

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

  /**
   * One pixel per tile, written straight into ImageData and blitted. A rect per
   * tile would be thousands of fill calls a frame for the same picture.
   */
  private paintFog(fov: FovField, width: number, height: number): void {
    const { fog, fogCtx, fogData } = this;
    if (!fog || !fogCtx || !fogData) return;

    const [r, g, b] = palette().night.shadow;
    const pixels = fogData.data;
    for (let i = 0; i < fov.light.length; i++) {
      const offset = i * 4;
      pixels[offset] = r;
      pixels[offset + 1] = g;
      pixels[offset + 2] = b;
      if (fov.light[i] >= SEEN_LIGHT) pixels[offset + 3] = 0;
      else pixels[offset + 3] = fov.explored[i] === 1 ? 158 : 235;
    }
    fogCtx.putImageData(fogData, 0, 0);
    this.ctx.drawImage(fog, 0, 0, width, height);
  }
}

/** One pixel per tile; scaling to the display size happens at draw time. */
function buildTileCache(world: TileMap): HTMLCanvasElement {
  const { canvas, ctx } = createSurface(world.width, world.height, 'minimap/cache');
  const tiles = palette().tiles;

  for (let ty = 0; ty < world.height; ty++) {
    for (let tx = 0; tx < world.width; tx++) {
      const tile = world.tiles[ty][tx];
      if (tile === VOID) {
        ctx.fillStyle = palette().surface;
      } else if (tile === FLOOR) {
        ctx.fillStyle = floorColor(tx, ty);
      } else {
        // Cheap top-edge hint so blockers read the same way as the main view.
        const exposed = ty === 0 || world.tiles[ty - 1][tx] === FLOOR;
        if (tile === TREE) ctx.fillStyle = exposed ? tiles.treeTop : tiles.tree;
        else ctx.fillStyle = exposed ? tiles.wallTop : tiles.wallBody;
      }
      ctx.fillRect(tx, ty, 1, 1);
    }
  }
  return canvas;
}
