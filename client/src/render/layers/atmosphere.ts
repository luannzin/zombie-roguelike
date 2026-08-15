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

/** Share of the pool that is a tumbling leaf rather than a speck of dust. */
const LEAF_SHARE = 0.09;
/** Leaves fall, they do not hang: their own drift, world px per second. */
const LEAF_FALL = 9;
const LEAF_ALPHA = 0.34;

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
    const dust = palette().effects.dustSmear;
    const leafColor = palette().tiles.tree;

    for (const mote of this.motes) {
      mote.x += mote.vx * dt;
      mote.y += mote.vy * dt;
      mote.phase += mote.rate * dt;

      // Wrap into the current view. Also handles the camera moving under them.
      mote.x = left + wrap(mote.x - left, width);
      mote.y = top + wrap(mote.y - top, height);

      if (mote.leaf) {
        // The tumble IS the animation: a leaf edge-on is one pixel wide and
        // face-on is three, and nothing else about it changes. Alpha stays
        // flat, because a leaf that also faded would read as another mote.
        const turn = Math.abs(Math.sin(mote.phase));
        ctx.fillStyle = leafColor;
        ctx.globalAlpha = mote.alpha;
        ctx.fillRect(
          Math.round(mote.x),
          Math.round(mote.y),
          1 + Math.round(turn * 2),
          mote.size,
        );
        continue;
      }

      // Breathe, so the field shimmers faintly instead of sliding rigidly.
      const pulse = 0.55 + 0.45 * Math.sin(mote.phase);
      ctx.fillStyle = dust;
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
      const leaf = Math.random() < LEAF_SHARE;
      this.motes.push({
        x: camera.renderX + Math.random() * camera.viewWidth,
        y: camera.renderY + Math.random() * camera.viewHeight,
        vx: Math.cos(angle) * speed * (leaf ? 0.5 : 1),
        // Biased downward: motes settle more than they rise, and a leaf has
        // real weight on top of that.
        vy: Math.sin(angle) * speed * 0.6 + (leaf ? LEAF_FALL : 1.5),
        size: leaf ? 2 : Math.random() < 0.8 ? 1 : 2,
        alpha: leaf ? LEAF_ALPHA : ALPHA_MIN + Math.random() * (ALPHA_MAX - ALPHA_MIN),
        phase: Math.random() * Math.PI * 2,
        // Leaves turn over slowly; the tumble is the one thing the eye can
        // follow here, so it has to stay under the speed of a glance.
        rate: leaf
          ? 1.1 + Math.random() * 0.9
          : (Math.PI * 2) / (PULSE_MIN + Math.random() * (PULSE_MAX - PULSE_MIN)),
        leaf,
      });
    }
  }
}

function wrap(value: number, span: number): number {
  const wrapped = value % span;
  return wrapped < 0 ? wrapped + span : wrapped;
}
