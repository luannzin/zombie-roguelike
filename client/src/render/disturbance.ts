/**
 * Disturbance: what bodies do to the plants they walk through.
 *
 * The single biggest thing separating "a nice background" from "a place you
 * are in" is whether the background knows you are there. Wind (`wind.ts`) makes
 * the forest move; this makes it move BECAUSE OF YOU. Nothing else in the
 * frame gives that back for so little.
 *
 * A WAKE, NOT A COLLISION. Each body contributes two pushes: one at its feet,
 * and a weaker, wider one at a LAGGED position that chases it a few frames
 * behind. The lagged push is the whole trick — without it the grass snaps back
 * the instant you clear it and the effect reads as a bubble stuck to your feet.
 * With it, the weeds behind you are still recovering while the ones ahead have
 * not been touched, and that asymmetry is what the eye reads as motion through
 * a material.
 *
 * The push is a cosine of the horizontal offset, not a radial shove: a tuft
 * dead ahead of you barely moves and the ones to either side splay out, which
 * is what actually happens and, more usefully, keeps the plants directly under
 * a character from jittering as it crosses them.
 *
 * VISIBILITY IS A HARD GATE, AND IT IS A RULE, NOT AN OPTIMISATION. A creature
 * the fov says you cannot see contributes NOTHING. Grass bending around an
 * invisible body would be a free tracker that undoes the lantern completely —
 * the exact failure `layers/vision.ts` documents for sight cones drawn over
 * things in the dark. Bending foliage is a tell, and a tell is only fair if
 * you can see the thing making it. Inside your light it is a real one, and it
 * is the good kind for an extraction run: something moving through the weeds
 * at the edge of the beam is information you earned by looking.
 */

/** How far a body reaches into the undergrowth, in world px. */
const PUSH_RADIUS = 22;
/** The lagged wake is wider and softer than the body itself. */
const WAKE_RADIUS = 30;
const WAKE_STRENGTH = 0.62;
/** How fast the lagged position chases the body. Lower = longer wake. */
const WAKE_CHASE = 5.5;

/** Peak displacement in world px, at zero distance and full strength. */
const PUSH_AMOUNT = 3.4;
/** Share of the push that follows the body's heading rather than splaying. */
const TRAIL_SHARE = 0.55;

/** Bodies that have stopped still part the weeds, just less. */
const STILL_SCALE = 0.55;

interface Push {
  x: number;
  y: number;
  /** Squared radius, so the hot loop never takes a square root to reject. */
  r2: number;
  radius: number;
  strength: number;
  /** Unit heading of the body that made this push, on the x axis. */
  hx: number;
}

/**
 * The minimum a body has to expose for the field to push anything.
 *
 * Structurally a subset of `DrawableEntity`, on purpose: the renderer hands
 * its existing entity list straight in, with no per-frame mapping. This runs
 * sixty times a second on every body on screen, and a projection array would
 * be pure garbage for no gain.
 */
export interface Disturber {
  id: string;
  x: number;
  /** Box CENTRE, as an entity carries it. The feet are `y + halfHeight`. */
  y: number;
  halfHeight: number;
  moving: boolean;
  /** 0..1 from the fov. Zero contributes nothing at all; see the file header. */
  visibility: number;
}

interface Wake {
  x: number;
  y: number;
  seen: boolean;
}

export class DisturbanceField {
  private readonly wakes = new Map<string, Wake>();
  private readonly pushes: Push[] = [];

  /** Rebuild the frame's pushes. Call once per frame, before any layer reads it. */
  update(bodies: readonly Disturber[], dt: number): void {
    this.pushes.length = 0;
    for (const wake of this.wakes.values()) wake.seen = false;

    // Frame-rate independent chase. Exponential rather than linear so the wake
    // never overshoots on a long frame — a wake that snapped past the body
    // would bend the grass the wrong way for a frame.
    const chase = 1 - Math.exp(-WAKE_CHASE * dt);

    for (const body of bodies) {
      if (body.visibility <= 0) continue;

      const footY = body.y + body.halfHeight;
      let wake = this.wakes.get(body.id);
      if (!wake) {
        wake = { x: body.x, y: footY, seen: true };
        this.wakes.set(body.id, wake);
      }
      wake.seen = true;

      const dx = body.x - wake.x;
      const dy = footY - wake.y;
      wake.x += dx * chase;
      wake.y += dy * chase;

      // Heading comes from the wake, not from an aim vector: what parts the
      // weeds is where the body actually went, and a character strafing while
      // aiming elsewhere should push the way it is travelling.
      const distance = Math.hypot(dx, dy);
      const hx = distance > 0.01 ? dx / distance : 0;

      const strength = body.visibility * (body.moving ? 1 : STILL_SCALE);
      this.pushes.push({
        x: body.x,
        y: footY,
        r2: PUSH_RADIUS * PUSH_RADIUS,
        radius: PUSH_RADIUS,
        strength,
        hx,
      });
      this.pushes.push({
        x: wake.x,
        y: wake.y,
        r2: WAKE_RADIUS * WAKE_RADIUS,
        radius: WAKE_RADIUS,
        strength: strength * WAKE_STRENGTH,
        hx,
      });
    }

    // Anything that left the frame — a body that died, walked into the dark, or
    // disconnected — stops being tracked, or the map accumulates one wake per
    // entity that has ever existed.
    for (const [id, wake] of this.wakes) {
      if (!wake.seen) this.wakes.delete(id);
    }
  }

  /** True when nothing is disturbing anything — lets a layer skip the loop. */
  get idle(): boolean {
    return this.pushes.length === 0;
  }

  /**
   * Horizontal displacement for a plant rooted at (x, y), in world px.
   *
   * Only horizontal, to match the sway the plants already do: they are drawn
   * bottom-anchored and shifted, so there is no second axis to move along
   * without redrawing them as a mesh.
   */
  bendAt(x: number, y: number): number {
    let bend = 0;
    for (const push of this.pushes) {
      const dx = x - push.x;
      const dy = y - push.y;
      const d2 = dx * dx + dy * dy;
      if (d2 >= push.r2) continue;
      const distance = Math.sqrt(d2);
      // Squared falloff: linear leaves a visible disc edge where the push
      // stops, which reads as a circle following the player.
      const falloff = (1 - distance / push.radius) ** 2;
      const splay = distance > 0.01 ? dx / distance : 0;
      bend +=
        falloff *
        push.strength *
        PUSH_AMOUNT *
        (splay * (1 - TRAIL_SHARE) + push.hx * TRAIL_SHARE);
    }
    return bend;
  }

  /** Forget every wake. For a map change or teardown. */
  clear(): void {
    this.wakes.clear();
    this.pushes.length = 0;
  }
}
