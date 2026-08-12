/**
 * Darkness + lantern glow.
 *
 * Turns the `FovField` into pixels with two blits and no shader.
 *
 * The trick is resolution. Both passes are built at ONE PIXEL PER TILE and then
 * drawn scaled up over the world with smoothing on. Canvas bilinear filtering
 * puts its interpolation nodes at texel centres, which land exactly on tile
 * centres, so the per-tile field becomes a smooth gradient for free — no blur
 * pass, no per-pixel work, and a mask that costs a few thousand bytes.
 *
 *   night   a cold wash whose alpha is the INVERSE of the light. Unseen ground
 *           is dimmed, never blacked out: you can still read the shape of the
 *           map, it is just drained and cold.
 *   warm    an additive amber pass over lit tiles, so the lantern reads as a
 *           light source rather than as a hole in the dark.
 *
 * Explored-but-unlit tiles sit between the two: remembered, colourless, and
 * empty of anything that has moved since you left.
 *
 * On top of those goes a third, unrelated pass: EVENT LIGHTS. A muzzle flash, a
 * death pop, a coin glint — each is a radial gradient added over the darkness,
 * at full canvas resolution rather than per tile, because these are small, brief
 * and the eye is looking straight at them. They are drawn last so a gunshot lights
 * the dark instead of being dimmed by it.
 */

import { createSurface } from '../../lib/canvas';
import { palette } from '../../theme/palette';
import type { PointLight } from '../../game/effects';
import type { TileMap } from '../../game/world';
import type { FovField } from '../fov';

/** Darkness over ground nobody has ever seen. */
const UNSEEN_ALPHA = 0.9;
/** Darkness over ground the team has seen before but cannot see now. */
const FOG_ALPHA = 0.66;
/** Strength of the additive warm light in the brightest part of the beam. */
const WARM_STRENGTH = 0.22;

/**
 * `#rgb` / `#rrggbb` -> `rgb(r g b / a)`. Gradient stops need per-stop alpha,
 * which `globalAlpha` cannot express. Non-hex input is passed through with the
 * alpha applied as a channel, which the browser will reject loudly rather than
 * silently painting the wrong colour.
 */
function withAlpha(color: string, alpha: number): string {
  const hex = color.trim();
  if (hex.startsWith('#')) {
    const body = hex.slice(1);
    const full =
      body.length === 3
        ? body
            .split('')
            .map((c) => c + c)
            .join('')
        : body;
    const value = parseInt(full, 16);
    const r = (value >> 16) & 255;
    const g = (value >> 8) & 255;
    const b = value & 255;
    return `rgb(${r} ${g} ${b} / ${alpha})`;
  }
  return color;
}

export class DarknessLayer {
  private night: HTMLCanvasElement | null = null;
  private nightCtx: CanvasRenderingContext2D | null = null;
  private nightData: ImageData | null = null;
  private warm: HTMLCanvasElement | null = null;
  private warmCtx: CanvasRenderingContext2D | null = null;
  private warmData: ImageData | null = null;
  private width = 0;
  private height = 0;

  /**
   * Additive event lights, in world space, over everything else.
   *
   * Each fades on a sharp attack / slow release curve — a flash that fades
   * linearly reads as a fading lamp, not as a bang.
   */
  drawLights(ctx: CanvasRenderingContext2D, lights: readonly PointLight[]): void {
    if (lights.length === 0) return;

    ctx.globalCompositeOperation = 'lighter';
    for (const light of lights) {
      const remaining = 1 - light.age / light.life;
      if (remaining <= 0) continue;
      const intensity = light.strength * remaining * remaining;

      const gradient = ctx.createRadialGradient(light.x, light.y, 0, light.x, light.y, light.radius);
      gradient.addColorStop(0, withAlpha(light.color, intensity));
      gradient.addColorStop(0.45, withAlpha(light.color, intensity * 0.34));
      gradient.addColorStop(1, withAlpha(light.color, 0));
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(light.x, light.y, light.radius, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalCompositeOperation = 'source-over';
  }

  /** Caller must have applied the world-space transform. */
  draw(ctx: CanvasRenderingContext2D, world: TileMap, fov: FovField): void {
    this.resize(fov.width, fov.height);
    const night = this.nightCtx;
    const warm = this.warmCtx;
    if (!night || !warm || !this.nightData || !this.warmData || !this.night || !this.warm) return;

    const [shadowR, shadowG, shadowB] = palette().night.shadow;
    const [warmR, warmG, warmB] = palette().night.lantern;
    const nightPixels = this.nightData.data;
    const warmPixels = this.warmData.data;

    for (let i = 0; i < fov.light.length; i++) {
      const lit = fov.light[i];
      const base = fov.explored[i] === 1 ? FOG_ALPHA : UNSEEN_ALPHA;
      const offset = i * 4;

      nightPixels[offset] = shadowR;
      nightPixels[offset + 1] = shadowG;
      nightPixels[offset + 2] = shadowB;
      nightPixels[offset + 3] = Math.round(base * (1 - lit) * 255);

      warmPixels[offset] = warmR;
      warmPixels[offset + 1] = warmG;
      warmPixels[offset + 2] = warmB;
      warmPixels[offset + 3] = Math.round(lit * WARM_STRENGTH * 255);
    }

    night.putImageData(this.nightData, 0, 0);
    warm.putImageData(this.warmData, 0, 0);

    const smoothing = ctx.imageSmoothingEnabled;
    ctx.imageSmoothingEnabled = true;

    ctx.drawImage(this.night, 0, 0, world.pixelWidth, world.pixelHeight);
    ctx.globalCompositeOperation = 'lighter';
    ctx.drawImage(this.warm, 0, 0, world.pixelWidth, world.pixelHeight);
    ctx.globalCompositeOperation = 'source-over';

    ctx.imageSmoothingEnabled = smoothing;
  }

  /** Release the mask surfaces. */
  reset(): void {
    this.night = this.warm = null;
    this.nightCtx = this.warmCtx = null;
    this.nightData = this.warmData = null;
    this.width = this.height = 0;
  }

  private resize(width: number, height: number): void {
    if (this.width === width && this.height === height && this.night) return;
    const night = createSurface(width, height, 'darkness/night');
    const warm = createSurface(width, height, 'darkness/warm');
    this.night = night.canvas;
    this.nightCtx = night.ctx;
    this.nightData = night.ctx.createImageData(width, height);
    this.warm = warm.canvas;
    this.warmCtx = warm.ctx;
    this.warmData = warm.ctx.createImageData(width, height);
    this.width = width;
    this.height = height;
  }
}
