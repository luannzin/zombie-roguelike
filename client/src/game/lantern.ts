/**
 * The lantern and its battery.
 *
 * One number comes out of this file — `output`, 0..1 — and the whole lighting
 * system reads it: the fov's beam gain and reach, the warmth of the hearth, and
 * the HUD's four cells. Everything else here exists to make that number lie
 * convincingly.
 *
 * The battery is FOUR CELLS, drawn on the HUD so the player can read how much
 * light is left at a glance. They drain continuously — the lamp burns until the
 * last cell runs dry, and only a flat battery cuts it out.
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
 * The battery is CLIENT-LOCAL. The switch is not: `on` rides the input packet
 * and comes back on every player snapshot so remotes go dark when the lamp is
 * off. Vision itself stays a visual system (see fov.ts).
 *
 * Some zones forbid the lamp outright (`allowed`) — the camp is lit by its
 * bonfire and the battery is what you carry out of it. A forbidden lamp still
 * ANSWERS the key: it counts the refusal so the HUD can push back, because a
 * control that silently does nothing reads as a broken keybind.
 */

import { clamp01, expDamp } from '../lib/math';

/** Cells on the HUD. Purely a readout — draining one does not cut the lamp. */
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
  /** Whether this zone lets the lamp be switched on at all. */
  allowed: boolean;
  /**
   * How many times the switch has been refused. A COUNTER rather than a flag
   * because the HUD has to react to each press, and at 5 Hz two refusals a
   * second apart are otherwise indistinguishable from one.
   */
  refusals: number;
}

export class Lantern {
  /**
   * Whether this zone permits the lamp. False in the camp: the bonfire is the
   * light there, and the battery is a resource you carry OUT rather than burn
   * standing next to a fire.
   *
   * It is a property of the LAMP and not a check at the call site so that every
   * route to switching on — a keypress, a future toggle button, a respawn —
   * goes through one refusal.
   */
  allowed = true;

  private switchedOn = false;
  private stored = 1;
  /** Smoothed light actually leaving the lamp. */
  private emitted = 0;
  /** Blink phases still to run, oldest first. Empty = steady. */
  private readonly queue: Phase[] = [];
  private phaseLeft = 0;
  private dark = false;
  private clock = 0;
  /** Monotonic: survives `reset()` so a refusal is never swallowed by a rejoin. */
  private refusals = 0;
  /** Extraction chase: charge is zero and it will not trickle back. */
  private blackout = false;
  /**
   * An event dark is on: the lamp will not light, but the CELL is untouched.
   *
   * DELIBERATELY NOT `blackout`, and the difference is the whole point. The
   * extraction chase is terminal — charge goes to zero and never trickles
   * back, because the run home is the last thing that happens on that map. An
   * event dark LIFTS, and a player who came out the far side of one with a
   * dead battery would have been charged for something the game did to them.
   *
   * So this cuts the light and leaves the charge alone. It even keeps
   * recharging underneath, which is the right answer: the lamp was off, and
   * off is when a cell recovers.
   */
  private suppressed = false;
  /** `Filamento Frio`: an event dark does not reach this lamp. */
  private darkImmune = false;
  /** Per-instance phase, so the waver is not in lockstep with anything else. */
  private readonly seed = Math.random() * 1000;
  /**
   * How much longer the cell lasts than stock, out of `Bateria Fria`.
   *
   * THE BATTERY IS THE ONE CLIENT-LOCAL RESOURCE — the server does not
   * simulate charge, only the switch — so the skill has to be applied here
   * rather than at the constant. It divides the drain and leaves the recharge
   * alone: what the skill buys is a longer burn, not a faster recovery, and
   * making it do both would quietly turn a small row into the best one in the
   * catalog.
   */
  private endurance = 1;

  get on(): boolean {
    return this.switchedOn;
  }

  get charge(): number {
    return this.stored;
  }

  /**
   * Adopt the owner's lamp mod off the roster. 1 is stock.
   *
   * Clamped at the bottom because a value under 1 would mean a skill that made
   * the lantern worse, and nothing in the catalog does that — a bad number
   * arriving on the wire should be ignored, not obeyed.
   */
  setEndurance(scale: number): void {
    this.endurance = Number.isFinite(scale) ? Math.max(1, scale) : 1;
  }

  /** Cells with any juice left. */
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
      allowed: this.allowed,
      refusals: this.refusals,
    };
  }

  /**
   * Flip the switch. A flat battery refuses, and so does a zone that forbids
   * the lamp — in both cases the refusal is COUNTED rather than ignored, so the
   * HUD can answer the keypress. A control that does nothing at all reads as a
   * bug; one that visibly says no reads as a rule.
   */
  toggle(): void {
    if (this.switchedOn) {
      this.cut();
      return;
    }
    if (!this.allowed || this.stored <= 0 || this.blackout || this.suppressed) {
      this.refusals++;
      return;
    }
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

    if (this.blackout) {
      this.stored = 0;
      if (this.switchedOn) this.cut();
    } else if (this.suppressed) {
      // Cut, but not charged for it — the cell recovers exactly as it would
      // with the lamp switched off, because that is what it is.
      if (this.switchedOn) this.cut();
      this.stored = Math.min(1, this.stored + dt / RECHARGE_SECONDS);
    } else if (this.switchedOn) {
      this.stored = Math.max(0, this.stored - dt / (DRAIN_SECONDS * this.endurance));
      if (this.stored <= 0) this.cut();
    } else {
      this.stored = Math.min(1, this.stored + dt / RECHARGE_SECONDS);
    }

    const lit = this.switchedOn && this.advance(dt);
    const target = lit ? this.brightness() : 0;
    const rate = target > this.emitted ? FILAMENT_RISE : FILAMENT_FALL;
    this.emitted += (target - this.emitted) * (1 - expDamp(rate, dt));
  }

  /**
   * Kill the battery and stop it recovering. The extraction chase: every lamp
   * on the map goes out together, and darkness is the resource you no longer
   * have. Cleared by `reset()` on the next welcome.
   */
  kill(): void {
    this.blackout = true;
    this.stored = 0;
    this.cut();
  }

  /**
   * An event dark, on or off. Mirrors `Room.dark_left` — see `suppressed`.
   *
   * The server is authoritative about this (it drops the `lantern` bit out of
   * every input while the dark is on), and this is the local half so the lamp
   * goes out on the frame the packet lands instead of a round trip later.
   */
  suppress(on: boolean): void {
    // `Filamento Frio` — see `darkImmune`. Checked here rather than at the
    // call site so that every route into a dark goes through one exemption.
    const want = on && !this.darkImmune;
    if (this.suppressed === want) return;
    this.suppressed = want;
    if (want) this.cut();
  }

  /**
   * Whether an event dark applies to this lamp. `Filamento Frio`.
   *
   * Held rather than passed to `suppress`, because the skill can be bought
   * mid-dark: a lamp that only learned about its own immunity at the next
   * event would stay out for the rest of the one it was bought in. Setting it
   * true lifts a suppression that is already running, which is exactly what
   * the player who just opened that canister expects to see.
   */
  setDarkImmune(on: boolean): void {
    if (this.darkImmune === on) return;
    this.darkImmune = on;
    if (on && this.suppressed) this.suppressed = false;
  }

  /** Back to a fresh lamp. Called on join and on dispose. */
  reset(): void {
    this.switchedOn = false;
    this.stored = 1;
    this.emitted = 0;
    this.queue.length = 0;
    this.phaseLeft = 0;
    this.dark = false;
    this.blackout = false;
    this.suppressed = false;
    // NOT `darkImmune`. It is a property of the PLAYER's build, not of the
    // lamp's state, and `adoptMods` re-asserts it off every roster anyway —
    // but clearing it here would blink the light off for one packet on every
    // welcome for anybody carrying the skill.
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
