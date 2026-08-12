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
 */

import { palette } from '../../theme/palette';
import type { Camera } from '../camera';

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

interface Mote {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  alpha: number;
  phase: number;
  rate: number;
}

export class AtmosphereLayer {
  private motes: Mote[] = [];

  /** Caller must have applied the world-space transform. */
  draw(ctx: CanvasRenderingContext2D, camera: Camera, dt: number): void {
    if (camera.viewWidth <= 0 || camera.viewHeight <= 0) return;
    if (this.motes.length === 0) this.seed(camera);

    const left = camera.renderX;
    const top = camera.renderY;
    const width = camera.viewWidth;
    const height = camera.viewHeight;
    const color = palette().effects.dustSmear;

    ctx.fillStyle = color;
    for (const mote of this.motes) {
      mote.x += mote.vx * dt;
      mote.y += mote.vy * dt;
      mote.phase += mote.rate * dt;

      // Wrap into the current view. Also handles the camera moving under them.
      mote.x = left + wrap(mote.x - left, width);
      mote.y = top + wrap(mote.y - top, height);

      // Breathe, so the field shimmers faintly instead of sliding rigidly.
      const pulse = 0.55 + 0.45 * Math.sin(mote.phase);
      ctx.globalAlpha = mote.alpha * pulse;
      ctx.fillRect(Math.round(mote.x), Math.round(mote.y), mote.size, mote.size);
    }
    ctx.globalAlpha = 1;
  }

  /** Drop the pool; it reseeds on the next frame. */
  reset(): void {
    this.motes.length = 0;
  }

  private seed(camera: Camera): void {
    for (let i = 0; i < COUNT; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = SPEED_MIN + Math.random() * (SPEED_MAX - SPEED_MIN);
      this.motes.push({
        x: camera.renderX + Math.random() * camera.viewWidth,
        y: camera.renderY + Math.random() * camera.viewHeight,
        vx: Math.cos(angle) * speed,
        // Biased downward: motes settle more than they rise.
        vy: Math.sin(angle) * speed * 0.6 + 1.5,
        size: Math.random() < 0.8 ? 1 : 2,
        alpha: ALPHA_MIN + Math.random() * (ALPHA_MAX - ALPHA_MIN),
        phase: Math.random() * Math.PI * 2,
        rate: (Math.PI * 2) / (PULSE_MIN + Math.random() * (PULSE_MAX - PULSE_MIN)),
      });
    }
  }
}

function wrap(value: number, span: number): number {
  const wrapped = value % span;
  return wrapped < 0 ? wrapped + span : wrapped;
}
