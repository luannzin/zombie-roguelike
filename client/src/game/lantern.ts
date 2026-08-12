/**
 * The lantern and its battery.
 *
 * One number comes out of this file — `output`, 0..1 — and the whole lighting
 * system reads it: the fov's beam gain and reach, the warmth of the hearth, and
 * the HUD's four cells. Everything else here exists to make that number lie
 * convincingly.
 *
 * The battery is FOUR CELLS, and they are not just a readout. Every time one
 * empties the lamp CUTS OUT and the player has to press F again. That is the
 * point of the mechanic: the light is not a slider that fades away over four
 * minutes, it is four hard interruptions, each one landing at a moment the
 * player did not choose. A quarter of your light dying while a zombie is
 * walking at you is a decision — run, or stand still and reach for the switch.
 *
 * Three kinds of flicker, and they mean different things:
 *
 *   STARTUP   a switch that works on the first try every time is a button. A
 *             real lamp catches, drops out, and catches again, so most (not
 *             all — see the chance) activations stutter for a tenth of a second
 *             before settling. It costs nothing and it is the difference
 *             between "state changed" and "I turned something on".
 *   FAILING   on the last cell the lamp starts dropping out at random and
 *             wavering in between. This is a WARNING the player feels before
 *             they read it: you know the light is about to go without ever
 *             looking at the HUD.
 *   FILAMENT  output eases rather than steps, faster up than down, so a
 *             dropout has a real dying edge to it instead of a hard cut.
 *
 * The battery trickles back while the lamp is OFF, at less than half the rate
 * it drains. Without that the lantern would be permanently dead a few minutes
 * into a session; with it, darkness is the resource you spend to get light
 * back, which is the trade this game wants. Set RECHARGE_SECONDS to Infinity
 * to make cells permanent once battery pickups exist.
 *
 * This is CLIENT-LOCAL. The server does not know the lamp exists (see fov.ts:
 * vision is a visual system), so remote players always light at full output.
 */

import { clamp01, expDamp } from '../lib/math';

/** Cells on the HUD, and therefore the number of cut-outs a full charge gives. */
export const BATTERY_CELLS = 4;
/** Seconds of continuous light on a full charge. One cell is a quarter of it. */
const DRAIN_SECONDS = 120;
/** Seconds of darkness to trickle back to full. Infinity disables recovery. */
const RECHARGE_SECONDS = 300;
/** Cells remaining at or below which the lamp starts failing. */
const FAILING_CELLS = 1;

/** How often flipping the switch produces a stutter rather than a clean start. */
const STARTUP_STUTTER_CHANCE = 0.7;
/** Dropouts in a stutter, and the length of the lit / dark phases in seconds. */
const STARTUP_BLINKS = [1, 3] as const;
const STARTUP_CATCH = [0.03, 0.1] as const;
const STARTUP_GAP = [0.04, 0.14] as const;

/** Dropouts per second on the last cell: at the top of it, and at empty. */
const FAIL_RATE = [0.5, 3.4] as const;
/** Length of one failing dropout, and the chance it stutters twice. */
const FAIL_GAP = [0.03, 0.17] as const;
const FAIL_DOUBLE_CHANCE = 0.4;
/** Brightness floor while failing — the lamp wavers even when it is lit. */
const FAIL_WAVER = 0.24;

/** Filament response. Rising fast and falling faster is what reads as a lamp. */
const FILAMENT_RISE = 34;
const FILAMENT_FALL = 46;

interface Phase {
  dark: boolean;
  time: number;
}

/** What the HUD needs. Sampled at HUD_INTERVAL, not per frame. */
export interface LanternReading {
  on: boolean;
  /** 0..1 across the whole battery. Cell `i` holds `charge * CELLS - i`. */
  charge: number;
  /** Cells with any juice left, 0..BATTERY_CELLS. */
  cells: number;
  /** True once the lamp is on its last cell and dropping out. */
  failing: boolean;
}

export class Lantern {
  private switchedOn = false;
  private stored = 1;
  /** Smoothed light actually leaving the lamp. */
  private emitted = 0;
  /** Blink phases still to run, oldest first. Empty = steady. */
  private readonly queue: Phase[] = [];
  private phaseLeft = 0;
  private dark = false;
  private clock = 0;
  /** Per-instance phase, so the waver is not in lockstep with anything else. */
  private readonly seed = Math.random() * 1000;

  get on(): boolean {
    return this.switchedOn;
  }

  get charge(): number {
    return this.stored;
  }

  /** Cells with any juice left. Crossing one of these boundaries cuts the lamp. */
  get cells(): number {
    return Math.ceil(this.stored * BATTERY_CELLS);
  }

  get failing(): boolean {
    return this.switchedOn && this.cells <= FAILING_CELLS;
  }

  /** 0..1 light output this frame. The only thing the renderer reads. */
  get output(): number {
    return this.emitted;
  }

  reading(): LanternReading {
    return {
      on: this.switchedOn,
      charge: this.stored,
      cells: this.cells,
      failing: this.failing,
    };
  }

  /** Flip the switch. A flat battery refuses, which is the feedback. */
  toggle(): void {
    if (this.switchedOn) {
      this.cut();
      return;
    }
    if (this.stored <= 0) return;
    this.switchedOn = true;
    this.stutter();
  }

  /**
   * `powered` is false when the player is dead or not in the world: the lamp
   * goes out, stops draining and starts recovering, and has to be switched back
   * on after a respawn.
   */
  update(dt: number, powered: boolean): void {
    this.clock += dt;

    if (this.switchedOn && !powered) this.cut();

    if (this.switchedOn) {
      const before = this.cells;
      this.stored = Math.max(0, this.stored - dt / DRAIN_SECONDS);
      // Order matters: a flat battery is dead, not merely one cell down.
      if (this.stored <= 0) this.cut();
      else if (this.cells < before) this.cut();
    } else {
      this.stored = Math.min(1, this.stored + dt / RECHARGE_SECONDS);
    }

    const lit = this.switchedOn && this.advance(dt);
    const target = lit ? this.brightness() : 0;
    const rate = target > this.emitted ? FILAMENT_RISE : FILAMENT_FALL;
    this.emitted += (target - this.emitted) * (1 - expDamp(rate, dt));
  }

  /** Back to a fresh lamp. Called on join and on dispose. */
  reset(): void {
    this.switchedOn = false;
    this.stored = 1;
    this.emitted = 0;
    this.queue.length = 0;
    this.phaseLeft = 0;
    this.dark = false;
  }

  /** Kill the light now, whatever it was in the middle of doing. */
  private cut(): void {
    this.switchedOn = false;
    this.queue.length = 0;
    this.phaseLeft = 0;
    this.dark = false;
  }

  /** Queue the catch-and-drop stutter that plays when the switch is flipped. */
  private stutter(): void {
    if (Math.random() > STARTUP_STUTTER_CHANCE) return;
    const blinks = randomInt(STARTUP_BLINKS);
    for (let i = 0; i < blinks; i++) {
      this.queue.push({ dark: false, time: randomIn(STARTUP_CATCH) });
      this.queue.push({ dark: true, time: randomIn(STARTUP_GAP) });
    }
    // The queue running dry IS the steady state, so it ends on a dark phase.
  }

  /** Run the blink queue for this frame. Returns whether the lamp is lit now. */
  private advance(dt: number): boolean {
    if (this.queue.length === 0 && this.phaseLeft <= 0) this.maybeFail(dt);

    this.phaseLeft -= dt;
    while (this.phaseLeft <= 0) {
      const next = this.queue.shift();
      if (!next) {
        this.dark = false;
        this.phaseLeft = 0;
        break;
      }
      this.dark = next.dark;
      // Carry the overshoot, or a phase shorter than a frame would last one.
      this.phaseLeft += next.time;
    }
    return !this.dark;
  }

  /** On the last cell, roll for a dropout. Emptier = more often. */
  private maybeFail(dt: number): void {
    if (!this.failing) return;
    const emptiness = 1 - clamp01(this.stored * (BATTERY_CELLS / FAILING_CELLS));
    const rate = FAIL_RATE[0] + (FAIL_RATE[1] - FAIL_RATE[0]) * emptiness;
    if (Math.random() > rate * dt) return;

    this.queue.push({ dark: true, time: randomIn(FAIL_GAP) });
    if (Math.random() < FAIL_DOUBLE_CHANCE) {
      this.queue.push({ dark: false, time: randomIn(STARTUP_CATCH) });
      this.queue.push({ dark: true, time: randomIn(FAIL_GAP) });
    }
  }

  /** Steady output, minus the waver of a lamp running out of charge. */
  private brightness(): number {
    if (!this.failing) return 1;
    // Two incommensurate sines again (see fov.ts): a waver you can count is a
    // waver you notice as an animation rather than as a fault.
    const waver =
      Math.sin(this.clock * 17.3 + this.seed) * 0.6 +
      Math.sin(this.clock * 41.7 + this.seed * 2.1) * 0.4;
    return clamp01(1 - FAIL_WAVER + waver * FAIL_WAVER);
  }
}

function randomIn([lo, hi]: readonly [number, number]): number {
  return lo + Math.random() * (hi - lo);
}

function randomInt([lo, hi]: readonly [number, number]): number {
  return lo + Math.floor(Math.random() * (hi - lo + 1));
}
