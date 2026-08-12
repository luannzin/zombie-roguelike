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
import { TileLayer } from './layers/tiles';
import { drawVignette } from './layers/vignette';
import { projectionFor } from './projection';
import { palette } from '../theme/palette';
import type { SpriteBook } from './sprites';
import type { RenderState } from './types';

export type { DrawableEntity, RenderState } from './types';

export class Renderer {
  private readonly ctx: CanvasRenderingContext2D;
  private readonly tiles = new TileLayer();

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly book: SpriteBook,
  ) {
    this.ctx = get2d(canvas, 'renderer', { alpha: false });
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

    // World space: map, then dust under everything.
    this.useWorldSpace(view.zoom, view.offsetX, view.offsetY);
    this.tiles.draw(ctx, state.world, state.camera);
    drawDust(ctx, state.effects);

    // Screen space: coins under characters, then entities depth-sorted.
    this.useScreenSpace();
    drawCoinShadows(entity, state.coins);
    drawCoins(entity, state.coins, state.config.coinSprite);
    const ordered = [...state.entities].sort((a, b) => a.y - b.y);
    for (const target of ordered) drawShadow(entity, target);
    for (const target of ordered) drawEntity(entity, target);

    // World space: combat effects draw over entities.
    this.useWorldSpace(view.zoom, view.offsetX, view.offsetY);
    drawCombatEffects(ctx, state.effects, state.config.tileSize);

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
