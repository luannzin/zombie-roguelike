/**
 * The upgrade machine's ceremony — the client half of one lever pull.
 *
 * SAME SPLIT AS THE EXTRACTION PICKUP, and for the same reason. The server
 * decides WHAT came out and says so once (`SpinEvent`); this file decides what
 * the next few seconds LOOK like, on the render clock, because a four-second
 * set piece resolved at snapshot rate would step rather than play.
 *
 * Nothing here talks to the socket and nothing here draws. It owns one struct
 * — the pull in progress — and answers, for any instant, where the arm is,
 * what each reel is doing, and where the canister is. `layers/machine.ts`
 * paints that answer and `Game` plays the sounds against the beats it crosses.
 *
 * THE THIRD REEL IS THE WHOLE DESIGN. Two of them stop on a fixed rhythm the
 * player learns inside two visits; the third holds for `reelHold[rarity]`, and
 * that hold is longer the better the pull was. By the third shop a player
 * knows a long third reel is good news — so the wait stops being latency and
 * becomes the thing they are actually there for. Because the roll already
 * happened, the machine is never deciding late; it is taking its time telling
 * them.
 */

import type { LootRarity, MachineTimingConfig, SpinEvent } from '../net/protocol';

/** Fallback clock, used only if a server predating `config.machine` answers. */
const FALLBACK: MachineTimingConfig = {
  armTime: 0.34,
  spinUp: 0.52,
  reelOne: 1.37,
  reelTwo: 1.89,
  reelHold: { common: 0.3, uncommon: 0.55, rare: 0.95, epic: 1.45, legendary: 1.95 },
  ejectLag: 0.26,
  ejectFlight: 0.55,
  holdTime: 1.15,
  resetTime: 0.6,
  reachTiles: 2.2,
};

/** Beats a pull crosses exactly once. `Game` hangs the sounds off these. */
export type MachineBeat =
  | 'arm'
  | 'reel0'
  | 'reel1'
  | 'reel2'
  | 'eject'
  | 'settle'
  | 'claim';

const BEATS: MachineBeat[] = ['arm', 'reel0', 'reel1', 'reel2', 'eject', 'settle', 'claim'];

export interface MachineTiming {
  arm: number;
  reel0: number;
  reel1: number;
  reel2: number;
  eject: number;
  settle: number;
  claim: number;
  done: number;
}

/** When each beat lands, in seconds from the lever coming down. */
export function machineTiming(
  config: MachineTimingConfig | undefined,
  rarity: string,
): MachineTiming {
  const c = config ?? FALLBACK;
  const hold = c.reelHold?.[rarity] ?? FALLBACK.reelHold[rarity] ?? 0.3;
  const reel2 = c.reelTwo + hold;
  const eject = reel2 + c.ejectLag;
  const settle = eject + c.ejectFlight;
  const claim = settle + c.holdTime;
  return {
    arm: c.armTime,
    reel0: c.reelOne,
    reel1: c.reelTwo,
    reel2,
    eject,
    settle,
    claim,
    done: claim + c.resetTime,
  };
}

/** A pull in flight. One at a time — the server refuses a second lever. */
export interface MachinePull {
  by: string;
  key: string;
  rarity: LootRarity;
  /** Copies held after this one; the HUD tile counts to it. */
  copies: number;
  timing: MachineTiming;
  elapsed: number;
  /** Beats already fired, so a long frame cannot replay or skip one. */
  fired: Set<MachineBeat>;
}

export function beginPull(
  event: SpinEvent,
  config: MachineTimingConfig | undefined,
): MachinePull {
  return {
    by: event.by,
    key: event.k,
    rarity: event.r,
    copies: event.n,
    timing: machineTiming(config, event.r),
    elapsed: 0,
    fired: new Set(),
  };
}

/**
 * Advance a pull and return the beats it crossed on this frame.
 *
 * Beats fire on the frame `elapsed` CROSSES them rather than on the frame it
 * is nearest to, which is what makes each happen exactly once when a frame
 * runs long — the same rule the extraction pickup keeps.
 */
export function stepPull(pull: MachinePull, dt: number): MachineBeat[] {
  pull.elapsed += dt;
  const crossed: MachineBeat[] = [];
  for (const beat of BEATS) {
    if (pull.fired.has(beat)) continue;
    if (pull.elapsed >= pull.timing[beat]) {
      pull.fired.add(beat);
      crossed.push(beat);
    }
  }
  return crossed;
}

export function pullFinished(pull: MachinePull): boolean {
  return pull.elapsed >= pull.timing.done;
}

/** What one reel is doing right now. */
export interface ReelPose {
  /** True while the strip is still going past. */
  spinning: boolean;
  /**
   * How far into its landing bounce, 0..1, or -1 when it is not bouncing. A
   * reel that simply stops has no weight; one that overshoots by a pixel and
   * comes back has mass, and mass is the only thing separating this from a
   * number appearing in a box.
   */
  bounce: number;
}

/** How long a reel is visibly settling after it stops, in seconds. */
const REEL_BOUNCE = 0.16;

export function reelPose(pull: MachinePull, index: number): ReelPose {
  const stops = [pull.timing.reel0, pull.timing.reel1, pull.timing.reel2];
  const stop = stops[Math.min(index, stops.length - 1)];
  if (pull.elapsed < stop) {
    return { spinning: pull.elapsed >= pull.timing.arm, bounce: -1 };
  }
  const since = pull.elapsed - stop;
  return { spinning: false, bounce: since < REEL_BOUNCE ? since / REEL_BOUNCE : -1 };
}

/**
 * The arm, 0 at rest and 1 fully pulled.
 *
 * Down FAST and back up SLOW. A lever is thrown by a hand and released by a
 * spring, and matching those two speeds is what makes the pull read as
 * somebody doing something rather than as an animation playing.
 */
export function leverPose(pull: MachinePull | null): number {
  if (!pull) return 0;
  const { arm, claim, done } = pull.timing;
  if (pull.elapsed < arm) {
    const t = Math.max(0, pull.elapsed / Math.max(0.001, arm));
    return t * t;
  }
  if (pull.elapsed < claim) return 1;
  const t = (pull.elapsed - claim) / Math.max(0.001, done - claim);
  return Math.max(0, 1 - t);
}

/** Where the canister is, or null before the eject and after the claim. */
export interface CanPose {
  /** 0 at the tray mouth, 1 at its resting place on the lip. */
  travel: number;
  /** Height above the landing point, in world pixels. */
  lift: number;
  /** 0..1 while it is being looked at; 1 the instant it starts to leave. */
  held: number;
  /** True once it has begun flying to the HUD tray. */
  claimed: boolean;
}

/** How far out of the tray a canister lands, in world pixels. */
export const CAN_THROW = 9;
/** How high it arcs on the way. */
export const CAN_ARC = 11;

export function canPose(pull: MachinePull): CanPose | null {
  const { eject, settle, claim, done } = pull.timing;
  if (pull.elapsed < eject) return null;
  if (pull.elapsed < settle) {
    const t = (pull.elapsed - eject) / Math.max(0.001, settle - eject);
    return {
      travel: t,
      // A parabola, not an ease: the thing was thrown out of a slot by a
      // spring, so it goes up, slows, and comes down on the frame it lands.
      lift: Math.sin(t * Math.PI) * CAN_ARC,
      held: 0,
      claimed: false,
    };
  }
  if (pull.elapsed < claim) {
    return { travel: 1, lift: 0, held: (pull.elapsed - settle) / Math.max(0.001, claim - settle), claimed: false };
  }
  if (pull.elapsed < done) {
    const t = (pull.elapsed - claim) / Math.max(0.001, done - claim);
    return { travel: 1, lift: t * 26, held: 1, claimed: true };
  }
  return null;
}

/**
 * How much light this pull is throwing, 0..1.
 *
 * THE RARITY IS A MULTIPLIER AND NOT A SECOND ANIMATION. Everything about a
 * legendary pull is the common pull with this number bigger: a wider burst, a
 * brighter marquee, a longer hold. One curve scaled five ways stays one thing
 * the player is learning to read; five hand-authored ceremonies would be five.
 */
export const RARITY_GAIN: Record<string, number> = {
  common: 0.45,
  uncommon: 0.65,
  rare: 0.9,
  epic: 1.25,
  legendary: 1.7,
};

export function pullGain(pull: MachinePull): number {
  return RARITY_GAIN[pull.rarity] ?? RARITY_GAIN.common;
}

/**
 * The payout flash, 0..1 across the burst sheet, or -1 when it is not playing.
 *
 * It starts on the LAST REEL rather than on the eject, because the flash is
 * the machine reacting to its own result — the canister arriving is the
 * consequence, and a flash timed to it would be a light with no cause.
 */
export function burstProgress(pull: MachinePull, seconds: number): number {
  const since = pull.elapsed - pull.timing.reel2;
  if (since < 0 || since > seconds) return -1;
  return since / seconds;
}
