/**
 * Canvas 2D renderer.
 *
 * Consumes a plain RenderState snapshot and draws it. It never touches the
 * network, never mutates game state, and holds no gameplay logic — swapping
 * renderers (or adding zombies to `players`) requires no changes elsewhere.
 *
 * This file only sequences passes and owns the transform between world space
 * and screen space. The drawing itself lives in `layers/`.
 */

import { get2d } from '../lib/canvas';
import { drawCombatEffects, drawDamageFloats, drawDust } from './layers/effects';
import { drawNameLabels, drawPlayer, drawShadow, type EntityContext } from './layers/entities';
import { TileLayer } from './layers/tiles';
import { drawVignette } from './layers/vignette';
import { projectionFor } from './projection';
import { palette } from '../theme/palette';
import { TintCache, type SpriteSheet } from './sprites';
import type { RenderState } from './types';

export type { DrawablePlayer, RenderState } from './types';

export class Renderer {
  private readonly ctx: CanvasRenderingContext2D;
  private readonly tints: TintCache;
  private readonly tiles = new TileLayer();

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly sheet: SpriteSheet,
  ) {
    this.ctx = get2d(canvas, 'renderer', { alpha: false });
    this.tints = new TintCache(sheet);
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
    this.tiles.reset();
    this.tints.clear();
  }

  draw(state: RenderState): void {
    const { ctx } = this;
    const view = projectionFor(state.camera);
    const entity: EntityContext = {
      ctx,
      view,
      config: state.config,
      sheet: this.sheet,
      tints: this.tints,
    };

    this.clear();

    // World space: map, then dust under everything.
    this.useWorldSpace(view.zoom, view.offsetX, view.offsetY);
    this.tiles.draw(ctx, state.world, state.camera);
    drawDust(ctx, state.effects);

    // Screen space: entities, pixel-exact. Painter's order by depth.
    this.useScreenSpace();
    const ordered = [...state.players].sort((a, b) => a.y - b.y);
    for (const player of ordered) drawShadow(entity, player);
    for (const player of ordered) drawPlayer(entity, player);

    // World space: combat effects draw over entities.
    this.useWorldSpace(view.zoom, view.offsetX, view.offsetY);
    drawCombatEffects(ctx, state.effects, state.config.tileSize);

    // Screen space: labels, numbers, then the full-screen vignette.
    this.useScreenSpace();
    drawNameLabels(entity, state.players);
    drawDamageFloats(ctx, state.effects, view);
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
