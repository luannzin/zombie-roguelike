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
 */

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
  private weather = 'clear';

  setWeather(kind: string): void {
    if (this.weather === kind) return;
    this.weather = kind;
    // Reseed so a dry night does not keep raining with leftover streaks.
    this.motes.length = 0;
    this.rain.length = 0;
  }

  /** Caller must have applied the world-space transform. */
  draw(ctx: CanvasRenderingContext2D, camera: Camera, dt: number): void {
    if (camera.viewWidth <= 0 || camera.viewHeight <= 0) return;
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

  /** Drop the pool; it reseeds on the next frame. */
  reset(): void {
    this.motes.length = 0;
    this.rain.length = 0;
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
