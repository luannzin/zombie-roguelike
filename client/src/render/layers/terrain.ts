/**
 * Terrain layer: the forest floor, what is rooted in it, and what moves.
 *
 * Split into THREE passes because the world is stacked in three parts and the
 * player stands in the middle of it:
 *
 *   ground()      floor + rocks + tree trunks. Static, so it bakes into two
 *                 offscreen canvases and costs two blits a frame.
 *   undergrowth() grass tufts. Drawn live because they SWAY, which is the
 *                 cheapest thing that stops a forest looking like a photograph.
 *   overgrowth()  tree canopies and ferns, drawn AFTER characters, so you walk
 *                 under foliage and behind bushes instead of over a flat plane.
 *
 * The bake is two canvases, not one, precisely so the swaying grass can sit
 * between them: ground underneath, grass on top of it, props on top of that.
 * Merging them would force the grass either under the ground or over the rocks.
 *
 * Sway is per-plant, never global. Every tuft gets its own phase and speed from
 * the tile hash; a forest where every blade leans the same way at the same
 * moment reads as a screen filter, not as wind.
 */

import { FLOOR, ROCK, TREE, VOID, type FirePlace, type TileMap } from '../../game/world';
import { createSurface } from '../../lib/canvas';
import { floorColor, hasFloorSpeck, palette } from '../../theme/palette';
import type { Camera } from '../camera';
import type { Projection } from '../projection';
import { tileHash, type PropSheet, type TerrainAtlas } from '../terrain';

/** Above this a map is drawn per-tile instead of cached. */
const MAX_CACHED_MAP_PIXELS = 4096 * 4096;

/** Share of floor tiles that get a grass tuft. */
const GRASS_CHANCE = 0.34;
/** Second tuft on a tile that already has one. */
const GRASS_DOUBLE_CHANCE = 0.4;
/** Share of floor tiles that get a foreground bush. Deliberately rare. */
const FERN_CHANCE = 0.045;

/** Peak horizontal lean of a swaying plant, in world px. */
const SWAY_GRASS = 0.9;
const SWAY_FERN = 1.4;
/** Radians/second of the sway oscillation, before per-plant variation. */
const SWAY_RATE = 1.5;

/** Contact shadow under a prop, as a fraction of the tile. */
const SHADOW_WIDTH = 0.78;
const SHADOW_HEIGHT = 0.24;
const SHADOW_ALPHA = 0.3;

/**
 * Veto for a decorative plant on a floor tile. Used to keep an area clear of
 * undergrowth without making its tiles solid — see the lobby's hearth.
 */
export type DecorationMask = (tx: number, ty: number) => boolean;

export class TerrainLayer {
  private atlas: TerrainAtlas | null = null;
  private groundCache: HTMLCanvasElement | null = null;
  private propCache: HTMLCanvasElement | null = null;
  private cachedFor: TileMap | null = null;
  private decorationMask: DecorationMask | null = null;

  /** Swap in the loaded atlas (or null to keep the flat fallback). */
  setAtlas(atlas: TerrainAtlas | null): void {
    this.atlas = atlas;
    this.reset();
  }

  /**
   * Restrict where grass and ferns may grow. `null` (the default) allows them
   * on every floor tile, which is what the arena wants.
   *
   * Only plants are affected: rocks and trees are tile kinds and are decided by
   * whoever built the map. This is deliberately not a tile kind of its own —
   * "floor with nothing growing on it" must stay walkable, and `isSolidTile`
   * treats anything that is not `FLOOR` as a wall.
   */
  setDecorationMask(mask: DecorationMask | null): void {
    this.decorationMask = mask;
  }

  /**
   * Floor and everything standing in it. Two blits when cached.
   * Caller must have applied the world-space transform.
   */
  ground(ctx: CanvasRenderingContext2D, world: TileMap, camera: Camera, time: number): void {
    if (this.cachedFor !== world) this.rebuild(world);
    const window = visibleTiles(world, camera);

    if (this.groundCache) {
      blit(ctx, this.groundCache, world, camera);
      this.undergrowth(ctx, world, window, time);
      if (this.propCache) blit(ctx, this.propCache, world, camera);
      return;
    }

    // Uncached (very large map): paint the visible window in the same order.
    if (this.atlas) {
      paintGround(ctx, world, this.atlas, window);
      this.undergrowth(ctx, world, window, time);
      paintProps(ctx, world, this.atlas, window);
    } else {
      paintFlat(ctx, world, window);
    }
  }

  /**
   * One bonfire, in SCREEN space, so it can be depth-sorted with the party.
   *
   * The fire is the one prop that is neither baked nor drawn with the ground.
   * Baked, it could not animate; drawn under the entity pass, it would be
   * covered by a player standing behind it, and a ring of characters sitting
   * around a picture of a fire is the exact thing this scene must not look
   * like. So the renderer hands it to the same sort the entities go through and
   * it overlaps whoever is further from the camera than the flame is.
   *
   * `fps` on the manifest entry is what makes these frames a loop rather than
   * variants — see the prop-sheet contract in `render/terrain.ts`.
   */
  fire(
    ctx: CanvasRenderingContext2D,
    view: Projection,
    fire: FirePlace,
    time: number,
  ): void {
    const sheet = this.atlas?.campfire;
    if (!sheet) return;
    const frame = sheet.fps > 0 ? Math.floor(time * sheet.fps) % sheet.frames : 0;
    ctx.drawImage(
      sheet.image,
      frame * sheet.frameWidth,
      0,
      sheet.frameWidth,
      sheet.frameHeight,
      view.x(fire.x) - Math.round((sheet.frameWidth * view.zoom) / 2),
      view.y(fire.y) - sheet.frameHeight * view.zoom,
      sheet.frameWidth * view.zoom,
      sheet.frameHeight * view.zoom,
    );
  }

  /**
   * Foliage that closes over the player: tree canopies and ferns.
   * Drawn after the entity pass, still in world space.
   */
  overgrowth(ctx: CanvasRenderingContext2D, world: TileMap, camera: Camera, time: number): void {
    const atlas = this.atlas;
    if (!atlas) return;

    const ts = world.tileSize;
    const seed = world.seed;
    const { x0, y0, x1, y1 } = visibleTiles(world, camera);
    const { tree, fern } = atlas;

    for (let ty = y0; ty <= y1; ty++) {
      for (let tx = x0; tx <= x1; tx++) {
        const tile = world.tiles[ty][tx];

        if (tile === TREE && tree.canopyHeight > 0) {
          // The canopy is already in the prop bake; redrawing the same opaque
          // pixels is a no-op except where a character has since been drawn
          // over them, which is exactly the case we want covered.
          const frame = variant(tree, tx, ty, seed, 2);
          ctx.drawImage(
            tree.image,
            frame * tree.frameWidth,
            0,
            tree.frameWidth,
            tree.canopyHeight,
            tx * ts + (ts - tree.frameWidth) / 2,
            (ty + 1) * ts - tree.frameHeight,
            tree.frameWidth,
            tree.canopyHeight,
          );
          continue;
        }

        if (tile !== FLOOR) continue;
        if (this.decorationMask && !this.decorationMask(tx, ty)) continue;
        if (tileHash(tx, ty, seed, 51) >= FERN_CHANCE) continue;
        const frame = variant(fern, tx, ty, seed, 52);
        const lean = sway(tx, ty, seed, time, SWAY_FERN, 53);
        ctx.drawImage(
          fern.image,
          frame * fern.frameWidth,
          0,
          fern.frameWidth,
          fern.frameHeight,
          Math.round(tx * ts + (ts - fern.frameWidth) / 2 + lean),
          Math.round((ty + 1) * ts - fern.frameHeight),
          fern.frameWidth,
          fern.frameHeight,
        );
      }
    }
  }

  /** Drop the cached bitmaps (map change, atlas arrival, teardown). */
  reset(): void {
    this.groundCache = null;
    this.propCache = null;
    this.cachedFor = null;
  }

  /** Swaying grass. Live, so it cannot live in the bake. */
  private undergrowth(
    ctx: CanvasRenderingContext2D,
    world: TileMap,
    { x0, y0, x1, y1 }: TileWindow,
    time: number,
  ): void {
    const atlas = this.atlas;
    if (!atlas) return;
    const seed = world.seed;

    for (let ty = y0; ty <= y1; ty++) {
      for (let tx = x0; tx <= x1; tx++) {
        if (world.tiles[ty][tx] !== FLOOR) continue;
        if (this.decorationMask && !this.decorationMask(tx, ty)) continue;
        if (tileHash(tx, ty, seed, 11) >= GRASS_CHANCE) continue;
        drawTuft(ctx, atlas.grass, world, tx, ty, 0, time);
        if (tileHash(tx, ty, seed, 12) < GRASS_DOUBLE_CHANCE) {
          drawTuft(ctx, atlas.grass, world, tx, ty, 1, time);
        }
      }
    }
  }

  private rebuild(world: TileMap): void {
    this.cachedFor = world;
    if (world.pixelWidth * world.pixelHeight > MAX_CACHED_MAP_PIXELS) {
      this.groundCache = null;
      this.propCache = null;
      return;
    }
    const window = { x0: 0, y0: 0, x1: world.width - 1, y1: world.height - 1 };

    const ground = createSurface(world.pixelWidth, world.pixelHeight, 'terrain/ground');
    if (this.atlas) paintGround(ground.ctx, world, this.atlas, window);
    else paintFlat(ground.ctx, world, window);
    this.groundCache = ground.canvas;

    if (this.atlas) {
      const props = createSurface(world.pixelWidth, world.pixelHeight, 'terrain/props');
      paintProps(props.ctx, world, this.atlas, window);
      this.propCache = props.canvas;
    } else {
      this.propCache = null;
    }
  }
}

interface TileWindow {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

function blit(
  ctx: CanvasRenderingContext2D,
  cache: HTMLCanvasElement,
  world: TileMap,
  camera: Camera,
): void {
  const sx = Math.max(0, Math.floor(camera.renderX));
  const sy = Math.max(0, Math.floor(camera.renderY));
  const sw = Math.min(world.pixelWidth - sx, Math.ceil(camera.viewWidth) + 2);
  const sh = Math.min(world.pixelHeight - sy, Math.ceil(camera.viewHeight) + 2);
  if (sw > 0 && sh > 0) ctx.drawImage(cache, sx, sy, sw, sh, sx, sy, sw, sh);
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

/**
 * Horizontal lean of one plant, in world px.
 *
 * Phase and rate both come from the tile hash. That per-plant variation is the
 * whole point: a synchronised field looks like the screen is wobbling, while a
 * desynchronised one looks like air moving through leaves.
 */
function sway(
  tx: number,
  ty: number,
  seed: number,
  time: number,
  amount: number,
  salt: number,
): number {
  const phase = tileHash(tx, ty, seed, salt) * Math.PI * 2;
  const rate = SWAY_RATE * (0.7 + tileHash(tx, ty, seed, salt + 1) * 0.6);
  return Math.sin(time * rate + phase) * amount;
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
      if (world.tiles[ty][tx] === VOID) continue;
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
  const shadow = palette().entity.shadow;

  // Row order so a prop overlaps the one behind it, never the one in front.
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
  time: number,
): void {
  const ts = world.tileSize;
  const seed = world.seed;
  const frame = variant(grass, tx, ty, seed, 20 + index);
  // Jitter inside the tile so tufts do not line up on a lattice.
  const jx = (tileHash(tx, ty, seed, 30 + index) - 0.5) * (ts - grass.frameWidth);
  const jy = (tileHash(tx, ty, seed, 40 + index) - 0.5) * ts * 0.5;
  const lean = sway(tx, ty, seed, time, SWAY_GRASS, 60 + index * 2);
  ctx.drawImage(
    grass.image,
    frame * grass.frameWidth,
    0,
    grass.frameWidth,
    grass.frameHeight,
    Math.round(tx * ts + (ts - grass.frameWidth) / 2 + jx + lean),
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
      const tile = world.tiles[ty][tx];
      if (tile === VOID) continue;
      if (tile !== FLOOR) {
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
