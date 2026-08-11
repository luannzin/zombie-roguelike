/**
 * Tile map layer.
 *
 * The map is pre-rendered once into an offscreen canvas, so a frame costs one
 * blit instead of ~1000 fillRect calls. Very large (procedural) maps fall back
 * to painting only the visible window each frame.
 */

import { WALL, type TileMap } from '../../game/world';
import { createSurface } from '../../lib/canvas';
import { floorColor, hasFloorSpeck, palette } from '../../theme/palette';
import type { Camera } from '../camera';

/** Above this a map is drawn per-tile instead of cached. */
const MAX_CACHED_MAP_PIXELS = 4096 * 4096;

export class TileLayer {
  private cache: HTMLCanvasElement | null = null;
  private cachedFor: TileMap | null = null;

  /** Caller must have applied the world-space transform. */
  draw(ctx: CanvasRenderingContext2D, world: TileMap, camera: Camera): void {
    if (this.cachedFor !== world) this.rebuild(world);

    if (this.cache) {
      const sx = Math.max(0, Math.floor(camera.renderX));
      const sy = Math.max(0, Math.floor(camera.renderY));
      const sw = Math.min(world.pixelWidth - sx, Math.ceil(camera.viewWidth) + 2);
      const sh = Math.min(world.pixelHeight - sy, Math.ceil(camera.viewHeight) + 2);
      if (sw > 0 && sh > 0) ctx.drawImage(this.cache, sx, sy, sw, sh, sx, sy, sw, sh);
      return;
    }

    const ts = world.tileSize;
    paintTiles(
      ctx,
      world,
      Math.max(0, Math.floor(camera.renderX / ts)),
      Math.max(0, Math.floor(camera.renderY / ts)),
      Math.min(world.width - 1, Math.ceil((camera.renderX + camera.viewWidth) / ts)),
      Math.min(world.height - 1, Math.ceil((camera.renderY + camera.viewHeight) / ts)),
    );
  }

  /** Drop the cached bitmap (map change, teardown). */
  reset(): void {
    this.cache = null;
    this.cachedFor = null;
  }

  private rebuild(world: TileMap): void {
    this.cachedFor = world;
    if (world.pixelWidth * world.pixelHeight > MAX_CACHED_MAP_PIXELS) {
      this.cache = null;
      return;
    }
    const { canvas, ctx } = createSurface(world.pixelWidth, world.pixelHeight, 'tiles/cache');
    paintTiles(ctx, world, 0, 0, world.width - 1, world.height - 1);
    this.cache = canvas;
  }
}

function paintTiles(
  ctx: CanvasRenderingContext2D,
  world: TileMap,
  x0: number,
  y0: number,
  x1: number,
  y1: number,
): void {
  const ts = world.tileSize;
  const tiles = palette().tiles;

  for (let ty = y0; ty <= y1; ty++) {
    for (let tx = x0; tx <= x1; tx++) {
      const px = tx * ts;
      const py = ty * ts;
      if (world.tiles[ty][tx] === WALL) {
        ctx.fillStyle = tiles.wallBody;
        ctx.fillRect(px, py, ts, ts);
        ctx.fillStyle = tiles.wallTop;
        ctx.fillRect(px, py, ts, 3);
        ctx.fillStyle = tiles.wallEdge;
        ctx.fillRect(px, py + ts - 2, ts, 2);
      } else {
        ctx.fillStyle = floorColor(tx, ty);
        ctx.fillRect(px, py, ts, ts);
        if (hasFloorSpeck(tx, ty)) {
          ctx.fillStyle = tiles.floorSpeck;
          ctx.fillRect(px + 4, py + 6, 3, 1);
        }
      }
    }
  }
}
