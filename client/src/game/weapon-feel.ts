/**
 * How a weapon BEHAVES in the hand, derived from the catalog row it already
 * ships with.
 *
 * The server owns what a weapon does — damage, cadence, reach, noise, the
 * recoil impulse. None of that is repeated here. What this file answers is
 * the presentation question the catalog leaves open: a Glock and an AK put
 * the same two numbers on the wire (`gunKick`, `gunPump`) and are held,
 * cycled and carried like completely different objects, and until this
 * existed the client drew them as one sprite that jumped and came back.
 *
 * EVERYTHING IS READ OFF THE ROW, NEVER OFF A PER-WEAPON TABLE. Twelve
 * hand-tuned animation blocks would drift from the catalog the first time a
 * cadence moved, and a thirteenth weapon would arrive with no entry and no
 * error. Two fields carry all of it:
 *
 *   * `kind` — pistol / smg / shotgun / rifle / sniper / melee, which the
 *     server already calls "presentation only". It decides how many HANDS are
 *     on the weapon and what its action IS. A pistol's slide, a rifle's bolt
 *     and a shotgun's forend are three different pieces of machinery and the
 *     eye knows all three; using one timing for them is what made every gun
 *     in this game feel like the same gun at different volumes.
 *   * `fireCooldown` — which decides how LONG that machinery may take. The
 *     action has to be closed before the trigger is live again, or a P90
 *     draws its second shot out of a weapon still standing open from the
 *     first. So every duration below is a fraction of the cadence, clamped
 *     to what the mechanism would plausibly take: an AWP bolt is slow because
 *     an AWP is slow, and it is never slower than the next round.
 *
 * The caps are the one authored half, and they are what stops a derivation
 * from being circular: a Glock's cadence would let its slide take 90 ms, and
 * a slide that takes 90 ms is a toy.
 */

import type { WeaponConfig } from '../net/protocol';

/** What reciprocates when the weapon fires, and therefore what the eye sees. */
export type WeaponAction = 'slide' | 'bolt' | 'pump' | 'none';

export interface WeaponFeel {
  /** Hands on the weapon. Two is a shoulder weapon; one is a sidearm. */
  hands: 1 | 2;
  action: WeaponAction;
  /** Seconds the action stays OPEN. The atlas swaps to `cycleFrame` for it. */
  cycle: number;
  /** Seconds after the shot before the brass clears the port. */
  eject: number;
  /** Heat one trigger pull leaves in the barrel, 0..1, accumulating. */
  heat: number;
  /** Radians of idle drift. What "held steady" is worth on this weapon. */
  sway: number;
  /** World px the muzzle rides up and down with the walk. */
  bob: number;
  /**
   * The mechanism is slow enough to HEAR over the round that worked it.
   *
   * A pistol's slide is shut again inside the gunshot's own transient, so a
   * clack for it is a sound mixed under the loudest thing in the game and
   * heard by nobody. A shotgun's forend and a rifle bolt are their own event,
   * happening in the space the report leaves behind — which is exactly when a
   * player is waiting to be able to fire again, and therefore the moment a
   * sound is worth spending.
   */
  audible: boolean;
}

/**
 * A weapon nobody is holding. Also what an unknown `kind` falls back to, so a
 * catalog row added on the server draws as a plain held object rather than
 * throwing at the one moment a player is looking at it.
 */
export const EMPTY_FEEL: WeaponFeel = {
  hands: 1,
  action: 'none',
  cycle: 0,
  eject: 0,
  heat: 0,
  sway: 0.03,
  bob: 0.5,
  audible: false,
};

/**
 * The longest a mechanism may stay open, per action.
 *
 * A SLIDE IS FASTER THAN THE EYE and its whole tell is the flicker; a
 * shotgun's forend is a full gesture and the player is meant to watch it
 * happen; a bolt-action rifle is a gesture you are meant to be impatient
 * through. These three numbers are the entire difference in feel between the
 * classes, which is why they are here rather than folded into one constant.
 */
const CYCLE_CAP: Record<WeaponAction, number> = {
  slide: 0.075,
  bolt: 0.09,
  pump: 0.3,
  none: 0,
};
/**
 * The share of the cadence the action may spend. Under half, always: the
 * weapon has to be shut and still for a moment before the next round, or a
 * gun on a fast trigger never reads as closed at all — it reads as broken.
 */
const CYCLE_SHARE = 0.45;
/**
 * A bolt-action rifle is the exception the cap cannot express: the AWP's
 * cycle IS its cadence, and hiding it under a 90 ms cap would draw the one
 * weapon in the game you have to commit to as the fastest-handling thing on
 * the belt.
 */
const BOLT_ACTION_SHARE = 0.55;
const BOLT_ACTION_CAP = 0.5;
/** Brass clears the port at roughly full travel, not on the trigger. */
const EJECT_AT = 0.45;
/**
 * Heat per pull, off the muzzle flash the server already sizes per round.
 * `flash` runs about 0.6 on a Glock to 1.6 on the AWP, so a sidearm needs a
 * magazine to smoke and a rifle needs a burst.
 */
const HEAT_PER_FLASH = 0.16;
const HEAT_PER_SHOT_MAX = 0.34;
/**
 * Idle drift, and it is the one place a two-handed weapon gets paid for being
 * two-handed. A shouldered rifle is STEADIER than a pistol held out at arm's
 * length — half the drift and two thirds of the bob — which is a thing the
 * player feels long before they could name it.
 */
const SWAY_ONE_HAND = 0.032;
const SWAY_TWO_HAND = 0.016;
const BOB_ONE_HAND = 0.55;
const BOB_TWO_HAND = 0.38;
/** Cycles shorter than this are inside the gunshot. See `WeaponFeel.audible`. */
const AUDIBLE_CYCLE = 0.16;

/** Hands and action per catalog `kind`. Everything else is derived. */
const BY_KIND: Record<string, { hands: 1 | 2; action: WeaponAction }> = {
  pistol: { hands: 1, action: 'slide' },
  smg: { hands: 2, action: 'bolt' },
  shotgun: { hands: 2, action: 'pump' },
  rifle: { hands: 2, action: 'bolt' },
  sniper: { hands: 2, action: 'bolt' },
  melee: { hands: 1, action: 'none' },
};

/**
 * Cached per catalog row, because this is asked once per body per frame.
 *
 * The catalog arrives on `welcome` and never changes inside a run, so the
 * answer for a given row is a constant — and keying on the ROW rather than on
 * its name means a second `welcome` (camp, then forest) simply produces new
 * objects and the old ones are collected with it.
 */
const cache = new WeakMap<WeaponConfig, WeaponFeel>();

export function weaponFeel(weapon: WeaponConfig | undefined | null): WeaponFeel {
  if (!weapon) return EMPTY_FEEL;
  const found = cache.get(weapon);
  if (found) return found;
  const made = derive(weapon);
  cache.set(weapon, made);
  return made;
}

function derive(weapon: WeaponConfig): WeaponFeel {
  const shape = BY_KIND[weapon.kind] ?? { hands: 1 as const, action: 'none' as const };
  const hands = shape.hands;
  // A blade has no mechanism, and neither has anything the catalog grows a
  // new `kind` for: no cycle, no port, no brass.
  const boltAction = weapon.kind === 'sniper';
  const share = boltAction ? BOLT_ACTION_SHARE : CYCLE_SHARE;
  const cap = boltAction ? BOLT_ACTION_CAP : CYCLE_CAP[shape.action];
  const cycle = shape.action === 'none' ? 0 : Math.min(cap, weapon.fireCooldown * share);
  return {
    hands,
    action: shape.action,
    cycle,
    eject: cycle * EJECT_AT,
    heat: Math.min(HEAT_PER_SHOT_MAX, weapon.flash * HEAT_PER_FLASH),
    sway: hands === 2 ? SWAY_TWO_HAND : SWAY_ONE_HAND,
    bob: hands === 2 ? BOB_TWO_HAND : BOB_ONE_HAND,
    audible: cycle >= AUDIBLE_CYCLE,
  };
}
