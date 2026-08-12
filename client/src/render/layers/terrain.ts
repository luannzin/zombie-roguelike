/**
 * Terrain layer: the forest floor and everything rooted in it.
 *
 * The map is baked once into an offscreen canvas, so a frame costs one blit
 * instead of thousands of draw calls. Very large maps fall back to painting
 * only the visible window each frame.
 *
 * Bake order matters and mirrors how the world is actually stacked:
 *   1. ground   every tile, from the seamless atlas
 *   2. grass    hashed tufts on floor tiles — decoration, never solid
 *   3. props    rocks and trees, row by row, each with a contact shadow
 *
 * Tree canopies are baked too, but they are ALSO redrawn per frame by
 * `drawCanopies`, after the entity pass. Redrawing opaque pixels over
 * themselves is a no-op where nothing moved, and where a player is standing
 * north of a trunk it puts them under the foliage — which is the whole reason
 * a top-down forest reads as a forest and not as a field of lollipops.
 */

import { FLOOR, ROCK, TREE, type TileMap } from '../../game/world';
import { createSurface } from '../../lib/canvas';
import { floorColor, hasFloorSpeck, palette } from '../../theme/palette';
import type { Camera } from '../camera';
import { tileHash, type PropSheet, type TerrainAtlas } from '../terrain';

/** Above this a map is drawn per-tile instead of cached. */
const MAX_CACHED_MAP_PIXELS = 4096 * 4096;

/** Share of floor tiles that get a grass tuft. */
const GRASS_CHANCE = 0.34;
/** Second tuft on a tile that already has one. */
const GRASS_DOUBLE_CHANCE = 0.4;
/** Contact shadow under a prop, as a fraction of the tile. */
const SHADOW_WIDTH = 0.78;
const SHADOW_HEIGHT = 0.24;
const SHADOW_ALPHA = 0.3;

export class TerrainLayer {
  private atlas: TerrainAtlas | null = null;
  private cache: HTMLCanvasElement | null = null;
  private cachedFor: TileMap | null = null;

  /** Swap in the loaded atlas (or null to keep the flat fallback). */
  setAtlas(atlas: TerrainAtlas | null): void {
    this.atlas = atlas;
    this.reset();
  }

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

    const window = visibleTiles(world, camera);
    if (this.atlas) {
      paintGround(ctx, world, this.atlas, window);
      paintProps(ctx, world, this.atlas, window);
    } else {
      paintFlat(ctx, world, window);
    }
  }

  /**
   * The overhanging part of every visible tree, drawn after entities.
   * Cheap: a few dozen blits of an already-decoded bitmap, no clipping.
   */
  drawCanopies(ctx: CanvasRenderingContext2D, world: TileMap, camera: Camera): void {
    const atlas = this.atlas;
    if (!atlas || atlas.tree.canopyHeight <= 0) return;

    const ts = world.tileSize;
    const { tree } = atlas;
    const { x0, y0, x1, y1 } = visibleTiles(world, camera);

    for (let ty = y0; ty <= y1; ty++) {
      for (let tx = x0; tx <= x1; tx++) {
        if (world.tiles[ty][tx] !== TREE) continue;
        const frame = variant(tree, tx, ty, world.seed, 2);
        // Same placement as the bake, cropped to the strip above the tile.
        const dx = tx * ts + (ts - tree.frameWidth) / 2;
        const dy = (ty + 1) * ts - tree.frameHeight;
        ctx.drawImage(
          tree.image,
          frame * tree.frameWidth,
          0,
          tree.frameWidth,
          tree.canopyHeight,
          dx,
          dy,
          tree.frameWidth,
          tree.canopyHeight,
        );
      }
    }
  }

  /** Drop the cached bitmap (map change, atlas arrival, teardown). */
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
    const { canvas, ctx } = createSurface(world.pixelWidth, world.pixelHeight, 'terrain/cache');
    const window = { x0: 0, y0: 0, x1: world.width - 1, y1: world.height - 1 };
    if (this.atlas) {
      paintGround(ctx, world, this.atlas, window);
      paintProps(ctx, world, this.atlas, window);
    } else {
      paintFlat(ctx, world, window);
    }
    this.cache = canvas;
  }
}

interface TileWindow {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

function visibleTiles(world: TileMap, camera: Camera): TileWindow {
  const ts = world.tileSize;
  return {
    // Props overhang upward, so the window starts a couple of rows early —
    // otherwise a tree just off the top edge pops in as you scroll to it.
    x0: Math.max(0, Math.floor(camera.renderX / ts) - 1),
    y0: Math.max(0, Math.floor(camera.renderY / ts) - 3),
    x1: Math.min(world.width - 1, Math.ceil((camera.renderX + camera.viewWidth) / ts)),
    y1: Math.min(world.height - 1, Math.ceil((camera.renderY + camera.viewHeight) / ts)),
  };
}

/** Which frame of a prop sheet this tile uses. Stable for the map's lifetime. */
function variant(sheet: PropSheet, tx: number, ty: number, seed: number, salt: number): number {
  return Math.floor(tileHash(tx, ty, seed, salt) * sheet.frames) % sheet.frames;
}

function paintGround(
  ctx: CanvasRenderingContext2D,
  world: TileMap,
  atlas: TerrainAtlas,
  { x0, y0, x1, y1 }: TileWindow,
): void {
  const ts = world.tileSize;
  const { ground, groundTile, groundCols, groundRows } = atlas;

  for (let ty = y0; ty <= y1; ty++) {
    for (let tx = x0; tx <= x1; tx++) {
      // Modulo, not a hash: adjacent cells of the atlas are adjacent in the
      // source texture, which is what keeps the floor seamless.
      const sx = (tx % groundCols) * groundTile;
      const sy = (ty % groundRows) * groundTile;
      ctx.drawImage(ground, sx, sy, groundTile, groundTile, tx * ts, ty * ts, ts, ts);
    }
  }
}

function paintProps(
  ctx: CanvasRenderingContext2D,
  world: TileMap,
  atlas: TerrainAtlas,
  { x0, y0, x1, y1 }: TileWindow,
): void {
  const ts = world.tileSize;
  const seed = world.seed;

  // Grass first: it is ground cover, so props and their shadows sit over it.
  for (let ty = y0; ty <= y1; ty++) {
    for (let tx = x0; tx <= x1; tx++) {
      if (world.tiles[ty][tx] !== FLOOR) continue;
      if (tileHash(tx, ty, seed, 11) >= GRASS_CHANCE) continue;
      drawTuft(ctx, atlas.grass, world, tx, ty, 0);
      if (tileHash(tx, ty, seed, 12) < GRASS_DOUBLE_CHANCE) {
        drawTuft(ctx, atlas.grass, world, tx, ty, 1);
      }
    }
  }

  // Row order so a prop overlaps the one behind it, never the one in front.
  const shadow = palette().entity.shadow;
  for (let ty = y0; ty <= y1; ty++) {
    for (let tx = x0; tx <= x1; tx++) {
      const tile = world.tiles[ty][tx];
      if (tile !== ROCK && tile !== TREE) continue;
      const sheet = tile === TREE ? atlas.tree : atlas.rock;
      const frame = variant(sheet, tx, ty, seed, tile === TREE ? 2 : 3);

      const baseY = (ty + 1) * ts;
      ctx.globalAlpha = SHADOW_ALPHA;
      ctx.fillStyle = shadow;
      ctx.beginPath();
      ctx.ellipse(
        tx * ts + ts / 2,
        baseY - (ts * SHADOW_HEIGHT) / 2,
        (ts * SHADOW_WIDTH) / 2,
        (ts * SHADOW_HEIGHT) / 2,
        0,
        0,
        Math.PI * 2,
      );
      ctx.fill();
      ctx.globalAlpha = 1;

      ctx.drawImage(
        sheet.image,
        frame * sheet.frameWidth,
        0,
        sheet.frameWidth,
        sheet.frameHeight,
        tx * ts + (ts - sheet.frameWidth) / 2,
        baseY - sheet.frameHeight,
        sheet.frameWidth,
        sheet.frameHeight,
      );
    }
  }
}

function drawTuft(
  ctx: CanvasRenderingContext2D,
  grass: PropSheet,
  world: TileMap,
  tx: number,
  ty: number,
  index: number,
): void {
  const ts = world.tileSize;
  const seed = world.seed;
  const frame = variant(grass, tx, ty, seed, 20 + index);
  // Jitter inside the tile so tufts do not line up on a lattice.
  const jx = (tileHash(tx, ty, seed, 30 + index) - 0.5) * (ts - grass.frameWidth);
  const jy = (tileHash(tx, ty, seed, 40 + index) - 0.5) * ts * 0.5;
  ctx.drawImage(
    grass.image,
    frame * grass.frameWidth,
    0,
    grass.frameWidth,
    grass.frameHeight,
    Math.round(tx * ts + (ts - grass.frameWidth) / 2 + jx),
    Math.round((ty + 1) * ts - grass.frameHeight + jy),
    grass.frameWidth,
    grass.frameHeight,
  );
}

/** No atlas built yet: flat theme colours, so the map is never blank. */
function paintFlat(
  ctx: CanvasRenderingContext2D,
  world: TileMap,
  { x0, y0, x1, y1 }: TileWindow,
): void {
  const ts = world.tileSize;
  const tiles = palette().tiles;

  for (let ty = y0; ty <= y1; ty++) {
    for (let tx = x0; tx <= x1; tx++) {
      const px = tx * ts;
      const py = ty * ts;
      if (world.tiles[ty][tx] !== FLOOR) {
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
