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
import { AtmosphereLayer } from './layers/atmosphere';
import { DarknessLayer } from './layers/darkness';
import { TerrainLayer } from './layers/terrain';
import { drawVignette } from './layers/vignette';
import { projectionFor } from './projection';
import { palette } from '../theme/palette';
import { loadTerrain } from './terrain';
import type { SpriteBook } from './sprites';
import type { RenderState } from './types';

export type { DrawableEntity, RenderState } from './types';

export class Renderer {
  private readonly ctx: CanvasRenderingContext2D;
  private readonly terrain = new TerrainLayer();
  private readonly darkness = new DarknessLayer();
  private readonly atmosphere = new AtmosphereLayer();

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly book: SpriteBook,
  ) {
    this.ctx = get2d(canvas, 'renderer', { alpha: false });
    // Fire-and-forget: until the atlas lands the terrain layer paints flat
    // colours, so the first frames are plain rather than blank.
    void loadTerrain().then((atlas) => this.terrain.setAtlas(atlas));
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

    // World space: floor, swaying undergrowth, props, then footstep dust.
    this.useWorldSpace(view.zoom, view.offsetX, view.offsetY);
    this.terrain.ground(ctx, state.world, state.camera, state.time);
    drawDust(ctx, state.effects);

    // Screen space: coins under characters, then entities depth-sorted.
    this.useScreenSpace();
    drawCoinShadows(entity, state.coins);
    drawCoins(entity, state.coins, state.config.coinSprite);
    const ordered = [...state.entities].sort((a, b) => a.y - b.y);
    for (const target of ordered) drawShadow(entity, target);
    for (const target of ordered) drawEntity(entity, target);

    // World space again, and the order here IS the atmosphere:
    //   overgrowth  canopies and ferns close over whoever is standing behind
    //               them, which is where a flat 2D scene gains depth
    //   atmosphere  motes go under the darkness so they only show up where
    //               there is light to catch them
    //   darkness    dims everything the team cannot see
    //   effects     tracers, slashes and event lights go OVER the darkness: a
    //               muzzle flash is a light source, not a thing being lit
    this.useWorldSpace(view.zoom, view.offsetX, view.offsetY);
    this.terrain.overgrowth(ctx, state.world, state.camera, state.time);
    this.atmosphere.draw(ctx, state.camera, state.dt);
    if (state.fov) this.darkness.draw(ctx, state.world, state.fov);
    drawCombatEffects(ctx, state.effects, state.config.tileSize);
    this.darkness.drawLights(ctx, state.effects.lights);

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
