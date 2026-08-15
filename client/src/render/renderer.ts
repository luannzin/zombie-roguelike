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
import { drawCombatEffects, drawDeathBursts, drawDust, drawTextFloats, drawWindPuffs } from './layers/effects';
import {
  drawCoinShadows,
  drawCoins,
  drawCorpseSprites,
  drawEntity,
  drawNameLabels,
  drawShadow,
  type EntityContext,
} from './layers/entities';
import { drawAlertMarks } from './layers/vision';
import { DisturbanceField } from './disturbance';
import { AtmosphereLayer } from './layers/atmosphere';
import { DarknessLayer } from './layers/darkness';
import { crateAnimFrame, drawFootprints, drawSceneryProp } from './layers/scenery';
import { drawBloodPools } from './layers/corpses';
import {
  chargeHandoff,
  drawRiftGlow,
  drawRiftProp,
  drawRiftScar,
  riftPhase,
  riftStanding,
  RIFT_FALLBACK,
  type RiftStanding,
} from './layers/rift';
import { loadRift, type RiftAtlas } from './rift';
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
import { loadGore, type GoreAtlas } from './gore';
import { loadGuns, type GunAtlas } from './guns';
import { loadLoot, type LootAtlas } from './loot';
import { loadScenery, type SceneryAtlas } from './scenery';
import { loadTerrain } from './terrain';
import { loadVfx, type VfxAtlas } from './vfx';
import type { SpriteBook } from './sprites';
import type { DrawableEntity, RenderState } from './types';
import { HIT_FLASH_LIFE } from '../game/entity-visuals';
import type { SceneryPiece } from '../game/world';

export type { DrawableEntity, RenderState } from './types';

export class Renderer {
  private readonly ctx: CanvasRenderingContext2D;
  private readonly terrain = new TerrainLayer();
  private readonly darkness = new DarknessLayer();
  private readonly atmosphere = new AtmosphereLayer();
  /** Depth-sort scratch — see `draw`. */
  private readonly ordered: DrawableEntity[] = [];
  /**
   * Standing scenery + live crates + smash sheets. Rebuilt every frame so a
   * crate can leave the live list and keep playing its break in the same sort.
   */
  private readonly depthProps: {
    y: number;
    anim: number;
    hitFlash: number;
    /**
     * Exactly one of these is set. Scenery and the rift come out of different
     * atlases and are drawn by different code, but they share one depth order
     * because they share one requirement: a body walking behind either has to
     * disappear behind it.
     */
    piece: SceneryPiece | null;
    rift: RiftStanding | null;
  }[] = [];
  /**
   * What the bodies on screen are doing to the plants around them. Owned here
   * rather than passed in: it is a per-frame consequence of `state.entities`,
   * which the renderer already has, and nothing outside drawing reads it.
   */
  private readonly disturbance = new DisturbanceField();
  private scenery: SceneryAtlas | null = null;
  private lootAtlas: LootAtlas | null = null;
  private gunAtlas: GunAtlas | null = null;
  private vfx: VfxAtlas | null = null;
  private gore: GoreAtlas | null = null;
  private riftAtlas: RiftAtlas | null = null;

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
    void loadGore().then((atlas) => {
      this.gore = atlas;
    });
    void loadGuns().then((atlas) => {
      this.gunAtlas = atlas;
    });
    void loadRift().then((atlas) => {
      this.riftAtlas = atlas;
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
      gore: this.gore,
      guns: this.gunAtlas,
    };

    this.clear();

    // Rebuilt before anything is drawn, because the very first pass reads it:
    // the undergrowth bends around whatever is standing in it this frame.
    this.disturbance.update(state.entities, state.dt);

    // World space: floor, then what is painted ON the floor — boot prints,
    // the blood pools under corpses, and footstep dust.
    this.useWorldSpace(view.zoom, view.offsetX, view.offsetY);
    this.terrain.ground(ctx, state.world, state.camera, state.time, this.disturbance);
    if (this.scenery) {
      drawFootprints(ctx, state.effects, this.scenery, state.camera);
      drawBloodPools(ctx, state.corpses, this.scenery, state.camera);
    }
    // The sigil goes on the floor with them: flat, under everybody, and the
    // only part of the structure that is there before anything happens.
    if (state.world.rift) {
      drawRiftScar(ctx, this.riftAtlas, state.world.rift, state.camera);
    }
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
    drawCorpseSprites(entity, state.corpses);

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
    const depthProps = this.depthProps;
    depthProps.length = 0;
    for (const piece of state.world.scenery.standing) {
      depthProps.push({ y: piece.y, anim: 0, hitFlash: 0, piece, rift: null });
    }
    const rift = state.world.rift;
    const phase = rift
      ? riftPhase(rift, state.config.rift ?? RIFT_FALLBACK, chargeHandoff(this.riftAtlas))
      : null;
    if (rift && phase) {
      for (const piece of riftStanding(rift, phase)) {
        depthProps.push({ y: piece.y, anim: 0, hitFlash: 0, piece: null, rift: piece });
      }
    }
    for (const crate of state.world.crates) {
      depthProps.push({
        y: crate.y,
        anim: 0,
        hitFlash: 0,
        rift: null,
        piece: {
          kind: 'crate',
          x: crate.x,
          y: crate.y,
          variant: crate.variant,
          flip: crate.flip,
        },
      });
    }
    const crateSheet = this.scenery?.props.crate;
    for (const smash of state.effects.crateSmashes) {
      const flash =
        smash.age < HIT_FLASH_LIFE ? 1 - smash.age / HIT_FLASH_LIFE : 0;
      depthProps.push({
        y: smash.y,
        anim: crateSheet ? crateAnimFrame(crateSheet, smash.age) : 0,
        hitFlash: flash,
        rift: null,
        piece: {
          kind: 'crate',
          x: smash.x,
          y: smash.y,
          variant: smash.variant,
          flip: smash.flip,
        },
      });
    }
    depthProps.sort((a, b) => a.y - b.y);

    const foot = state.config.playerHalfHeight;
    let fire = 0;
    let prop = 0;
    const scenery = this.scenery;

    const flushTo = (limit: number): void => {
      for (;;) {
        const fireY = fire < fires.length ? fires[fire].y - foot : Infinity;
        const propY = prop < depthProps.length ? depthProps[prop].y - foot : Infinity;
        const nextY = Math.min(fireY, propY);
        // Both exhausted. Checked before the limit compare because the final
        // flush passes Infinity, and `Infinity > Infinity` is false.
        if (nextY === Infinity) return;
        if (nextY > limit) return;
        if (fireY <= propY) {
          this.terrain.fire(ctx, view, fires[fire], state.time);
          fire++;
        } else {
          const row = depthProps[prop];
          if (row.rift) {
            if (this.riftAtlas) {
              drawRiftProp(ctx, view, this.riftAtlas, row.rift, palette().entity.shadow);
            }
          } else if (scenery && row.piece) {
            drawSceneryProp(
              ctx, view, scenery, row.piece, state.time, row.anim, row.hitFlash,
            );
          }
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
    this.atmosphere.setWeather(state.weather);
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
    drawWindPuffs(ctx, this.vfx?.wind ?? null, state.effects.winds);
    drawDeathBursts(ctx, this.vfx?.death ?? null, state.effects.deaths);
    // The structure's own light, last of the additive passes: the stones'
    // crowns and the anomaly are the brightest things on the map once they are
    // lit, and nothing after this may be drawn under them.
    if (rift && phase) {
      // `scene.beacon` is raw channels — the same triple `drawSceneLights`
      // joins for its gradients. The tint cache wants a CSS colour.
      const beacon = palette().scene.beacon;
      drawRiftGlow(
        ctx, this.riftAtlas, rift, phase,
        `rgb(${beacon[0]} ${beacon[1]} ${beacon[2]})`,
      );
    }
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
