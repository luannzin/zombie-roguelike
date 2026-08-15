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
 *   warm    an additive amber pass driven by the fov's HEAT, so the lantern
 *           reads as a light source rather than as a hole in the dark.
 *
 * The warm pass is deliberately not a copy of the night pass. Night uses
 * `light`, which saturates: everything within a couple of tiles is equally
 * visible. Warm uses `heat`, which does not, so the ground the player is
 * standing on glows hot while the far end of the same beam is a pale wash —
 * that difference is the whole reason the lantern reads as a lamp being
 * carried rather than as a flashlight texture pasted on the floor.
 *
 * Explored-but-unlit tiles sit between the two: remembered, colourless, and
 * empty of anything that has moved since you left.
 *
 * VOID is a winding path of forest floor between trees. Darkness is a
 * falloff around those tiles, not a rectangle of them: the night pass
 * crushes the path and a couple of tiles of woods beside it, and the warm
 * pass dies along the same ribbon, so leaked firelight never turns the
 * mouth into a hallway. The ground under that shadow is still the atlas.
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
import { VOID, type FirePlace, type SceneryLight, type TileMap } from '../../game/world';
import { fireFlicker } from '../fov';
import type { FovField } from '../fov';

/** Kind index of a steady lamp — see `server/app/scenery.py`. */
const LIGHT_LAMP = 0;

/** Darkness over ground nobody has ever seen. */
const UNSEEN_ALPHA = 0.9;
/** Darkness over ground the team has seen before but cannot see now. */
const FOG_ALPHA = 0.66;
/**
 * How dark the path itself goes. Even a little leaked firelight is crushed
 * so the gap between the trees reads as deep woods, not as a lit hallway.
 */
const VOID_NIGHT = 0.96;
/** How much light is allowed to punch through VOID_NIGHT. Tiny on purpose. */
const VOID_LIGHT_LEAK = 0.12;
/** How far, in tiles, the path's darkness bleeds into the woods around it. */
const VOID_CRUSH_REACH = 2.3;
/**
 * Amber per unit of heat. Heat runs past 1 close to the lamp, so this is the
 * slope of the warm pass and not its ceiling — the alpha is clamped instead.
 */
const WARM_GAIN = 0.27;

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
  /** Next draw rebuilds the whole mask: fresh surfaces, or a new palette. */
  private stale = true;
  /** Last shadow red channel drawn with — cheap "did the tokens change". */
  private tone = -1;
  /** 0..1 falloff around VOID. Rebuilt when the map identity changes. */
  private pathCrush: Float32Array | null = null;
  private crushFor: TileMap | null = null;

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

  /**
   * The warm pool a bonfire throws on the ground it is standing on.
   *
   * The fov already made the camp VISIBLE (see its light sources) — this is the
   * part that makes it look burnt rather than merely lit: a soft additive disc
   * that breathes on the same flicker the sprite's own frames do, so the ground,
   * the flame and the shadows on the party are all moving together. Drawn over
   * the darkness, like every other light in this file.
   *
   * Caller must have applied the world-space transform.
   */
  drawFires(
    ctx: CanvasRenderingContext2D,
    fires: readonly FirePlace[],
    tileSize: number,
    reachTiles: number,
    time: number,
  ): void {
    if (fires.length === 0) return;
    const glow = palette().fire.glow.join(' ');

    ctx.globalCompositeOperation = 'lighter';
    for (let i = 0; i < fires.length; i++) {
      const fire = fires[i];
      const flicker = fireFlicker(time, i);
      const radius = tileSize * reachTiles * (0.55 + flicker * 0.12);
      // Lifted off the ground line: the light comes from the flame, not from
      // the ashes it is sitting in.
      const cy = fire.y - tileSize * 0.55;
      const gradient = ctx.createRadialGradient(fire.x, cy, 1, fire.x, cy, radius);
      gradient.addColorStop(0, `rgb(${glow} / ${(0.3 * flicker).toFixed(3)})`);
      gradient.addColorStop(0.4, `rgb(${glow} / ${(0.11 * flicker).toFixed(3)})`);
      gradient.addColorStop(1, `rgb(${glow} / 0)`);
      ctx.fillStyle = gradient;
      ctx.fillRect(fire.x - radius, cy - radius, radius * 2, radius * 2);
    }
    ctx.globalCompositeOperation = 'source-over';
  }

  /**
   * The glow around lights the MAP owns — a lamp left burning at a cabin door,
   * embers in a camp that has only just gone out.
   *
   * Same pass and same rules as `drawFires`, and deliberately so: a light is a
   * light, and the moment the forest's lights are drawn by different code from
   * the camp's they start looking like a different kind of object. What differs
   * is only the TONE and the beat — a lamp is pale and nearly steady, embers
   * are deep and breathe slowly, and neither may look as warm as a bonfire,
   * because the camp's fire is the warmest thing in the game and everything
   * out in the woods is a colder imitation of it.
   *
   * Caller must have applied the world-space transform.
   */
  drawSceneLights(
    ctx: CanvasRenderingContext2D,
    lights: readonly SceneryLight[],
    tileSize: number,
    time: number,
  ): void {
    if (lights.length === 0) return;
    const tones = palette().scene;
    const table = [tones.lamp, tones.ember, tones.beacon];

    ctx.globalCompositeOperation = 'lighter';
    for (let i = 0; i < lights.length; i++) {
      const light = lights[i];
      const tone = (table[light.kind] ?? tones.lamp).join(' ');
      // A lamp barely moves; embers pulse. Phase is per-light so two of them on
      // screen never breathe together.
      const steady = light.kind === LIGHT_LAMP;
      const beat = 0.5 + 0.5 * Math.sin(time * (steady ? 1.7 : 0.9) + i * 2.4);
      const pulse = steady ? 0.9 + beat * 0.1 : 0.62 + beat * 0.38;
      const radius = tileSize * light.radiusTiles * (0.62 + pulse * 0.14);
      const gradient = ctx.createRadialGradient(light.x, light.y, 1, light.x, light.y, radius);
      gradient.addColorStop(0, `rgb(${tone} / ${(0.26 * pulse).toFixed(3)})`);
      gradient.addColorStop(0.4, `rgb(${tone} / ${(0.09 * pulse).toFixed(3)})`);
      gradient.addColorStop(1, `rgb(${tone} / 0)`);
      ctx.fillStyle = gradient;
      ctx.fillRect(light.x - radius, light.y - radius, radius * 2, radius * 2);
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

    const crush = this.ensurePathCrush(world);
    const onPath = crush.length === fov.light.length;

    // Only the tiles the fov says changed. Both surfaces are retained, so
    // everything outside the box is already correct from an earlier frame —
    // see `FovField.dirty`. A colour change (a token edited in dev) is the one
    // thing the box cannot know about, so it forces a full pass.
    if (shadowR !== this.tone) {
      this.tone = shadowR;
      this.stale = true;
    }
    const box = this.stale
      ? { x0: 0, y0: 0, x1: fov.width - 1, y1: fov.height - 1 }
      : fov.dirty;
    this.stale = false;

    for (let ty = box.y0; ty <= box.y1; ty++) {
      const row = ty * fov.width;
      for (let tx = box.x0; tx <= box.x1; tx++) {
        const i = row + tx;
        const lit = fov.light[i];
        const path = onPath ? crush[i] : 0;
        const fog = fov.explored[i] === 1 ? FOG_ALPHA : UNSEEN_ALPHA;
        const base = fog + (VOID_NIGHT - fog) * path;
        const leak = 1 - (1 - VOID_LIGHT_LEAK) * path;
        const offset = i * 4;

        nightPixels[offset] = shadowR;
        nightPixels[offset + 1] = shadowG;
        nightPixels[offset + 2] = shadowB;
        nightPixels[offset + 3] = Math.round(base * (1 - lit * leak) * 255);

        warmPixels[offset] = warmR;
        warmPixels[offset + 1] = warmG;
        warmPixels[offset + 2] = warmB;
        warmPixels[offset + 3] = Math.min(
          255,
          Math.round(fov.heat[i] * WARM_GAIN * (1 - path) * 255),
        );
      }
    }

    const boxW = box.x1 - box.x0 + 1;
    const boxH = box.y1 - box.y0 + 1;
    if (boxW > 0 && boxH > 0) {
      night.putImageData(this.nightData, 0, 0, box.x0, box.y0, boxW, boxH);
      warm.putImageData(this.warmData, 0, 0, box.x0, box.y0, boxW, boxH);
    }

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
    this.pathCrush = null;
    this.crushFor = null;
    this.width = this.height = 0;
    this.stale = true;
  }

  /**
   * How much of the exit's darkness sits on each tile. VOID is 1; woods
   * within VOID_CRUSH_REACH fall off with a smoothstep, so the path reads
   * as a ribbon through the trees instead of as a stamped block.
   */
  private ensurePathCrush(world: TileMap): Float32Array {
    if (this.crushFor === world && this.pathCrush) return this.pathCrush;

    const width = world.width;
    const height = world.height;
    const crush = new Float32Array(width * height);
    const tiles = world.tiles;
    let any = false;
    for (let ty = 0; ty < height; ty++) {
      const row = tiles[ty];
      for (let tx = 0; tx < width; tx++) {
        if (row[tx] === VOID) {
          crush[ty * width + tx] = 1;
          any = true;
        }
      }
    }
    if (any) {
      const reach = VOID_CRUSH_REACH;
      const span = Math.ceil(reach);
      for (let ty = 0; ty < height; ty++) {
        for (let tx = 0; tx < width; tx++) {
          const i = ty * width + tx;
          if (crush[i] === 1) continue;
          let best = reach;
          for (let dy = -span; dy <= span; dy++) {
            const ny = ty + dy;
            if (ny < 0 || ny >= height) continue;
            const row = tiles[ny];
            for (let dx = -span; dx <= span; dx++) {
              const nx = tx + dx;
              if (nx < 0 || nx >= width || row[nx] !== VOID) continue;
              const d = Math.hypot(dx, dy);
              if (d < best) best = d;
            }
          }
          if (best < reach) {
            const t = 1 - best / reach;
            crush[i] = t * t * (3 - 2 * t);
          }
        }
      }
    }

    this.pathCrush = crush;
    this.crushFor = world;
    return crush;
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
    // Fresh surfaces are transparent, so nothing outside the fov's dirty box
    // would ever be painted without this.
    this.stale = true;
  }
}
