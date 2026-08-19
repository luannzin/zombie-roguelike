/**
 * Per-entity transient VISUAL state — animation phase, hit flash, recoil or
 * attack lunge, footstep cadence, the wounds it is wearing, and the last seen
 * HP used to detect damage.
 *
 * Keyed by entity id, so players and enemies share it: a zombie animates,
 * flashes when shot, bleeds and kicks up dust exactly the way a player does, and
 * `prune()` reclaims a record the moment its owner stops appearing in
 * snapshots — which for enemies is every death and despawn.
 *
 * None of this is authoritative: it can be dropped or rebuilt at any time and
 * the simulation is unaffected.
 *
 * This used to be seven parallel `Map<string, X>` fields on `Game`, which meant
 * seven places to clear on join and — because nothing removed entries when a
 * player left — seven maps that grew for the lifetime of the page. One record
 * per entity, with `prune()` driven by the current snapshot, fixes both.
 */

import type { Effects } from './effects';
import { clamp01, expDamp, normalize } from '../lib/math';

/** Seconds of white flash after taking a hit. Shared with crate smash. */
export const HIT_FLASH_LIFE = 0.18;
/** Sprite kick distance opposite aim (world px). Default; weapons pass their own. */
const RECOIL_KICK = 1.2;
/** How far an enemy lurches into its own attack (world px). */
const LUNGE_KICK = 3.5;
/** How fast recoil and lunges spring back (higher = snappier). */
const RECOIL_RECOVER = 16;
/** How fast a hit-stun tilt springs back after the freeze. */
const SPIN_RECOVER = 11;
/**
 * Gun damage → juice scale. On the ported CS2 ladder a Glock (9) sits just
 * under 1, an AK (11) a little over, a Deagle (16) at 1.6, and both the AWP
 * (35) and a full shotgun shell (36) peg the 3.2 cap — which is the right
 * place for the cap to be, since those are the two weapons that kill a
 * zombie outright. One number drives blood, knockback, tilt and freeze.
 */
export function hitPower(damage: number): number {
  return clamp(damage / 10, 0.5, 3.2);
}
/** Freeze the walk cycle only when the stun is long enough to read as planted. */
const PLANT_STUN = 0.08;
/** World px travelled between footfall dust puffs. */
const FOOTSTEP_SPACING = 7;
/**
 * Minimum gap between "your i-frames ate that" visuals on one target. A pack in
 * contact throws several absorbed swings per second and drawing every one of
 * them turns the victim into a strobe.
 */
const BLOCKED_VFX_GAP = 0.2;

/**
 * THE BLADE'S TIMELINE, and the first two numbers here are shared with
 * `drawSwings` in the effects layer rather than merely similar to them.
 *
 * `SWING_TRAVEL_END` is the fraction of a swing's life the leading EDGE
 * spends crossing the arc; the rest of the life is the path's tail closing
 * behind it. The sprite runs the same fraction and the same easing, which is
 * the entire fix for a knife that used to bob upward while its own slash
 * swept sideways past it. If either number moves, both move.
 */
const SWING_TRAVEL_END = 0.66;
/** Ease-out on the travel: fast off the mark, decelerating into the finish. */
function swingTravel(u: number): number {
  const x = clamp01(u / SWING_TRAVEL_END);
  return 1 - (1 - x) ** 2;
}
/**
 * How far PAST the starting lip the blade is cocked on the first frame, as a
 * fraction of the arc's half-width, and how much of the travel it takes to
 * resolve. This is the wind-up, and it costs no latency: the swing still
 * begins on the frame of the click, it just begins with the arm loaded. A
 * real wind-up phase before the arc would read better in a fighting game and
 * would put sixty milliseconds between a click and any white on screen,
 * which is the one thing a weapon must never do.
 */
const SWING_OVERSHOOT = 0.34;
const SWING_SNAP = 0.13;
/**
 * The follow-through, as a multiple of the swing's own length: the blade
 * carries past the far lip and is drawn back to rest rather than switched
 * off there. A swing that ended the instant the arc did would snap the
 * sprite back to centre in one frame, which is the tell that a pose is a
 * value and not a motion.
 */
const SWING_RETURN = 0.9;

/**
 * A wound worn on a body: one frame of the gore sheet, pinned to a spot on the
 * sprite and carried around until it dries.
 *
 * The offsets are NORMALISED rather than in world pixels, because this module
 * knows nothing about how big anything is: `u` is -1..1 across the sprite's
 * width and `v` is 0..1 up from its feet, and the renderer multiplies by the
 * sheet it is about to draw. A creature twice the size wears its wounds in the
 * same places with no code here.
 */
export interface BloodStain {
  u: number;
  v: number;
  /** Frame in the gore sheet — a wound kind, not an animation step. */
  frame: number;
  flip: boolean;
  age: number;
  life: number;
}

/**
 * How long a wound stays on a body, and how much of the end of that is spent
 * fading. Long enough that a zombie you have shot twice LOOKS like a zombie
 * you have shot twice — that is the whole point, since a health bar only
 * appears once you have hurt something and reads as a number rather than as
 * damage — and short enough that a survivor of a long fight is not solid red.
 */
const STAIN_LIFE = 7;
const STAIN_FADE = 2;
/**
 * Wounds worn at once. Past a few they stop being wounds and start being a
 * red silhouette, which hides the creature the lantern just found.
 */
const STAIN_LIMIT = 4;
/** Frames in the gore sheet. Mirrors `KINDS` in server/tools/make_gore.py. */
const STAIN_FRAMES = 6;

interface VisualState {
  animTime: number;
  /** Remaining hit-flash time in seconds. */
  hitFlash: number;
  /** Last known HP — used to detect damage between snapshots. */
  lastHp: number | null;
  recoilX: number;
  recoilY: number;
  /** Distance travelled since the last footfall puff. */
  stepAccum: number;
  stepPrevX: number;
  stepPrevY: number;
  /** Alternating foot side (-1 / 1). */
  stepSide: number;
  /** Seconds until this entity may show another blocked-hit visual. */
  blockedCooldown: number;
  /** Wounds worn on the sprite. Oldest first; see BloodStain. */
  stains: BloodStain[];
  /** Set every frame the entity appears; drives prune(). */
  seen: boolean;
  /** Muzzle climb, radians, springs back. */
  gunKick: number;
  /** Slide back along aim, world px. */
  gunPump: number;
  /**
   * A MELEE SWING IN FLIGHT. Seconds elapsed, and how long the pose runs.
   *
   * A gun's pose is a SPRING — `gunKick` snaps to a value and decays — and
   * that is right for a barrel jumping in somebody's hands. It is wrong for
   * a blade, and it was what the knife used: `kickGun(step.swing, 0)` tilted
   * the sprite up by a fixed angle and let it fall back, so the steel bobbed
   * upward while the white path swept sideways past it. The blade did not
   * follow its own slash because nothing ever asked it to.
   *
   * This is a TIMELINE instead, and it runs the same easing `drawSwings`
   * runs on the path, off the same `arcDegrees` — so the sprite IS the
   * leading edge of the arc rather than a separate animation that happens
   * nearby. `swingLife` of 0 means nothing is swinging.
   */
  swingAge: number;
  swingLife: number;
  /** Half-width of the travel, radians. Half the step's `arcDegrees`. */
  swingHalf: number;
  /** +1 / -1, which way round. The two slashes cross. */
  swingSweep: number;
  /** World px the grip thrusts out along the blade at mid-swing. */
  swingThrust: number;
  /** Radians of hit tilt around the feet. Springs back after stun. */
  hitSpin: number;
  /** Seconds the body stays planted before the knockback springs back. */
  stunLeft: number;
}

function blank(): VisualState {
  return {
    animTime: 0,
    hitFlash: 0,
    lastHp: null,
    recoilX: 0,
    recoilY: 0,
    stepAccum: 0,
    stepPrevX: Number.NaN,
    stepPrevY: Number.NaN,
    stepSide: 1,
    blockedCooldown: 0,
    stains: [],
    seen: true,
    gunKick: 0,
    gunPump: 0,
    swingAge: 0,
    swingLife: 0,
    swingHalf: 0,
    swingSweep: 1,
    swingThrust: 0,
    hitSpin: 0,
    stunLeft: 0,
  };
}

/** Nothing is wearing a wound — shared so the common case allocates nothing. */
const NO_STAINS: readonly BloodStain[] = [];

export class EntityVisuals {
  private readonly states = new Map<string, VisualState>();

  private state(id: string): VisualState {
    let found = this.states.get(id);
    if (!found) {
      found = blank();
      this.states.set(id, found);
    }
    found.seen = true;
    return found;
  }

  /** Forget everything — new room, or disconnect. */
  clear(): void {
    this.states.clear();
  }

  /**
   * Drop entities that were not touched since the last call. Without this the
   * map keeps a record for every player who ever joined and every enemy that
   * ever spawned.
   */
  prune(): void {
    for (const [id, state] of this.states) {
      if (!state.seen) this.states.delete(id);
      else state.seen = false;
    }
  }

  // --- animation -----------------------------------------------------------
  /**
   * Advance and return the walk-cycle clock. Idle resets to frame 0.
   *
   * `rate` quickens the cycle for a body covering ground faster than a walk —
   * a sprint at 1.55x playing the authored cadence is a character skating. It
   * is only ever used to speed the legs UP: the walk's own timing is art, and
   * a carry-slowed body still walks like a person carrying something rather
   * than one in slow motion.
   */
  advanceAnim(id: string, moving: boolean, dt: number, rate = 1): number {
    const state = this.state(id);
    const planted = state.stunLeft > PLANT_STUN;
    state.animTime = moving && !planted ? state.animTime + dt * Math.max(1, rate) : 0;
    return state.animTime;
  }

  /** True while a heavy hit has the body frozen on idle. */
  planted(id: string): boolean {
    const state = this.states.get(id);
    return !!state && state.stunLeft > PLANT_STUN;
  }

  // --- damage feedback -----------------------------------------------------
  /**
   * Record an authoritative HP value. Returns true when HP dropped, i.e. the
   * entity just took damage and should flash.
   */
  noteHp(id: string, hp: number): boolean {
    const state = this.state(id);
    const previous = state.lastHp;
    state.lastHp = hp;
    if (previous === null || hp >= previous) return false;
    state.hitFlash = Math.max(state.hitFlash, HIT_FLASH_LIFE);
    return true;
  }

  pulseHitFlash(id: string): void {
    this.state(id).hitFlash = HIT_FLASH_LIFE;
  }

  /** 0..1 flash intensity for the renderer. */
  hitFlashAmount(id: string): number {
    const state = this.states.get(id);
    if (!state) return 0;
    return clamp01(state.hitFlash / HIT_FLASH_LIFE);
  }

  // --- wounds --------------------------------------------------------------
  /**
   * Mark `id` with a wound from a hit that came in along `(dirX, dirY)`.
   *
   * The mark lands on the side the hit came FROM, so a creature shot from the
   * left wears it on its left — the sprite has one body and four facings, and
   * a wound placed on the exit side would be on the wrong half of the sprite
   * as soon as the thing turned around.
   *
   * The ranges are the TRUNK, and they are narrow for a reason: the renderer
   * masks every wound to the sprite's own alpha, so a mark aimed past the
   * silhouette does not spill — it is simply thrown away, and a hit that
   * leaves nothing visible is worse than one placed conservatively. On the
   * processed 16x16 grid a body runs x 4..11 and its trunk y 6..10, which is
   * roughly the middle two fifths across and a band from a third to two
   * thirds up. Legs are excluded: they are four pixels wide and a stain down
   * there reads as mud.
   */
  splatter(id: string, dirX: number, dirY: number): void {
    const state = this.state(id);
    if (state.stains.length >= STAIN_LIMIT) state.stains.shift();
    const { x: nx } = normalize(dirX, dirY);
    state.stains.push({
      u: clamp(-nx * 0.28 + (Math.random() - 0.5) * 0.32, -0.4, 0.4),
      v: 0.42 + Math.random() * 0.26,
      frame: (Math.random() * STAIN_FRAMES) | 0,
      flip: Math.random() < 0.5,
      age: 0,
      life: STAIN_LIFE * (0.8 + Math.random() * 0.4),
    });
  }

  /** Wounds `id` is currently wearing. Empty for anything unhurt. */
  stainsOf(id: string): readonly BloodStain[] {
    const state = this.states.get(id);
    if (!state || state.stains.length === 0) return NO_STAINS;
    return state.stains;
  }

  /**
   * Claim the right to draw a blocked-hit visual on `id`, at most one per
   * BLOCKED_VFX_GAP. Returns false when the last one is still too recent.
   */
  allowBlockedVfx(id: string): boolean {
    const state = this.state(id);
    if (state.blockedCooldown > 0) return false;
    state.blockedCooldown = BLOCKED_VFX_GAP;
    return true;
  }

  // --- recoil / lunge ------------------------------------------------------
  kickRecoil(id: string, aimX: number, aimY: number, kick = RECOIL_KICK): void {
    const state = this.state(id);
    state.recoilX = -aimX * kick;
    state.recoilY = -aimY * kick;
  }

  kickGun(id: string, angle: number, pump: number): void {
    const state = this.state(id);
    // A shot ends any swing still in the air: somebody who swapped from the
    // blade to a gun mid-arc is holding a barrel now, and a barrel does not
    // finish a follow-through.
    state.swingLife = 0;
    state.swingAge = 0;
    state.gunKick = -Math.abs(angle);
    state.gunPump = pump;
  }

  /**
   * Throw a BLADE, not a recoil. Call once per melee beat.
   *
   * `half` is half the step's arc in radians and `sweep` is which way round —
   * the same two numbers `Effects.spawnSwing` is given — so the sprite and
   * the white path are two drawings of one motion. `life` is the step's
   * `swingTime`; the pose outlives it by `SWING_RETURN` for the follow
   * through.
   *
   * Any gun recoil still in the air is cleared, because a blade and a barrel
   * are the same sprite and leaving a muzzle climb under a swing would tilt
   * the whole arc off its own centre.
   */
  startSwing(id: string, half: number, sweep: number, life: number, thrust: number): void {
    const state = this.state(id);
    state.swingAge = 0;
    state.swingLife = Math.max(0.02, life);
    state.swingHalf = Math.abs(half);
    state.swingSweep = sweep < 0 ? -1 : 1;
    state.swingThrust = thrust;
    state.gunKick = 0;
    state.gunPump = 0;
  }

  /**
   * A gunshot landing on a body. Knockback is a small shove ALONG the shot,
   * with a tilt around the feet. The freeze stacks so a burst plants them;
   * the server is what actually slows the walk. `power` is `hitPower(damage)`.
   */
  takeHit(id: string, dirX: number, dirY: number, power: number): void {
    const state = this.state(id);
    const { x: nx, y: ny } = normalize(dirX, dirY);
    const kick = 0.8 + power * 1.6;
    state.recoilX = nx * kick;
    state.recoilY = ny * kick;
    const twist = (0.035 + power * 0.055) * (nx >= 0 ? 1 : -1);
    if (Math.abs(twist) > Math.abs(state.hitSpin)) state.hitSpin = twist;
    state.stunLeft = Math.min(0.55, state.stunLeft + 0.04 + power * 0.07);
    state.hitFlash = HIT_FLASH_LIFE * (0.8 + power * 0.45);
    const wounds = power > 1.7 ? 2 : 1;
    for (let i = 0; i < wounds; i++) this.splatter(id, dirX, dirY);
  }

  hitSpinOf(id: string): number {
    const state = this.states.get(id);
    return state?.hitSpin ?? 0;
  }

  /**
   * How the held weapon is posed right now.
   *
   * `kick` is a gun's muzzle climb and is measured in the SPRITE's frame —
   * the renderer negates it when the aim is left, so a barrel rises whichever
   * way the body faces. `swing` is a blade's angle off the aim and is already
   * SCREEN space, because an arc has a handedness a mirror must not eat: the
   * two slashes of the chain cross, and negating one of them for a
   * left-facing player would uncross them.
   *
   * `pump` is along the barrel for a gun and along the BLADE for a swing,
   * which is why `gunHand` takes the swing angle too.
   */
  gunFeelOf(id: string): { kick: number; pump: number; swing: number } {
    const state = this.states.get(id);
    if (!state) return { kick: 0, pump: 0, swing: 0 };
    if (state.swingLife <= 0) {
      return { kick: state.gunKick, pump: state.gunPump, swing: 0 };
    }
    const pose = swingPose(state);
    return { kick: 0, pump: pose.thrust, swing: pose.angle };
  }

  /** Shove an attacker forward along its swing; same spring as recoil. */
  lunge(id: string, dirX: number, dirY: number): void {
    const state = this.state(id);
    state.recoilX = dirX * LUNGE_KICK;
    state.recoilY = dirY * LUNGE_KICK;
  }

  recoilOf(id: string): { x: number; y: number } {
    const state = this.states.get(id);
    if (!state) return { x: 0, y: 0 };
    return { x: state.recoilX, y: state.recoilY };
  }

  /** Decay flashes and recoil springs. Call once per rendered frame. */
  update(dt: number): void {
    const damp = expDamp(RECOIL_RECOVER, dt);
    const spinDamp = expDamp(SPIN_RECOVER, dt);
    for (const state of this.states.values()) {
      if (state.hitFlash > 0) state.hitFlash = Math.max(0, state.hitFlash - dt);
      if (state.blockedCooldown > 0) {
        state.blockedCooldown = Math.max(0, state.blockedCooldown - dt);
      }
      if (state.stunLeft > 0) {
        state.stunLeft = Math.max(0, state.stunLeft - dt);
      } else {
        state.recoilX *= damp;
        state.recoilY *= damp;
        if (Math.abs(state.recoilX) < 0.01) state.recoilX = 0;
        if (Math.abs(state.recoilY) < 0.01) state.recoilY = 0;
        state.hitSpin *= spinDamp;
        if (Math.abs(state.hitSpin) < 0.004) state.hitSpin = 0;
      }
      // A SWING RUNS ON A CLOCK, A GUN ON A SPRING, and the two never run
      // at once: `startSwing` clears the spring, and a shot clears the
      // clock. A blade decayed like a recoil is exactly the bug this
      // replaced — the pose would sag toward centre mid-arc instead of
      // carrying through it.
      if (state.swingLife > 0) {
        state.swingAge += dt;
        if (state.swingAge >= swingPoseLife(state)) {
          state.swingLife = 0;
          state.swingAge = 0;
        }
      } else {
        state.gunKick *= damp;
        state.gunPump *= damp;
        if (Math.abs(state.gunKick) < 0.002) state.gunKick = 0;
        if (Math.abs(state.gunPump) < 0.05) state.gunPump = 0;
      }
      if (state.stains.length > 0) ageStains(state.stains, dt);
    }
  }

  // --- footsteps -----------------------------------------------------------
  /**
   * Emit dust once per FOOTSTEP_SPACING world px travelled, alternating feet.
   * Teleports and respawn snaps are ignored so they do not spray a burst.
   *
   * `halfHeight` is the entity's own collision half-height (its feet), and
   * `topSpeed` the fastest it could plausibly have moved in one frame — both
   * come from the entity, not from the player constants, so enemies of any
   * size and speed leave footprints in the right place.
   */
  emitFootsteps(
    id: string,
    x: number,
    y: number,
    vx: number,
    vy: number,
    moving: boolean,
    effects: Effects,
    halfHeight: number,
    topSpeed: number,
    burden = 0,
  ): void {
    const state = this.state(id);
    const prevX = state.stepPrevX;
    const prevY = state.stepPrevY;
    state.stepPrevX = x;
    state.stepPrevY = y;

    if (!moving || Number.isNaN(prevX)) {
      state.stepAccum = 0;
      return;
    }

    const travelled = Math.hypot(x - prevX, y - prevY);
    // Ignore teleport / respawn snaps.
    if (travelled > topSpeed * 0.2) {
      state.stepAccum = 0;
      return;
    }

    state.stepAccum += travelled;
    const feetY = y + halfHeight * 0.9;
    const speed = Math.hypot(vx, vy);
    const dirX = speed > 1 ? vx : x - prevX;
    const dirY = speed > 1 ? vy : y - prevY;
    const load = Math.min(1.2, Math.max(0, burden));
    const spacing = FOOTSTEP_SPACING * (1 - 0.42 * Math.min(1, load));

    while (state.stepAccum >= spacing) {
      state.stepAccum -= spacing;
      effects.spawnDust(x, feetY, dirX, dirY, state.stepSide, load);
      state.stepSide = -state.stepSide;
    }
  }
}

/** 0..1 opacity for a stain: solid, then drying off over its last seconds. */
export function stainFade(stain: BloodStain): number {
  const left = stain.life - stain.age;
  return left >= STAIN_FADE ? 1 : clamp01(left / STAIN_FADE);
}

/** Age wounds in place, dropping the dry ones. Oldest-first order is kept. */
function ageStains(stains: BloodStain[], dt: number): void {
  let kept = 0;
  for (const stain of stains) {
    stain.age += dt;
    if (stain.age >= stain.life) continue;
    stains[kept++] = stain;
  }
  stains.length = kept;
}

function clamp(value: number, low: number, high: number): number {
  return value < low ? low : value > high ? high : value;
}

/** Total seconds a swing pose runs: the arc, then the follow-through. */
function swingPoseLife(state: VisualState): number {
  return state.swingLife * (SWING_TRAVEL_END + SWING_RETURN);
}

/**
 * Where the blade is, this frame.
 *
 * Three phases and no gaps between them:
 *
 *   SNAP    the first eighth of the travel. The edge starts cocked PAST the
 *           near lip of the arc by `SWING_OVERSHOOT` and closes onto the
 *           path — the arm loading, drawn without spending a frame on it.
 *   SWEEP   the edge crosses the arc on `swingTravel`, which is the exact
 *           curve `drawSwings` moves the white path on. This is the phase
 *           the whole rewrite exists for: sprite and path are one motion.
 *   RETURN  past the far lip the blade is DRAWN BACK to rest rather than
 *           released there, on an ease-in so it leaves slowly and arrives
 *           quickly — the shape a hand makes recovering a weapon.
 *
 * `thrust` rides a half-sine over the sweep: the grip pushes out along the
 * blade at the middle of the arc and is home again by the end of it, which is
 * what turns a rotation into a cut through something.
 *
 * The returned angle is SCREEN space and is signed by `swingSweep`, matching
 * `facing + (sweep > 0 ? lead : -lead)` in `drawSwings` exactly.
 */
function swingPose(state: VisualState): { angle: number; thrust: number } {
  const half = state.swingHalf;
  const sweepEnd = state.swingLife * SWING_TRAVEL_END;
  let lead: number;
  let thrust: number;

  if (state.swingAge <= sweepEnd) {
    const u = state.swingAge / state.swingLife;
    const travel = swingTravel(u);
    lead = -half + 2 * half * travel;
    // The load, gone within `SWING_SNAP` of the travel.
    lead -= half * SWING_OVERSHOOT * Math.max(0, 1 - u / SWING_SNAP);
    thrust = state.swingThrust * Math.sin(Math.PI * clamp01(u / SWING_TRAVEL_END));
  } else {
    const span = Math.max(1e-4, swingPoseLife(state) - sweepEnd);
    const k = clamp01((state.swingAge - sweepEnd) / span);
    // Ease-in: leaves the far lip slowly, arrives at rest quickly.
    lead = half * (1 - k * k);
    thrust = 0;
  }

  return { angle: state.swingSweep > 0 ? lead : -lead, thrust };
}
