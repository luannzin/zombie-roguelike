/**
 * Per-player transient VISUAL state — animation phase, hit flash, recoil kick,
 * footstep cadence and the last seen HP used to detect damage.
 *
 * None of this is authoritative: it can be dropped or rebuilt at any time and
 * the simulation is unaffected.
 *
 * This used to be seven parallel `Map<string, X>` fields on `Game`, which meant
 * seven places to clear on join and — because nothing removed entries when a
 * player left — seven maps that grew for the lifetime of the page. One record
 * per player, with `prune()` driven by the current snapshot, fixes both.
 */

import type { Effects } from './effects';
import { clamp01, expDamp } from '../lib/math';
import type { GameConfig } from '../net/protocol';

/** Seconds of white flash after taking a hit. */
const HIT_FLASH_LIFE = 0.18;
/** Sprite kick distance opposite aim (world px). */
const RECOIL_KICK = 0;
/** How fast recoil springs back (higher = snappier). */
const RECOIL_RECOVER = 16;
/** World px travelled between footfall dust puffs. */
const FOOTSTEP_SPACING = 7;

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
  /** Set every frame the player appears; drives prune(). */
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
    seen: true,
  };
}

export class PlayerVisuals {
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
   * Drop players that were not touched since the last call. Without this the
   * map keeps a record for every player who ever joined.
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
   * player just took damage and should flash.
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

  // --- recoil --------------------------------------------------------------
  kickRecoil(id: string, aimX: number, aimY: number): void {
    const state = this.state(id);
    state.recoilX = -aimX * RECOIL_KICK;
    state.recoilY = -aimY * RECOIL_KICK;
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
   */
  emitFootsteps(
    id: string,
    x: number,
    y: number,
    vx: number,
    vy: number,
    moving: boolean,
    effects: Effects,
    config: GameConfig,
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
    if (travelled > config.moveSpeed * 0.2) {
      state.stepAccum = 0;
      return;
    }

    state.stepAccum += travelled;
    const feetY = y + config.playerHalfHeight * 0.9;
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
