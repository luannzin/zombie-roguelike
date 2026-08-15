/**
 * Canvas 2D renderer.
 *
 * Consumes a plain RenderState snapshot and draws it. It never touches the
 * network, never mutates game state, and holds no gameplay logic — players and
 * enemies arrive in one `entities` list and are drawn by one path.
 *
 * This file only sequences passes and owns the transform between world space
 * and screen space. The drawing itself lives in `layers/`.
 */

import { get2d } from '../lib/canvas';
import { drawCombatEffects, drawDust, drawTextFloats } from './layers/effects';
import {
  drawCoinShadows,
  drawCoins,
  drawEntity,
  drawNameLabels,
  drawShadow,
  type EntityContext,
} from './layers/entities';
import { drawAlertMarks } from './layers/vision';
import { DisturbanceField } from './disturbance';
import { AtmosphereLayer } from './layers/atmosphere';
import { DarknessLayer } from './layers/darkness';
import { drawFootprints, drawSceneryProp } from './layers/scenery';
import {
  drawLootAuras,
  drawLootBeams,
  drawLootMotes,
  drawLootShadows,
  drawLootSprites,
} from './layers/loot';
import { TerrainLayer, type DecorationMask } from './layers/terrain';
import { drawVignette } from './layers/vignette';
import { projectionFor } from './projection';
import { palette } from '../theme/palette';
import { loadLoot, type LootAtlas } from './loot';
import { loadScenery, type SceneryAtlas } from './scenery';
import { loadTerrain } from './terrain';
import { loadVfx, type VfxAtlas } from './vfx';
import type { SpriteBook } from './sprites';
import type { DrawableEntity, RenderState } from './types';

export type { DrawableEntity, RenderState } from './types';

export class Renderer {
  private readonly ctx: CanvasRenderingContext2D;
  private readonly terrain = new TerrainLayer();
  private readonly darkness = new DarknessLayer();
  private readonly atmosphere = new AtmosphereLayer();
  /** Depth-sort scratch — see `draw`. */
  private readonly ordered: DrawableEntity[] = [];
  /**
   * What the bodies on screen are doing to the plants around them. Owned here
   * rather than passed in: it is a per-frame consequence of `state.entities`,
   * which the renderer already has, and nothing outside drawing reads it.
   */
  private readonly disturbance = new DisturbanceField();
  private scenery: SceneryAtlas | null = null;
  private lootAtlas: LootAtlas | null = null;
  private vfx: VfxAtlas | null = null;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly book: SpriteBook,
  ) {
    this.ctx = get2d(canvas, 'renderer', { alpha: false });
    // Fire-and-forget: until the atlases land the terrain layer paints flat
    // colours and no scenery is drawn, so the first frames are plain rather
    // than blank. The scenery atlas goes to the terrain layer as well as being
    // held here, because its FLAT half is baked into the ground canvas.
    void loadTerrain().then((atlas) => this.terrain.setAtlas(atlas));
    void loadScenery().then((atlas) => {
      this.scenery = atlas;
      this.terrain.setSceneryAtlas(atlas);
    });
    void loadLoot().then((atlas) => {
      this.lootAtlas = atlas;
    });
    void loadVfx().then((atlas) => {
      this.vfx = atlas;
    });
  }

  /**
   * Keep grass and ferns off some tiles. Null (the default) allows them
   * everywhere, which is what a forest wants; the camp passes a hearth mask so
   * nothing grows where the party is standing. See `layers/terrain.ts`.
   */
  setDecorationMask(mask: DecorationMask | null): void {
    this.terrain.setDecorationMask(mask);
  }

  /** Call only when the canvas element actually changed size (see ResizeObserver). */
  resize(): void {
    const width = Math.max(1, Math.floor(this.canvas.clientWidth));
    const height = Math.max(1, Math.floor(this.canvas.clientHeight));
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
    this.ctx.imageSmoothingEnabled = false;
  }

  /** Release cached bitmaps. Safe to call more than once. */
  dispose(): void {
    this.terrain.reset();
    this.darkness.reset();
    this.atmosphere.reset();
    this.disturbance.clear();
    this.book.clearTints();
  }

  draw(state: RenderState): void {
    const { ctx } = this;
    const view = projectionFor(state.camera);
    const entity: EntityContext = {
      ctx,
      view,
      config: state.config,
      book: this.book,
    };

    this.clear();

    // Rebuilt before anything is drawn, because the very first pass reads it:
    // the undergrowth bends around whatever is standing in it this frame.
    this.disturbance.update(state.entities, state.dt);

    // World space: floor, then what is painted ON the floor — boot prints
    // and footstep dust.
    this.useWorldSpace(view.zoom, view.offsetX, view.offsetY);
    this.terrain.ground(ctx, state.world, state.camera, state.time, this.disturbance);
    if (this.scenery) drawFootprints(ctx, state.effects, this.scenery, state.camera);
    drawDust(ctx, state.effects);

    // Screen space: coins under characters, then everything that STANDS on the
    // ground, depth-sorted together. Bonfires are in that sort rather than in
    // the terrain bake because a player on the near side of a fire has to
    // overlap the flame and one behind it has to be hidden by it — drawn as
    // scenery, the fire would flatten the party into a row of characters
    // standing in front of a picture of a fire.
    this.useScreenSpace();
    drawCoinShadows(entity, state.coins);
    drawCoins(entity, state.coins, state.config.coinSprite);
    drawLootShadows(ctx, view, state.loot);
    drawLootSprites(ctx, view, this.lootAtlas, state.loot);

    // Scratch array, reused every frame: this list is rebuilt and re-sorted
    // 60 times a second and none of it outlives the call.
    const ordered = this.ordered;
    ordered.length = 0;
    for (const target of state.entities) ordered.push(target);
    ordered.sort((a, b) => a.y - b.y);
    for (const target of ordered) drawShadow(entity, target);

    // Bonfires and standing scenery are MERGED into the same depth order
    // rather than sorted with it. Both are already in ascending y and both are
    // anchored on a contact point where an entity's `y` is a box centre, so
    // each is sorted as if it were a body whose feet are at its base. A cabin
    // has to hide whoever walks behind it and be hidden by whoever walks in
    // front, which is the same requirement the fire has and the same answer.
    const fires = state.world.fires;
    const standing = state.world.scenery.standing;
    const foot = state.config.playerHalfHeight;
    let fire = 0;
    let prop = 0;
    const scenery = this.scenery;

    const flushTo = (limit: number): void => {
      for (;;) {
        const fireY = fire < fires.length ? fires[fire].y - foot : Infinity;
        const propY = prop < standing.length ? standing[prop].y - foot : Infinity;
        const nextY = Math.min(fireY, propY);
        // Both exhausted. Checked before the limit compare because the final
        // flush passes Infinity, and `Infinity > Infinity` is false.
        if (nextY === Infinity) return;
        if (nextY > limit) return;
        if (fireY <= propY) {
          this.terrain.fire(ctx, view, fires[fire], state.time);
          fire++;
        } else {
          if (scenery) drawSceneryProp(ctx, view, scenery, standing[prop], state.time);
          prop++;
        }
      }
    };

    for (const target of ordered) {
      flushTo(target.y);
      drawEntity(entity, target);
    }
    flushTo(Infinity);

    // World space again, and the order here IS the atmosphere:
    //   overgrowth  canopies and ferns close over whoever is standing behind
    //               them, which is where a flat 2D scene gains depth
    //   atmosphere  motes go under the darkness so they only show up where
    //               there is light to catch them
    //   darkness    dims everything the team cannot see
    //   effects     tracers, slashes and event lights go OVER the darkness: a
    //               muzzle flash is a light source, not a thing being lit
    this.useWorldSpace(view.zoom, view.offsetX, view.offsetY);
    this.terrain.overgrowth(ctx, state.world, state.camera, state.time, this.disturbance);
    this.atmosphere.draw(ctx, state.camera, state.dt);
    if (state.fov) this.darkness.draw(ctx, state.world, state.fov);
    this.darkness.drawFires(
      ctx,
      state.world.fires,
      state.world.tileSize,
      state.config.campfireLightTiles,
      state.time,
    );
    this.darkness.drawSceneLights(
      ctx,
      state.world.scenery.lights,
      state.world.tileSize,
      state.time,
    );
    drawCombatEffects(ctx, state.effects, state.config.tileSize);
    this.darkness.drawLights(ctx, state.effects.lights);
    drawLootAuras(ctx, state.loot, state.time);
    drawLootMotes(ctx, state.loot, state.time, state.config.tileSize);
    drawLootBeams(ctx, this.vfx?.aura ?? null, state.loot, state.time);
    // Hunt tell sits ON the night: a hunter you cannot see still wears the
    // diamond, so killing the lamp does not hide that it has you.
    drawAlertMarks(entity, state.entities, state.time);

    // Screen space: labels, numbers, then the full-screen vignette.
    this.useScreenSpace();
    drawNameLabels(entity, state.entities);
    drawTextFloats(ctx, state.effects, view);
    drawVignette(ctx, this.canvas.width, this.canvas.height, state.danger, state.time);
  }

  private clear(): void {
    const { ctx } = this;
    this.useScreenSpace();
    ctx.fillStyle = palette().surface;
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
  }

  private useScreenSpace(): void {
    this.ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.ctx.imageSmoothingEnabled = false;
  }

  private useWorldSpace(zoom: number, offsetX: number, offsetY: number): void {
    this.ctx.setTransform(zoom, 0, 0, zoom, offsetX, offsetY);
  }
}
