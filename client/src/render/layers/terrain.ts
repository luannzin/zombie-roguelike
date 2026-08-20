/**
 * Terrain layer: the forest floor, what is rooted in it, and what moves.
 *
 * Split into THREE passes because the world is stacked in three parts and the
 * player stands in the middle of it:
 *
 *   ground()      floor + litter + rocks + trunks. Static, so it bakes into
 *                 two offscreen canvases and costs two blits a frame.
 *   undergrowth() grass tufts. Drawn live because they SWAY, which
 *                 is the cheapest thing that stops a forest looking like a
 *                 photograph.
 *   overgrowth()  tree canopies, bushes and ferns, drawn AFTER characters, so
 *                 you walk under foliage and INTO a thicket instead of over a
 *                 flat plane.
 *
 * The bake is two canvases, not one, precisely so the swaying plants can sit
 * between them: ground underneath, plants on top of it, props on top of that.
 * Merging them would force the grass either under the ground or over the rocks.
 *
 * FOUR SOILS, ONE FLOOR. A single ground texture over a whole map is the
 * loudest tell that a forest was generated — the eye finds the atlas repeat in
 * seconds. So a low-frequency MATERIAL FIELD, hashed from the map seed, says
 * which of loam / turf / mud / leaf litter each tile is made of. A hard tile
 * boundary between two soils would only move the tell, so the fringe is
 * dissolved through the graded stencils in `blend.png`: the neighbouring soil
 * is drawn through the stencil whose coverage matches how far this tile has
 * crossed the boundary, and the two interlock in ragged teeth.
 *
 * BLIGHT is the same idea applied to trunks. A second, coarser field marks
 * stands of dead wood, so bare trees come in GROVES — a clearing full of grey
 * limbs you can see through, next to a thicket you cannot — instead of being
 * salted evenly across the map, which would read as damage to the art rather
 * than as a place.
 *
 * Sway is per-plant, never global. Every tuft gets its own phase and speed from
 * the tile hash; a forest where every blade leans the same way at the same
 * moment reads as a screen filter, not as wind.
 */

import { FLOOR, LOW, PROP, ROCK, TREE, VOID, type FirePlace, type TileMap } from '../../game/world';
import { createSurface } from '../../lib/canvas';
import { floorColor, hasFloorSpeck, palette } from '../../theme/palette';
import type { Camera } from '../camera';
import type { Projection } from '../projection';
import type { DisturbanceField } from '../disturbance';
import type { SceneryAtlas } from '../scenery';
import { tileHash, type DecalSheet, type PropSheet, type TerrainAtlas } from '../terrain';
import * as wind from '../wind';
import { bakeSceneryDecals } from './scenery';

/** Above this a map is drawn per-tile instead of cached. */
const MAX_CACHED_MAP_PIXELS = 4096 * 4096;

/** Share of floor tiles that get a grass tuft. */
const GRASS_CHANCE = 0.34;
/** Second tuft on a tile that already has one. */
const GRASS_DOUBLE_CHANCE = 0.4;
/** Share of floor tiles that get a bush. Drawn OVER bodies, with the fern. */
const BUSH_CHANCE = 0.055;
/** Share of floor tiles that get a fern. Deliberately rare. */
const FERN_CHANCE = 0.045;

/** Share of floor tiles that get flat litter baked into the ground. */
const LEAVES_CHANCE = 0.16;
const BRANCH_CHANCE = 0.07;
/** Ground stains are sampled on a coarse lattice — they are 2 tiles across and
 *  hashing them per tile would carpet the map in overlapping blotches. */
const PATCH_STRIDE = 5;
const PATCH_CHANCE = 0.32;

/** Peak horizontal lean of a swaying plant, in world px. */
const SWAY_GRASS = 0.9;
const SWAY_BUSH = 1.1;
const SWAY_FERN = 1.4;
/** Radians/second of the sway oscillation, before per-plant variation. */
const SWAY_RATE = 1.5;

/**
 * How hard a passing body pushes each plant, as a multiple of the shared
 * disturbance field. A tuft underfoot is trodden; a bush is shouldered aside;
 * a fern is the thinnest of the three and whips furthest. Bush and fern are
 * both drawn in FRONT of the character now, so their bend is the reaction the
 * player actually watches and both are worth the reach.
 */
const GRASS_PUSH = 1;
const BUSH_PUSH = 0.8;
const FERN_PUSH = 1.25;

/** Contact shadow under a prop, as a fraction of the tile. */
const SHADOW_WIDTH = 0.78;
const SHADOW_HEIGHT = 0.24;
const SHADOW_ALPHA = 0.3;

/**
 * Material field. Lattice cell in TILES: big enough that a soil covers a
 * recognisable stretch of ground and small enough that a screen usually holds
 * more than one.
 */
const MATERIAL_CELL = 13;
/**
 * Where one soil ends and the next begins, on the 0..1 field. Unequal on
 * purpose — loam is the forest's default and the others are things that have
 * happened to it, so mud (the narrowest band) reads as low ground rather than
 * as a quarter of the map.
 */
const MATERIAL_EDGES = [0, 0.46, 0.7, 0.87, 1];
/**
 * Width of the dissolve either side of an edge, in field units.
 *
 * Both ends of this are visible failures and they are opposite. Too WIDE and
 * the narrowest band (mud, 0.13) has no interior left, so the map reads as one
 * dithered mush of every soil at once instead of as ground that changes. Too
 * NARROW and a region's edge falls inside a single tile, which quantizes it to
 * the tile grid and draws soil patches with straight rectangular sides.
 */
const MATERIAL_FRINGE = 0.07;
/**
 * Per-tile jitter on the field before it is banded, as a full range.
 *
 * Frays which TILES are on a boundary, where the stencil frays the boundary
 * inside a tile. Both are needed: the stencil alone still leaves the run of
 * fringe tiles following a smooth contour, and a smooth contour on a grid is a
 * staircase.
 */
const MATERIAL_JITTER = 0.06;

/** Blight field: coarser than the soil, so a dead stand spans a clearing. */
const BLIGHT_CELL = 17;
/** Above this the field is a blighted stand. */
const BLIGHT_AT = 0.62;
/** Share of trunks inside a stand that are dead, at the heart of it. */
const BLIGHT_DENSITY = 0.85;
/** Share of dead trunks that are cut stumps instead — somebody worked here. */
const STUMP_SHARE = 0.16;

/**
 * Veto for a decorative plant on a floor tile. Used to keep an area clear of
 * undergrowth without making its tiles solid — see the lobby's hearth.
 */
export type DecorationMask = (tx: number, ty: number) => boolean;

export class TerrainLayer {
  private atlas: TerrainAtlas | null = null;
  private scenery: SceneryAtlas | null = null;
  private groundCache: HTMLCanvasElement | null = null;
  private propCache: HTMLCanvasElement | null = null;
  /** One tile-sized scratch surface, reused for every soil dissolve. */
  private stencil: { canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D } | null = null;
  private cachedFor: TileMap | null = null;
  private decorationMask: DecorationMask | null = null;

  /** Swap in the loaded atlas (or null to keep the flat fallback). */
  setAtlas(atlas: TerrainAtlas | null): void {
    this.atlas = atlas;
    this.stencil = null;
    this.reset();
  }

  /**
   * Swap in the scenery atlas. Flat scenery — blood, boot prints, dropped
   * clothing — is baked into the SAME ground canvas as the forest's own
   * litter, so it arriving is a reason to rebuild that canvas.
   */
  setSceneryAtlas(atlas: SceneryAtlas | null): void {
    this.scenery = atlas;
    this.reset();
  }

  /**
   * Restrict where grass, bushes and ferns may grow. `null` (the default)
   * allows them on every floor tile, which is what the arena wants.
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
  ground(
    ctx: CanvasRenderingContext2D,
    world: TileMap,
    camera: Camera,
    time: number,
    bodies: DisturbanceField | null = null,
  ): void {
    if (this.cachedFor !== world) this.rebuild(world);
    const window = visibleTiles(world, camera);

    if (this.groundCache) {
      blit(ctx, this.groundCache, world, camera);
      this.undergrowth(ctx, world, window, time, bodies);
      if (this.propCache) blit(ctx, this.propCache, world, camera);
      return;
    }

    // Uncached (very large map): paint the visible window in the same order.
    if (this.atlas) {
      this.paintGround(ctx, world, this.atlas, window, true);
      this.undergrowth(ctx, world, window, time, bodies);
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
  overgrowth(
    ctx: CanvasRenderingContext2D,
    world: TileMap,
    camera: Camera,
    time: number,
    bodies: DisturbanceField | null = null,
  ): void {
    const atlas = this.atlas;
    if (!atlas) return;

    const ts = world.tileSize;
    const seed = world.seed;
    const { x0, y0, x1, y1 } = visibleTiles(world, camera);
    const { fern } = atlas;

    for (let ty = y0; ty <= y1; ty++) {
      for (let tx = x0; tx <= x1; tx++) {
        const tile = world.tiles[ty][tx];

        if (tile === TREE) {
          // The canopy is already in the prop bake; redrawing the same opaque
          // pixels is a no-op except where a character has since been drawn
          // over them, which is exactly the case we want covered. The sheet is
          // resolved through the same function the bake used, or a body would
          // walk under a canopy belonging to a different tree.
          const trunk = trunkSheet(atlas, tx, ty, seed);
          if (trunk.canopyHeight <= 0) continue;
          const frame = variant(trunk, tx, ty, seed, 2);
          ctx.drawImage(
            trunk.image,
            frame * trunk.frameWidth,
            0,
            trunk.frameWidth,
            trunk.canopyHeight,
            tx * ts + (ts - trunk.frameWidth) / 2,
            (ty + 1) * ts - trunk.frameHeight,
            trunk.frameWidth,
            trunk.canopyHeight,
          );
          continue;
        }

        if (tile !== FLOOR) continue;
        if (this.decorationMask && !this.decorationMask(tx, ty)) continue;

        // BUSHES CLOSE OVER A BODY. They used to be drawn with the grass, one
        // pass before the characters, which meant the tallest undergrowth on
        // the map was the only foliage a player could never be hidden by —
        // you walked in front of a thicket the way you walk in front of a
        // painting of one. Same claim as the fern's, one line above it in the
        // depth stack because a bush is the bigger mass: standing in it, you
        // are in cover and it looks like it.
        if (tileHash(tx, ty, seed, 13) < BUSH_CHANCE) {
          drawPlant(ctx, atlas.bush, world, tx, ty, time, SWAY_BUSH, 14, bodies);
        }

        if (tileHash(tx, ty, seed, 51) >= FERN_CHANCE) continue;
        const frame = variant(fern, tx, ty, seed, 52);
        // Ferns are the ones the player pushes through face-first: they are
        // drawn in FRONT of a body, so their bend is the most visible reaction
        // in the frame and it is worth the extra reach.
        const lean =
          sway(tx, ty, seed, time, SWAY_FERN, 53, world.tileSize) +
          bendOf(bodies, tx, ty, world.tileSize) * FERN_PUSH;
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

  /**
   * Trees (and rocks) just landed on tiles that used to be VOID. Stamp them
   * into the prop bake without rebuilding the soil — the corridor was already
   * forest floor, and the slam is the trunks appearing on it.
   */
  stampProps(world: TileMap, tiles: ReadonlyArray<[tx: number, ty: number, kind: number]>): void {
    if (!this.propCache || this.cachedFor !== world || !this.atlas || tiles.length === 0) {
      this.reset();
      return;
    }
    const ts = world.tileSize;
    let x0 = world.width;
    let y0 = world.height;
    let x1 = 0;
    let y1 = 0;
    for (const [tx, ty] of tiles) {
      if (tx < x0) x0 = tx;
      if (ty < y0) y0 = ty;
      if (tx > x1) x1 = tx;
      if (ty > y1) y1 = ty;
    }
    // Canopies overhang upward; a stamp that forgot the rows above would
    // clip a trunk that just grew in.
    const window = {
      x0: Math.max(0, x0 - 1),
      y0: Math.max(0, y0 - 3),
      x1: Math.min(world.width - 1, x1 + 1),
      y1: Math.min(world.height - 1, y1 + 1),
    };
    const ctx = this.propCache.getContext('2d');
    if (!ctx) {
      this.reset();
      return;
    }
    ctx.clearRect(window.x0 * ts, window.y0 * ts, (window.x1 - window.x0 + 1) * ts, (window.y1 - window.y0 + 4) * ts);
    paintProps(ctx, world, this.atlas, window);
  }

  /** Swaying grass. Live, so it cannot live in the bake. */
  private undergrowth(
    ctx: CanvasRenderingContext2D,
    world: TileMap,
    { x0, y0, x1, y1 }: TileWindow,
    time: number,
    bodies: DisturbanceField | null,
  ): void {
    const atlas = this.atlas;
    if (!atlas) return;
    const seed = world.seed;

    for (let ty = y0; ty <= y1; ty++) {
      for (let tx = x0; tx <= x1; tx++) {
        if (world.tiles[ty][tx] !== FLOOR) continue;
        if (this.decorationMask && !this.decorationMask(tx, ty)) continue;

        // A BUSH IS CLAIMED HERE AND DRAWN IN `overgrowth`. The tile still
        // gives up its grass — a bush and a tuft on the same tile is a pile,
        // not undergrowth — but the shrub itself belongs to the pass that runs
        // AFTER the bodies, because a waist-high thicket that a character
        // stands in front of is not a thicket. See `overgrowth`.
        if (tileHash(tx, ty, seed, 13) < BUSH_CHANCE) continue;
        if (tileHash(tx, ty, seed, 11) >= GRASS_CHANCE) continue;
        drawTuft(ctx, atlas.grass, world, tx, ty, 0, time, bodies);
        if (tileHash(tx, ty, seed, 12) < GRASS_DOUBLE_CHANCE) {
          drawTuft(ctx, atlas.grass, world, tx, ty, 1, time, bodies);
        }
      }
    }
  }

  /**
   * The floor: soil, its dissolved boundaries, and everything lying flat on it.
   *
   * Order inside this pass is a stack of things resting on each other — soil,
   * then stains that soaked into it, then litter that fell on top, then what
   * people left last. A blood stain under a drift of leaves is older than the
   * leaves, which is not the story any of these scenes is telling.
   */
  private paintGround(
    ctx: CanvasRenderingContext2D,
    world: TileMap,
    atlas: TerrainAtlas,
    window: TileWindow,
    live = false,
  ): void {
    this.paintSoil(ctx, world, atlas, window);
    paintPatches(ctx, world, atlas.patch, window);
    paintLitter(ctx, world, atlas, window, this.decorationMask);
    if (this.scenery) {
      const ts = world.tileSize;
      bakeSceneryDecals(
        ctx,
        world,
        this.scenery,
        // Baking walks the whole map once; painting live walks it every frame,
        // so that path gets the visible window to cull against.
        live
          ? {
              x0: window.x0 * ts,
              y0: window.y0 * ts,
              x1: (window.x1 + 1) * ts,
              y1: (window.y1 + 1) * ts,
            }
          : null,
      );
    }
  }

  /** Soil, one tile at a time, with the material boundaries dissolved. */
  private paintSoil(
    ctx: CanvasRenderingContext2D,
    world: TileMap,
    atlas: TerrainAtlas,
    { x0, y0, x1, y1 }: TileWindow,
  ): void {
    const ts = world.tileSize;
    const seed = world.seed;
    const { grounds, blend } = atlas;
    if (grounds.length === 0) return;

    for (let ty = y0; ty <= y1; ty++) {
      for (let tx = x0; tx <= x1; tx++) {
        const mix = materialAt(tx, ty, seed, grounds.length);
        drawSoil(ctx, grounds[mix.index], tx, ty, ts);
        if (mix.other < 0) continue;

        // The neighbouring soil, through the stencil whose coverage matches how
        // far this tile has crossed the boundary. Drawn into a scratch tile and
        // masked with `destination-in`, because the alternative — clipping —
        // would antialias the teeth into a blur on a canvas that is otherwise
        // entirely hard pixels.
        const step = Math.min(
          blend.frames - 1,
          Math.max(0, Math.floor(mix.coverage * blend.frames)),
        );
        const scratch = this.scratch(ts);
        scratch.ctx.clearRect(0, 0, ts, ts);
        drawSoil(scratch.ctx, grounds[mix.other], tx, ty, ts, true, true);
        scratch.ctx.globalCompositeOperation = 'destination-in';
        scratch.ctx.drawImage(
          blend.image,
          step * blend.frameWidth, 0, blend.frameWidth, blend.frameHeight,
          0, 0, ts, ts,
        );
        scratch.ctx.globalCompositeOperation = 'source-over';
        ctx.drawImage(scratch.canvas, tx * ts, ty * ts);
      }
    }
  }

  private scratch(size: number): { canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D } {
    if (!this.stencil || this.stencil.canvas.width !== size) {
      this.stencil = createSurface(size, size, 'terrain/blend');
    }
    return this.stencil;
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
    if (this.atlas) this.paintGround(ground.ctx, world, this.atlas, window);
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

/**
 * Smooth 0..1 noise over the tile grid, from the map seed.
 *
 * TWO octaves of bilinear value noise with a quintic fade — the same mixer the
 * ground textures are built from, so a soil boundary in the field has the same
 * softness as the grain inside the soil. `salt` picks the field: every
 * independent decision (which soil, which stand is dead) needs its own, or the
 * material map and the blight map would be the same shape.
 *
 * The second octave is what stops the regions being SQUARE. One bilinear
 * lattice has its extrema on the lattice points and its saddles between them,
 * so every level set through it is an axis-aligned blob about a cell across —
 * on the floor that reads as a grid of soil patches, which is the exact
 * artefact the whole material field exists to hide.
 */
function field(tx: number, ty: number, seed: number, cell: number, salt: number): number {
  return (
    octave(tx, ty, seed, cell, salt) * 0.72 + octave(tx, ty, seed, cell / 2.7, salt + 1) * 0.28
  );
}

function octave(tx: number, ty: number, seed: number, cell: number, salt: number): number {
  const fx = tx / cell;
  const fy = ty / cell;
  const gx = Math.floor(fx);
  const gy = Math.floor(fy);
  const ax = fade(fx - gx);
  const ay = fade(fy - gy);
  const top =
    tileHash(gx, gy, seed, salt) * (1 - ax) + tileHash(gx + 1, gy, seed, salt) * ax;
  const bottom =
    tileHash(gx, gy + 1, seed, salt) * (1 - ax) + tileHash(gx + 1, gy + 1, seed, salt) * ax;
  return top * (1 - ay) + bottom * ay;
}

function fade(t: number): number {
  return t * t * t * (t * (t * 6 - 15) + 10);
}

/**
 * Which soil a tile is made of, as an index into the atlas's `grounds`.
 *
 * Exported because the floor is not only a texture any more: how well ground
 * takes a boot print, and how much dust a footstep kicks up, are properties of
 * what you are standing on. Reading the same field the floor is painted from
 * is what keeps those honest — a print that sinks into mud has to be on a tile
 * the player can SEE is mud.
 */
export function soilAt(tx: number, ty: number, seed: number): number {
  return materialAt(tx, ty, seed, MATERIAL_EDGES.length - 1).index;
}

interface Material {
  /** Soil this tile is made of. */
  index: number;
  /** Soil bleeding in from the nearest boundary, or -1 when there is none. */
  other: number;
  /** 0..0.5 — how much of `other` shows through. */
  coverage: number;
}

/**
 * Which soil a tile is, and what is bleeding into it.
 *
 * Coverage peaks at 0.5 exactly on a boundary, so the tile on either side gives
 * up half of itself and the two soils meet as an interlock rather than as a
 * fade one way. Anything higher and the fringe reads as a third material.
 */
function materialAt(tx: number, ty: number, seed: number, count: number): Material {
  const value = clamp01(
    field(tx, ty, seed, MATERIAL_CELL, 71) +
      (tileHash(tx, ty, seed, 72) - 0.5) * MATERIAL_JITTER,
  );

  const bands = Math.min(count, MATERIAL_EDGES.length - 1);
  let index = bands - 1;
  for (let band = 0; band < bands; band++) {
    if (value < MATERIAL_EDGES[band + 1]) {
      index = band;
      break;
    }
  }

  const below = value - MATERIAL_EDGES[index];
  const above = MATERIAL_EDGES[index + 1] - value;
  const [distance, other] = below < above ? [below, index - 1] : [above, index + 1];
  if (other < 0 || other >= bands || distance >= MATERIAL_FRINGE) {
    return { index, other: -1, coverage: 0 };
  }
  return { index, other, coverage: (1 - distance / MATERIAL_FRINGE) * 0.5 };
}

/**
 * One tile of one soil.
 *
 * Modulo, not a hash: adjacent cells of an atlas are adjacent in the source
 * texture, which is what keeps the floor seamless. `offset` shifts the cell
 * pick by one so the soil bleeding across a boundary is not the identical
 * pixels its neighbour would have drawn — the two atlases have different
 * grain, but sharing the phase makes the teeth line up suspiciously well.
 */
function drawSoil(
  ctx: CanvasRenderingContext2D,
  sheet: { image: HTMLImageElement; tile: number; cols: number; rows: number },
  tx: number,
  ty: number,
  ts: number,
  offset = false,
  local = false,
): void {
  const shift = offset ? 1 : 0;
  const sx = (((tx + shift) % sheet.cols) + sheet.cols) % sheet.cols;
  const sy = (((ty + shift) % sheet.rows) + sheet.rows) % sheet.rows;
  ctx.drawImage(
    sheet.image,
    sx * sheet.tile, sy * sheet.tile, sheet.tile, sheet.tile,
    local ? 0 : tx * ts, local ? 0 : ty * ts, ts, ts,
  );
}

/** Which frame of a prop sheet this tile uses. Stable for the map's lifetime. */
function variant(sheet: PropSheet, tx: number, ty: number, seed: number, salt: number): number {
  return Math.floor(tileHash(tx, ty, seed, salt) * sheet.frames) % sheet.frames;
}

/**
 * Living tree, dead tree or stump for a TREE tile.
 *
 * Read by BOTH the prop bake and the overgrowth pass, and it has to be: they
 * draw the same trunk twice, and a canopy redrawn from a different sheet than
 * the one baked underneath would leave a living crown hanging over a bare
 * trunk wherever a body walked past.
 */
function trunkSheet(atlas: TerrainAtlas, tx: number, ty: number, seed: number): PropSheet {
  const blight = field(tx, ty, seed, BLIGHT_CELL, 81);
  if (blight <= BLIGHT_AT) return atlas.tree;
  // Density ramps from the edge of the stand to its heart, so a grove fades
  // into the living wood instead of ending on a line.
  const depth = Math.min(1, (blight - BLIGHT_AT) / (1 - BLIGHT_AT));
  const roll = tileHash(tx, ty, seed, 82);
  if (roll >= depth * BLIGHT_DENSITY) return atlas.tree;
  return roll < depth * BLIGHT_DENSITY * STUMP_SHARE ? atlas.stump : atlas.deadtree;
}

/**
 * Horizontal lean of one plant, in world px.
 *
 * Phase and rate come from the tile hash and the GUST comes from `wind.ts`.
 * Both halves are needed and they fail in opposite ways: a purely per-plant
 * field looks like air moving through leaves but never like weather, and a
 * purely shared one looks like the screen wobbling. `wind.lean` mixes them,
 * and every other bending thing in the game — including the scenery's signs
 * and tent canvas — reads the same function, so a gust crossing a clearing
 * moves the weeds and the signpost on one beat.
 */
function sway(
  tx: number,
  ty: number,
  seed: number,
  time: number,
  amount: number,
  salt: number,
  tileSize: number,
): number {
  const phase = tileHash(tx, ty, seed, salt) * Math.PI * 2;
  const rate = SWAY_RATE * (0.7 + tileHash(tx, ty, seed, salt + 1) * 0.6);
  // Sampled at the plant's own world position: the gust is a travelling front,
  // so where it is matters as much as when.
  return wind.lean((tx + 0.5) * tileSize, (ty + 0.5) * tileSize, time, amount, phase, rate);
}

/** Displacement from nearby bodies for a plant on this tile, in world px. */
function bendOf(
  bodies: DisturbanceField | null,
  tx: number,
  ty: number,
  tileSize: number,
): number {
  if (!bodies || bodies.idle) return 0;
  // Measured at the plant's ROOT, not its centre: a body standing on the tile
  // below a tuft is touching its base, and pushing from the middle of the
  // sprite would have tall plants react a tile early.
  return bodies.bendAt((tx + 0.5) * tileSize, (ty + 1) * tileSize);
}

/** Ground stains — "manchas". Sampled coarsely; they are 2 tiles across. */
function paintPatches(
  ctx: CanvasRenderingContext2D,
  world: TileMap,
  patch: DecalSheet,
  { x0, y0, x1, y1 }: TileWindow,
): void {
  const ts = world.tileSize;
  const seed = world.seed;
  const first = (v: number) => Math.floor(v / PATCH_STRIDE) * PATCH_STRIDE;

  for (let ty = first(y0) - PATCH_STRIDE; ty <= y1 + PATCH_STRIDE; ty += PATCH_STRIDE) {
    for (let tx = first(x0) - PATCH_STRIDE; tx <= x1 + PATCH_STRIDE; tx += PATCH_STRIDE) {
      if (tileHash(tx, ty, seed, 91) >= PATCH_CHANCE) continue;
      const frame = Math.floor(tileHash(tx, ty, seed, 92) * patch.frames) % patch.frames;
      // Jittered across most of a stride, or the stains sit on a visible grid.
      const jx = (tileHash(tx, ty, seed, 93) - 0.5) * PATCH_STRIDE * ts * 0.8;
      const jy = (tileHash(tx, ty, seed, 94) - 0.5) * PATCH_STRIDE * ts * 0.8;
      ctx.drawImage(
        patch.image,
        frame * patch.frameWidth, 0, patch.frameWidth, patch.frameHeight,
        Math.round(tx * ts + jx - patch.frameWidth / 2),
        Math.round(ty * ts + jy - patch.frameHeight / 2),
        patch.frameWidth, patch.frameHeight,
      );
    }
  }
}

/**
 * Fallen leaves and twigs, baked flat into the floor.
 *
 * These are the cheapest thing in the whole layer and they do most of the
 * work: a tile of bare soil next to a tile of bare soil is a texture, and the
 * same two tiles with a drift of leaves across the seam is ground.
 */
function paintLitter(
  ctx: CanvasRenderingContext2D,
  world: TileMap,
  atlas: TerrainAtlas,
  { x0, y0, x1, y1 }: TileWindow,
  mask: DecorationMask | null,
): void {
  const ts = world.tileSize;
  const seed = world.seed;

  for (let ty = y0; ty <= y1; ty++) {
    for (let tx = x0; tx <= x1; tx++) {
      const tile = world.tiles[ty][tx];
      // VOID, PROP and LOW are floor with something on top of them, so litter
      // belongs there too — it is what makes the camp exit read as forest
      // floor in shadow rather than as a painted rectangle, and what keeps
      // the dirt under a crate from turning into a wall tile.
      if (tile !== FLOOR && tile !== VOID && tile !== PROP && tile !== LOW) continue;
      if (mask && !mask(tx, ty)) continue;

      const roll = tileHash(tx, ty, seed, 95);
      const sheet =
        roll < LEAVES_CHANCE
          ? atlas.leaves
          : roll < LEAVES_CHANCE + BRANCH_CHANCE
            ? atlas.branch
            : null;
      if (!sheet) continue;

      const frame = Math.floor(tileHash(tx, ty, seed, 96) * sheet.frames) % sheet.frames;
      const jx = (tileHash(tx, ty, seed, 97) - 0.5) * ts * 0.7;
      const jy = (tileHash(tx, ty, seed, 98) - 0.5) * ts * 0.7;
      ctx.drawImage(
        sheet.image,
        frame * sheet.frameWidth, 0, sheet.frameWidth, sheet.frameHeight,
        Math.round(tx * ts + (ts - sheet.frameWidth) / 2 + jx),
        Math.round(ty * ts + (ts - sheet.frameHeight) / 2 + jy),
        sheet.frameWidth, sheet.frameHeight,
      );
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
      const sheet = tile === TREE ? trunkSheet(atlas, tx, ty, seed) : atlas.rock;
      const frame = variant(sheet, tx, ty, seed, tile === TREE ? 2 : 3);

      const baseY = (ty + 1) * ts;
      // Rocks carry their own shadow, baked by `make_textures.py` and shaped to
      // that rock's footprint with the offset the key light implies. A generic
      // ellipse under one would be a second shadow pointing nowhere.
      if (tile !== ROCK) {
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
      }

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

/** One swaying plant, centred on its tile and rooted at the bottom edge. */
function drawPlant(
  ctx: CanvasRenderingContext2D,
  sheet: PropSheet,
  world: TileMap,
  tx: number,
  ty: number,
  time: number,
  amount: number,
  salt: number,
  bodies: DisturbanceField | null,
): void {
  const ts = world.tileSize;
  const seed = world.seed;
  const frame = variant(sheet, tx, ty, seed, salt);
  const jx = (tileHash(tx, ty, seed, salt + 3) - 0.5) * ts * 0.4;
  const lean = sway(tx, ty, seed, time, amount, salt + 5, ts) + bendOf(bodies, tx, ty, ts) * BUSH_PUSH;
  ctx.drawImage(
    sheet.image,
    frame * sheet.frameWidth,
    0,
    sheet.frameWidth,
    sheet.frameHeight,
    Math.round(tx * ts + (ts - sheet.frameWidth) / 2 + jx + lean),
    Math.round((ty + 1) * ts - sheet.frameHeight),
    sheet.frameWidth,
    sheet.frameHeight,
  );
}

function drawTuft(
  ctx: CanvasRenderingContext2D,
  grass: PropSheet,
  world: TileMap,
  tx: number,
  ty: number,
  index: number,
  time: number,
  bodies: DisturbanceField | null,
): void {
  const ts = world.tileSize;
  const seed = world.seed;
  const frame = variant(grass, tx, ty, seed, 20 + index);
  // Jitter inside the tile so tufts do not line up on a lattice.
  const jx = (tileHash(tx, ty, seed, 30 + index) - 0.5) * (ts - grass.frameWidth);
  const jy = (tileHash(tx, ty, seed, 40 + index) - 0.5) * ts * 0.5;
  const lean =
    sway(tx, ty, seed, time, SWAY_GRASS, 60 + index * 2, ts) +
    bendOf(bodies, tx, ty, ts) * GRASS_PUSH;
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
      if (tile !== FLOOR && tile !== VOID && tile !== PROP && tile !== LOW) {
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

function clamp01(value: number): number {
  return value < 0 ? 0 : value > 1 ? 1 : value;
}
