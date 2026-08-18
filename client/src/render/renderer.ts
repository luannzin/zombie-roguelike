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
  drawEgressFire,
  drawEgressGround,
  drawRiftAir,
  drawRiftFire,
  drawRiftGlow,
  drawRiftGround,
  drawRiftProp,
  egressTorches,
  riftPhase,
  riftStanding,
  RIFT_FALLBACK,
  type RiftPhase,
  type RiftStanding,
} from './layers/rift';
import { loadRift, type RiftAtlas } from './rift';
import { loadPlatform, type PlatformAtlas } from './platform';
import {
  drawLootAuras,
  drawLootBeams,
  drawLootMotes,
  drawLootShadows,
  drawLootPops,
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
import { loadMerchant, type MerchantAtlas } from './merchant';
import { loadStore, type StoreAtlas } from './store';
import {
  drawStoreFloor,
  drawStoreLight,
  drawStorePrices,
  drawStoreProp,
  storeStanding,
  type StoreStanding,
} from './layers/store';
import { loadTerrain } from './terrain';
import { loadVfx, type VfxAtlas } from './vfx';
import type { SpriteBook } from './sprites';
import type { DrawableEntity, RenderState } from './types';
import { HIT_FLASH_LIFE } from '../game/entity-visuals';
import type { SceneryPiece, TileMap } from '../game/world';

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
    store: StoreStanding | null;
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
  private platformAtlas: PlatformAtlas | null = null;
  private storeAtlas: StoreAtlas | null = null;
  private merchantAtlas: MerchantAtlas | null = null;

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
    void loadPlatform().then((atlas) => {
      this.platformAtlas = atlas;
    });
    void loadStore().then((atlas) => {
      this.storeAtlas = atlas;
    });
    void loadMerchant().then((atlas) => {
      this.merchantAtlas = atlas;
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

  /**
   * What every extraction rig is doing this frame.
   *
   * Computed once and read by FOUR passes — the imprint on the floor, the
   * depth sort, the air pass and the additive light — which are spread across
   * the whole frame. Recomputing it in each would be cheap arithmetic and
   * still wrong: the shudder is keyed off wall time, so two calls a frame
   * would put the skid's sprite and the shadow under it in different places.
   */
  private riftPhasesFor(state: RenderState): { rift: NonNullable<RenderState['world']['rifts'][number]>; phase: RiftPhase }[] {
    const timing = state.config.rift ?? RIFT_FALLBACK;
    return state.world.rifts.map((rift) => ({
      rift,
      phase: riftPhase(rift, timing, this.platformAtlas, state.time),
    }));
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

  /**
   * Tiles just changed (the forest swallowing the arrival corridor). Stamp
   * new trunks into the prop bake and drop the VOID crush so the ribbon
   * recedes with the path.
   */
  stampTiles(world: TileMap, tiles: ReadonlyArray<[number, number, number]>): void {
    this.terrain.stampProps(world, tiles);
    this.darkness.invalidatePath();
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

    // The merchant's camp, or null everywhere else. There is no floor pass for
    // it: the clearing is forest, painted by the terrain layer like any other.
    const store = state.store;

    // World space: floor, then what is painted ON the floor — boot prints,
    // the blood pools under corpses, and footstep dust.
    this.useWorldSpace(view.zoom, view.offsetX, view.offsetY);
    this.terrain.ground(ctx, state.world, state.camera, state.time, this.disturbance);
    // The mat goes down with the boot prints: flat, under everybody.
    drawStoreFloor(ctx, this.storeAtlas, store);
    if (this.scenery) {
      drawFootprints(ctx, state.effects, this.scenery, state.camera);
      drawBloodPools(ctx, state.corpses, this.scenery, state.camera);
    }
    // The hole an extraction platform leaves goes on the floor with them:
    // flat, under everybody, and revealed on the frame the skid comes free
    // rather than shipped with the map. Until then there is nothing here —
    // the ground under a platform is the platform's.
    const riftPhases = this.riftPhasesFor(state);
    for (const { rift, phase } of riftPhases) {
      drawRiftGround(ctx, this.platformAtlas, rift, phase, state.camera);
    }
    // The threshold's paving, with the imprint and the boot prints — it is a
    // mark on the floor and belongs in the same pass they do.
    drawEgressGround(ctx, this.riftAtlas, state.world, state.camera);
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
    // The item jumping out of something that was just opened. AFTER the
    // ground drops and before the bodies, so it passes over the drop it is
    // about to become and still goes behind anyone standing in front of it.
    drawLootPops(
      ctx,
      view,
      this.lootAtlas,
      state.effects.lootPops,
      (key) => state.config.loot?.[key]?.frame ?? null,
    );
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
      depthProps.push({ y: piece.y, anim: 0, hitFlash: 0, piece, rift: null, store: null });
    }
    for (const { rift, phase } of riftPhases) {
      for (const piece of riftStanding(rift, phase)) {
        depthProps.push({ y: piece.y, anim: 0, hitFlash: 0, piece: null, rift: piece, store: null });
      }
    }
    for (const piece of egressTorches(state.world.egress)) {
      depthProps.push({ y: piece.y, anim: 0, hitFlash: 0, piece: null, rift: piece, store: null });
    }
    // The tables and the merchant. In the sort for the reason everything else
    // is: a player walking behind a stall has to disappear behind it, and the
    // merchant is a body standing on a floor like any other.
    for (const piece of storeStanding(store)) {
      depthProps.push({ y: piece.y, anim: 0, hitFlash: 0, piece: null, rift: null, store: piece });
    }
    // Live objects. `sheet` was resolved when the row was unpacked (see
    // `game/objects.ts`), so a bus and a barrel reach the same depth sort
    // without this loop knowing that either of them exists.
    for (const crate of state.world.crates) {
      // An opened object plays its own sheet from the moment it was used and
      // then HOLDS the last frame — a lid standing up, a boot swung open. The
      // clamp in `crateAnimFrame` is what makes one expression serve both the
      // object that was just opened and the one that was opened five minutes
      // ago, or before this client even joined.
      const openSheet = crate.opened ? this.scenery?.props[crate.sheet] : null;
      depthProps.push({
        y: crate.y,
        anim: openSheet ? crateAnimFrame(openSheet, state.time - crate.openedAt) : 0,
        hitFlash: 0,
        rift: null,
        store: null,
        piece: {
          kind: crate.sheet,
          x: crate.x,
          y: crate.y,
          variant: crate.variant,
          flip: crate.flip,
        },
      });
    }
    // Objects that are already gone from that list and are still playing.
    // They keep their own `sheet` for exactly that reason.
    for (const smash of state.effects.crateSmashes) {
      // Sheet-less one-shots are the object's own dust: the sprite is being
      // animated by the live object itself (see `Game.onCrateBreak`), so
      // there is nothing to draw here.
      if (!smash.sheet) continue;
      const sheet = this.scenery?.props[smash.sheet];
      const flash =
        smash.age < HIT_FLASH_LIFE ? 1 - smash.age / HIT_FLASH_LIFE : 0;
      depthProps.push({
        y: smash.y,
        anim: sheet ? crateAnimFrame(sheet, smash.age) : 0,
        hitFlash: flash,
        rift: null,
        store: null,
        piece: {
          kind: smash.sheet,
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
    // Authored server-side beside the reach that answers E, so the gun never
    // rises at a distance where the key does nothing.
    const storeLift = (state.config.storeLiftTiles ?? 0.4) * state.world.tileSize;

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
            drawRiftProp(
              ctx, view, this.riftAtlas, this.platformAtlas, row.rift,
              palette().entity.shadow, this.lootAtlas,
            );
          } else if (row.store) {
            if (this.storeAtlas && store) {
              drawStoreProp(
                ctx, view, this.storeAtlas, this.gunAtlas, this.merchantAtlas,
                row.store, store, storeLift,
              );
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

    // The rigging and whatever is hanging off it. AFTER the depth sort and
    // still in screen space: nothing standing on the floor can plausibly be in
    // front of a machine hovering over it, and a rope between two points in
    // the air has no contact row to be sorted by. Before the darkness, so a
    // platform twenty tiles up dissolves into the night instead of staying
    // crisp and bright over a blacked-out forest.
    for (const { rift, phase } of riftPhases) {
      drawRiftAir(
        ctx, view, phase, this.platformAtlas, palette().entity.shadow,
        rift.id, this.lootAtlas,
      );
    }

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
    // Every torch on the map, the exit's and the pads'. Before the rigs,
    // because a platform under power is the brighter thing and should sit over
    // them — and once every pad has flown these are the only fire left burning
    // anyway.
    drawEgressFire(ctx, this.riftAtlas, state.world.egress, state.time);
    drawRiftFire(ctx, this.riftAtlas, state.world.rifts, state.time);
    // The rigs' own light, last of the additive passes: rotor wash, the burst
    // and four sets of nav lights are the brightest things on the map once a
    // platform is running, and nothing after this may be drawn under them.
    if (riftPhases.length > 0) {
      const beacon = palette().scene.beacon;
      const beaconCss = `rgb(${beacon[0]} ${beacon[1]} ${beacon[2]})`;
      for (const { rift, phase } of riftPhases) {
        drawRiftGlow(
          ctx, rift, phase, this.riftAtlas, this.platformAtlas,
          beaconCss, state.world.tileSize, state.time,
        );
      }
    }
    // The lamps burning, and the pool under the weapon E is offering.
    drawStoreLight(ctx, this.storeAtlas, store, state.time);
    // Hunt tell sits ON the night: a hunter you cannot see still wears the
    // diamond, so killing the lamp does not hide that it has you.
    drawAlertMarks(entity, state.entities, state.time);

    // Screen space: labels, numbers, then the full-screen vignette.
    this.useScreenSpace();
    drawNameLabels(entity, state.entities);
    // Prices go with the labels: what a thing costs is the shop talking to
    // you, not an object in the room, so nothing in the room may cover it.
    drawStorePrices(ctx, view, this.storeAtlas, store, state.balance);
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
