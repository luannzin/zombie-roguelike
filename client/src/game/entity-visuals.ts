/**
 * Per-entity transient VISUAL state — animation phase, hit flash, recoil or
 * attack lunge, footstep cadence and the last seen HP used to detect damage.
 *
 * Keyed by entity id, so players and enemies share it: a zombie animates,
 * flashes when shot and kicks up dust exactly the way a player does, and
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
import { clamp01, expDamp } from '../lib/math';

/** Seconds of white flash after taking a hit. */
const HIT_FLASH_LIFE = 0.18;
/** Sprite kick distance opposite aim (world px). */
const RECOIL_KICK = 0;
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
  /** Set every frame the entity appears; drives prune(). */
  seen: boolean;
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
    seen: true,
  };
}

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
  kickRecoil(id: string, aimX: number, aimY: number): void {
    const state = this.state(id);
    state.recoilX = -aimX * RECOIL_KICK;
    state.recoilY = -aimY * RECOIL_KICK;
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

    while (state.stepAccum >= FOOTSTEP_SPACING) {
      state.stepAccum -= FOOTSTEP_SPACING;
      effects.spawnDust(x, feetY, dirX, dirY, state.stepSide);
      state.stepSide = -state.stepSide;
    }
  }
}
