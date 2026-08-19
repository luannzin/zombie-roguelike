/**
 * Airborne motes: dust, spores, the odd insect.
 *
 * Drawn BEFORE the darkness pass, which is the entire trick. Motes outside the
 * lantern are dimmed away with everything else, so they only really appear
 * inside the beam — the way dust only exists once a torch finds it. Drawing
 * them after the darkness would give you snow.
 *
 * The field is anchored to the CAMERA, not the world: a fixed pool of motes is
 * wrapped into the visible rectangle, so cost is constant regardless of map size
 * and you never see an edge to the effect. Wrapping is invisible because a mote
 * carries no identity — one drifting speck is any other drifting speck.
 *
 * Motion is deliberately slow and slightly vertical. Anything fast enough to
 * track with your eye stops being atmosphere and starts being a particle
 * effect competing with the gameplay.
 *
 * A FEW of the motes are LEAVES: bigger, slower, and tumbling — their width
 * breathes between one and three pixels, which at this scale reads as a flat
 * thing turning over as it falls. They are rare on purpose. Dust says the air
 * is thick; a leaf says the trees overhead are real and something is moving
 * them, and one every few seconds says that far better than a constant fall,
 * which reads as weather and then as snow.
 *
 * Rain and fog are the night's other coats, stated by the zone. Rain is
 * streaks in the lantern — you hear it everywhere, you SEE it in the beam,
 * same trick as the motes. Fog is a thicker field plus a veil. Both wrap
 * with the camera the way dust does, so cost stays constant.
 *
 * GROUND FOG is the fourth field and the only one that is not made of pixels.
 * It is always on, at a density the weather sets, and it is what gives a flat
 * top-down forest a floor with air above it: low banks drifting on the same
 * wind everything else bends to, wide and short, so they read as something
 * lying ON the ground rather than a veil hung in front of it. Drawn SMOOTH —
 * one soft blob baked once and stamped at a dozen scales with image smoothing
 * turned back on for the duration. That is the house split stated in one
 * pass: the world is pixel art, the air is not.
 *
 * Ordering does the rest. All four fields go in before the darkness, so the
 * fog only exists where there is light to find it. Fog drawn after the night
 * would be a grey sheet over a black screen.
 */

import { createSurface, type OffscreenSurface } from '../../lib/canvas';
import { palette } from '../../theme/palette';
import type { Camera } from '../camera';
import { angle as windAngle } from '../wind';

/** Motes alive at once. Constant — the pool wraps rather than spawning. */
const COUNT = 90;
/** Drift speed range, world px per second. */
const SPEED_MIN = 2.5;
const SPEED_MAX = 7;
/** Peak opacity. Low: these should register as texture, not as objects. */
const ALPHA_MIN = 0.1;
const ALPHA_MAX = 0.3;
/** Seconds for one full breathe cycle of a mote's opacity. */
const PULSE_MIN = 1.8;
const PULSE_MAX = 4.5;

/** Share of the pool that is a tumbling leaf rather than a speck of dust. */
const LEAF_SHARE = 0.09;
/** Leaves fall, they do not hang: their own drift, world px per second. */
const LEAF_FALL = 9;
const LEAF_ALPHA = 0.34;

const RAIN_COUNT = 140;
const RAIN_SPEED_MIN = 95;
const RAIN_SPEED_MAX = 165;
const FOG_VEIL = 0.07;

/** Ground-fog banks alive at once. Wrapped with the camera, never spawned. */
const BANK_COUNT = 16;
/** World px. Banks are much wider than they are tall — they lie down. */
const BANK_WIDTH_MIN = 110;
const BANK_WIDTH_MAX = 330;
const BANK_ASPECT = 0.34;
/** Drift, world px per second. Slower than the dust: mass moves reluctantly. */
const BANK_SPEED_MIN = 2;
const BANK_SPEED_MAX = 6.5;
const BANK_ALPHA_MIN = 0.05;
const BANK_ALPHA_MAX = 0.13;
/** Seconds for one bank to breathe through its own thickness. */
const BANK_PULSE_MIN = 7;
const BANK_PULSE_MAX = 15;
/** The baked blob, in its own pixels. Small: it is stamped scaled up. */
const BLOB_SIZE = 64;
/** How much ground fog each coat wants. */
const BANK_DENSITY: Record<string, number> = { clear: 0.55, rain: 0.4, fog: 1.6 };

interface Mote {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  alpha: number;
  phase: number;
  rate: number;
  /** Leaves tumble (width breathes) and fall; dust just drifts and pulses. */
  leaf: boolean;
}

interface Bank {
  x: number;
  y: number;
  vx: number;
  vy: number;
  width: number;
  alpha: number;
  phase: number;
  rate: number;
}

interface Streak {
  x: number;
  y: number;
  vx: number;
  vy: number;
  length: number;
  alpha: number;
}

export class AtmosphereLayer {
  private motes: Mote[] = [];
  private rain: Streak[] = [];
  private banks: Bank[] = [];
  /** One soft blob, baked on first use and stamped for every bank. */
  private blob: OffscreenSurface | null = null;
  private weather = 'clear';

  setWeather(kind: string): void {
    if (this.weather === kind) return;
    this.weather = kind;
    // Reseed so a dry night does not keep raining with leftover streaks.
    this.motes.length = 0;
    this.rain.length = 0;
    // The banks reseed too: a fog bank's whole identity is its size, and the
    // sizes a clear night wants are not the ones a fog bank wants.
    this.banks.length = 0;
  }

  /** Caller must have applied the world-space transform. */
  draw(ctx: CanvasRenderingContext2D, camera: Camera, dt: number): void {
    if (camera.viewWidth <= 0 || camera.viewHeight <= 0) return;
    // Ground first, and under everything else in this pass: it lies on the
    // floor, and the dust and the rain are in the air above it.
    this.drawGroundFog(ctx, camera, dt);
    if (this.weather === 'rain') {
      this.drawRain(ctx, camera, dt);
      this.drawMotes(ctx, camera, dt, 0.45);
      return;
    }
    if (this.weather === 'fog') {
      this.drawFog(ctx, camera);
      this.drawMotes(ctx, camera, dt, 1.55);
      return;
    }
    this.drawMotes(ctx, camera, dt, 1);
  }

  /**
   * Low banks drifting across the floor.
   *
   * Smoothing is turned ON for this pass and OFF again after, which is the
   * only place in the renderer that happens. A fog bank made of hard pixels is
   * a shape; a fog bank made of a soft gradient is air, and the difference is
   * most of what makes the forest look like it has depth in it.
   */
  private drawGroundFog(ctx: CanvasRenderingContext2D, camera: Camera, dt: number): void {
    const density = BANK_DENSITY[this.weather] ?? BANK_DENSITY.clear;
    if (density <= 0) return;
    if (this.banks.length === 0) this.seedBanks(camera, density);
    const blob = this.blob ?? this.bakeBlob();

    const left = camera.renderX;
    const top = camera.renderY;
    const width = camera.viewWidth;
    const height = camera.viewHeight;

    const smoothed = ctx.imageSmoothingEnabled;
    ctx.imageSmoothingEnabled = true;
    for (const bank of this.banks) {
      bank.x += bank.vx * dt;
      bank.y += bank.vy * dt;
      bank.phase += bank.rate * dt;
      bank.x = left + wrap(bank.x - left, width);
      bank.y = top + wrap(bank.y - top, height);

      const breathe = 0.55 + 0.45 * Math.sin(bank.phase);
      ctx.globalAlpha = bank.alpha * breathe * density;
      const w = bank.width;
      const h = w * BANK_ASPECT;
      ctx.drawImage(blob.canvas, bank.x - w / 2, bank.y - h / 2, w, h);
    }
    ctx.globalAlpha = 1;
    ctx.imageSmoothingEnabled = smoothed;
  }

  /**
   * The one blob every bank is a copy of: a radial falloff to nothing, baked
   * once. Stamping a cached bitmap is an order of magnitude cheaper than
   * building sixteen gradients a frame, and it is the same picture.
   */
  private bakeBlob(): OffscreenSurface {
    const surface = createSurface(BLOB_SIZE, BLOB_SIZE, 'ground-fog');
    const half = BLOB_SIZE / 2;
    const tone = palette().grade.fogGround;
    const gradient = surface.ctx.createRadialGradient(half, half, 0, half, half, half);
    gradient.addColorStop(0, `rgb(${tone[0]} ${tone[1]} ${tone[2]} / 1)`);
    gradient.addColorStop(0.45, `rgb(${tone[0]} ${tone[1]} ${tone[2]} / 0.55)`);
    gradient.addColorStop(1, `rgb(${tone[0]} ${tone[1]} ${tone[2]} / 0)`);
    surface.ctx.fillStyle = gradient;
    surface.ctx.fillRect(0, 0, BLOB_SIZE, BLOB_SIZE);
    this.blob = surface;
    return surface;
  }

  private seedBanks(camera: Camera, density: number): void {
    const drift = windAngle(0);
    const count = Math.round(BANK_COUNT * Math.min(1.6, density));
    for (let i = 0; i < count; i++) {
      const speed = BANK_SPEED_MIN + Math.random() * (BANK_SPEED_MAX - BANK_SPEED_MIN);
      // Banks travel with the wind, not in every direction: fog that drifts
      // against the grass everything else is bending in reads as a bug.
      const angle = drift + (Math.random() - 0.5) * 0.5;
      this.banks.push({
        x: camera.renderX + Math.random() * camera.viewWidth,
        y: camera.renderY + Math.random() * camera.viewHeight,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed * 0.4,
        width: BANK_WIDTH_MIN + Math.random() * (BANK_WIDTH_MAX - BANK_WIDTH_MIN),
        alpha: BANK_ALPHA_MIN + Math.random() * (BANK_ALPHA_MAX - BANK_ALPHA_MIN),
        phase: Math.random() * Math.PI * 2,
        rate: (Math.PI * 2) / (BANK_PULSE_MIN + Math.random() * (BANK_PULSE_MAX - BANK_PULSE_MIN)),
      });
    }
  }

  private drawMotes(
    ctx: CanvasRenderingContext2D,
    camera: Camera,
    dt: number,
    density: number,
  ): void {
    if (this.motes.length === 0) this.seed(camera, density);
    const left = camera.renderX;
    const top = camera.renderY;
    const width = camera.viewWidth;
    const height = camera.viewHeight;
    const dust = palette().effects.dustSmear;
    const leafColor = palette().tiles.tree;
    const fog = this.weather === 'fog';

    for (const mote of this.motes) {
      mote.x += mote.vx * dt;
      mote.y += mote.vy * dt;
      mote.phase += mote.rate * dt;

      mote.x = left + wrap(mote.x - left, width);
      mote.y = top + wrap(mote.y - top, height);

      if (mote.leaf) {
        const turn = Math.abs(Math.sin(mote.phase));
        ctx.fillStyle = leafColor;
        ctx.globalAlpha = mote.alpha * (fog ? 0.7 : 1);
        ctx.fillRect(
          Math.round(mote.x),
          Math.round(mote.y),
          1 + Math.round(turn * 2),
          mote.size,
        );
        continue;
      }

      const pulse = 0.55 + 0.45 * Math.sin(mote.phase);
      ctx.fillStyle = dust;
      ctx.globalAlpha = mote.alpha * pulse * (fog ? 1.25 : 1);
      const size = fog ? mote.size + 1 : mote.size;
      ctx.fillRect(Math.round(mote.x), Math.round(mote.y), size, size);
    }
    ctx.globalAlpha = 1;
  }

  private drawRain(ctx: CanvasRenderingContext2D, camera: Camera, dt: number): void {
    if (this.rain.length === 0) this.seedRain(camera);
    const left = camera.renderX;
    const top = camera.renderY;
    const width = camera.viewWidth;
    const height = camera.viewHeight;
    const color = palette().effects.dustSmear;
    ctx.fillStyle = color;

    for (const streak of this.rain) {
      streak.x += streak.vx * dt;
      streak.y += streak.vy * dt;
      streak.x = left + wrap(streak.x - left, width);
      streak.y = top + wrap(streak.y - top, height);
      ctx.globalAlpha = streak.alpha;
      const x = Math.round(streak.x);
      const y = Math.round(streak.y);
      ctx.fillRect(x, y, 1, streak.length);
      ctx.globalAlpha = streak.alpha * 0.45;
      ctx.fillRect(x + 1, y + 1, 1, Math.max(1, streak.length - 1));
    }
    ctx.globalAlpha = 1;
  }

  private drawFog(ctx: CanvasRenderingContext2D, camera: Camera): void {
    ctx.fillStyle = palette().minimap.fog;
    ctx.globalAlpha = FOG_VEIL;
    ctx.fillRect(
      Math.round(camera.renderX),
      Math.round(camera.renderY),
      Math.ceil(camera.viewWidth),
      Math.ceil(camera.viewHeight),
    );
    ctx.globalAlpha = 1;
  }

  /** Drop the pools; they reseed on the next frame. */
  reset(): void {
    this.motes.length = 0;
    this.rain.length = 0;
    this.banks.length = 0;
    this.blob = null;
  }

  private seed(camera: Camera, density: number): void {
    const count = Math.round(COUNT * density);
    for (let i = 0; i < count; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = SPEED_MIN + Math.random() * (SPEED_MAX - SPEED_MIN);
      const leaf = Math.random() < LEAF_SHARE;
      this.motes.push({
        x: camera.renderX + Math.random() * camera.viewWidth,
        y: camera.renderY + Math.random() * camera.viewHeight,
        vx: Math.cos(angle) * speed * (leaf ? 0.5 : 1),
        vy: Math.sin(angle) * speed * 0.6 + (leaf ? LEAF_FALL : 1.5),
        size: leaf ? 2 : Math.random() < 0.8 ? 1 : 2,
        alpha: leaf ? LEAF_ALPHA : ALPHA_MIN + Math.random() * (ALPHA_MAX - ALPHA_MIN),
        phase: Math.random() * Math.PI * 2,
        rate: leaf
          ? 1.1 + Math.random() * 0.9
          : (Math.PI * 2) / (PULSE_MIN + Math.random() * (PULSE_MAX - PULSE_MIN)),
        leaf,
      });
    }
  }

  private seedRain(camera: Camera): void {
    const drift = windAngle(0);
    const dx = Math.cos(drift) * 0.35;
    const dy = 1;
    for (let i = 0; i < RAIN_COUNT; i++) {
      const speed = RAIN_SPEED_MIN + Math.random() * (RAIN_SPEED_MAX - RAIN_SPEED_MIN);
      this.rain.push({
        x: camera.renderX + Math.random() * camera.viewWidth,
        y: camera.renderY + Math.random() * camera.viewHeight,
        vx: dx * speed,
        vy: dy * speed,
        length: 2 + ((Math.random() * 4) | 0),
        alpha: 0.18 + Math.random() * 0.28,
      });
    }
  }
}

function wrap(value: number, span: number): number {
  const wrapped = value % span;
  return wrapped < 0 ? wrapped + span : wrapped;
}
