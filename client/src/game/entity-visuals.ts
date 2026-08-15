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
/** World px travelled between footfall dust puffs. */
const FOOTSTEP_SPACING = 7;
/**
 * Minimum gap between "your i-frames ate that" visuals on one target. A pack in
 * contact throws several absorbed swings per second and drawing every one of
 * them turns the victim into a strobe.
 */
const BLOCKED_VFX_GAP = 0.2;

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
  /** Advance and return the walk-cycle clock. Idle resets to frame 0. */
  advanceAnim(id: string, moving: boolean, dt: number): number {
    const state = this.state(id);
    state.animTime = moving ? state.animTime + dt : 0;
    return state.animTime;
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
    state.hitFlash = HIT_FLASH_LIFE;
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
    state.gunKick = -Math.abs(angle);
    state.gunPump = pump;
  }

  gunFeelOf(id: string): { kick: number; pump: number } {
    const state = this.states.get(id);
    if (!state) return { kick: 0, pump: 0 };
    return { kick: state.gunKick, pump: state.gunPump };
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
    for (const state of this.states.values()) {
      if (state.hitFlash > 0) state.hitFlash = Math.max(0, state.hitFlash - dt);
      if (state.blockedCooldown > 0) {
        state.blockedCooldown = Math.max(0, state.blockedCooldown - dt);
      }
      state.recoilX *= damp;
      state.recoilY *= damp;
      if (Math.abs(state.recoilX) < 0.01) state.recoilX = 0;
      if (Math.abs(state.recoilY) < 0.01) state.recoilY = 0;
      state.gunKick *= damp;
      state.gunPump *= damp;
      if (Math.abs(state.gunKick) < 0.002) state.gunKick = 0;
      if (Math.abs(state.gunPump) < 0.05) state.gunPump = 0;
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
