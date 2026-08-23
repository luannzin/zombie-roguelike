/**
 * The client's half of the boss fight: what the wire says, plus what it feels like.
 *
 * The server owns the fight — his position, his state, his playhead, every
 * hitbox. This file owns nothing about the outcome and everything about the
 * IMPACT: the flash when he is hit, the shake when he lands, the wobble under
 * a running engine, the ember light, the sound.
 *
 * WHY THE JUICE LIVES HERE AND NOT IN `game.ts`. It is a lot of small,
 * short-lived numbers that all decay, all read the same event list, and all
 * belong to one fight on one map. Threaded through `Game` they would be nine
 * more fields on a class that already has two hundred, live for the ninety
 * seconds a boss night lasts and be dead weight for the rest of a run. Here
 * they are one object that is null everywhere else.
 *
 * THE EVENT LIST IS FIRE-AND-FORGET. `bossEvents` never repeats: a client
 * that missed the packet with `impact` in it missed the shake and that is
 * all — it did not miss the damage, because the damage is on the health bar,
 * which is STATE. Everything in this file follows that split. Nothing here
 * may ever be the reason a player knows something.
 */

import type { BossEvent, BossRow, GameConfig } from '../net/protocol';
import { TRAIL_LENGTH, tipAt, type TrailPoint } from '../render/layers/boss-vfx';

/**
 * How long a hit flash lasts. Short — it is a punch, not a glow.
 *
 * Nudged up from 0.11 when the flash became the local player's PRIMARY signal
 * that a round connected (see `Game.feelBossHit`). At 0.11 a hit landing on
 * the frame before a snapshot could be most of the way decayed by the time
 * the eye found it, on a sprite that starts nearly black; at 0.15 it survives
 * a frame drop and still reads as a blink rather than a glow.
 */
const FLASH_LIFE = 0.15;
/** …and how long the one on his death lasts, which is not the same beat. */
const SLAIN_FLASH = 0.9;

export interface BossFeel {
  /** The last row the server sent. Null until he is on the map. */
  row: BossRow | null;
  /** 0..1, decaying. Painted over his silhouette. */
  flash: number;
  /** World-px wobble, resolved every frame from the engine and the shake. */
  shakeX: number;
  shakeY: number;
  /** Local decaying shake, added to the idle wobble. */
  jolt: number;
  /**
   * Seconds since the fight became winnable — the moment the cinematic ended.
   * Negative while it is still running. The HUD bar slides in off this.
   */
  engaged: number;
  /** Set for one frame when he goes down, so `Game` can run the payoff once. */
  slainAt: number | null;
  /** Bumps whenever the name plate should re-announce itself. */
  announce: number;
  /**
   * The bar's recent path, NEWEST FIRST.
   *
   * Newest first because the ribbon tapers from the head and every consumer
   * wants to walk it in that order; pushing to the front of a 12-element
   * array costs nothing and saves every reader from reversing it.
   */
  trail: TrailPoint[];
  /** Live impact flashes. Short-lived, and they outlive the event. */
  hits: BossHit[];
}

/** One landed blow, as a thing on screen rather than a thing that happened. */
export interface BossHit {
  x: number;
  y: number;
  dx: number;
  dy: number;
  age: number;
  life: number;
  /** Scales the crescent. A blow that caught somebody is bigger. */
  power: number;
}

export function newBossFeel(): BossFeel {
  return {
    row: null,
    flash: 0,
    shakeX: 0,
    shakeY: 0,
    jolt: 0,
    engaged: -1,
    slainAt: null,
    announce: 0,
    trail: [],
    hits: [],
  };
}

/** A row arrived. Replace, and notice the transitions worth reacting to. */
export function applyBossRow(feel: BossFeel, row: BossRow): void {
  const before = feel.row;
  feel.row = row;
  if (!before || before.s === 'sleep') {
    if (row.s !== 'sleep') feel.announce += 1;
  }
}

/**
 * What one event does to the picture. Returns the shake and the sound so
 * `Game` can apply them with the camera and the mixer it owns — this module
 * deliberately imports neither.
 */
export interface BossPunch {
  /** Camera trauma, 0..1. */
  trauma: number;
  /** Directional kick, in world px, and which way. */
  kick: number;
  kx: number;
  ky: number;
  /** A sound name from the audio manifest, or null. */
  sound: string | null;
  /** How loud, and whether it is positional. */
  gain: number;
  at: { x: number; y: number } | null;
  /** Seconds to wait — a landing lands, then the dust arrives. */
  delay: number;
}

const NOTHING: BossPunch = {
  trauma: 0, kick: 0, kx: 0, ky: 0, sound: null, gain: 1, at: null, delay: 0,
};

/**
 * THE WHOLE FEEL OF THE FIGHT IS THIS TABLE.
 *
 * Every kind gets its own trauma, its own kick and its own sound, and the
 * numbers are not interchangeable — that is the point. A boss whose every
 * beat shakes the screen by the same amount teaches the player nothing, and
 * after ninety seconds of it they have stopped seeing any of it. So:
 *
 *   the ARRIVAL is the biggest number on the sheet and happens once
 *   an IMPACT that HIT is worth more than one that missed, because the miss
 *     is already telling you something good
 *   a HIT ON HIM is deliberately tiny — it happens two hundred times, and
 *     the flash is doing that job
 *   the ROAR does not shake at all. It is a sound and a light, and a screen
 *     that rattles at it would make the one beat that is not an attack read
 *     as an attack.
 */
export function punchFor(event: BossEvent): BossPunch {
  const at = { x: event.x, y: event.y };
  switch (event.kind) {
    case 'arrive':
      return { ...NOTHING, sound: 'dread', gain: 0.9, at, delay: 0.1 };
    case 'impact': {
      const landed = (event.hits ?? 0) > 0;
      return {
        trauma: landed ? 0.62 : 0.34,
        kick: landed ? 15 : 7,
        kx: event.dx ?? 0,
        ky: event.dy ?? 0,
        sound: 'object-heavy',
        gain: landed ? 1 : 0.75,
        at,
        delay: 0,
      };
    }
    case 'rip':
      // A FAN IS LOUDER THAN A THROW. `hits` is how many crescents left the
      // bar — one before the enrage, three after — and the beat has to say
      // which, because the answer to them is a different answer.
      return {
        ...NOTHING,
        trauma: (event.hits ?? 1) > 1 ? 0.34 : 0.2,
        sound: 'knife-swing',
        gain: (event.hits ?? 1) > 1 ? 1.35 : 1.1,
        at,
      };
    case 'charge':
      // The moment he stops being a thing you are circling. Trauma, not a
      // kick: nothing has been hit yet — this is the launch, and the whole
      // job of it is to make the player look up.
      return { ...NOTHING, trauma: 0.4, sound: 'zombie-alert', gain: 1.4, at };
    case 'slam':
      // A charge that went into the treeline. The biggest free window in the
      // fight, and it has to SOUND like a mistake he made.
      return {
        trauma: 0.75, kick: 18, kx: event.dx ?? 0, ky: event.dy ?? 0,
        sound: 'crate-break', gain: 1.1, at, delay: 0,
      };
    case 'crestBurst':
      return { ...NOTHING, trauma: 0.16, sound: 'knife-hit', gain: 0.9, at };
    case 'roar':
      return { ...NOTHING, sound: 'zombie-alert', gain: 1.3, at };
    case 'enrage':
      return { ...NOTHING, trauma: 0.3, sound: 'siren', gain: 0.7, at };
    case 'hit':
      return { ...NOTHING, trauma: 0.03, sound: 'zombie-hit', gain: 0.6, at };
    case 'windup':
      // Silent and still by default — the ANIMATION is the telegraph and a
      // sound on every windup would bury the two that matter. The exception
      // is the enraged double chop: it arrives inside the window the player
      // has spent the whole fight learning is free, so it gets the one thing
      // a windup is normally denied, a noise that says "again".
      return event.encore
        ? { ...NOTHING, trauma: 0.22, sound: 'zombie-alert', gain: 0.9, at }
        : NOTHING;
    case 'hurt':
      return { ...NOTHING, trauma: 0.45, kick: 10, kx: event.dx ?? 0, ky: event.dy ?? 0 };
    case 'slain':
      return { ...NOTHING, trauma: 0.85, sound: 'crate-break', gain: 1.2, at, delay: 0.25 };
    default:
      return NOTHING;
  }
}

/** Apply an event's visual half. The audio half is the caller's. */
export function feelEvent(feel: BossFeel, event: BossEvent): void {
  switch (event.kind) {
    case 'hit':
      // STACKED, not assigned. Two clients watch the same fight and both of
      // them see a body being shot several times a second; a flash that
      // overwrites itself cannot get brighter under sustained fire, which is
      // exactly when the player most needs it to.
      feel.flash = Math.min(1, Math.max(feel.flash, 0.75) + 0.25);
      break;
    case 'slain':
      feel.flash = 1;
      feel.slainAt = 0;
      break;
    case 'impact': {
      const landed = (event.hits ?? 0) > 0;
      feel.jolt = Math.max(feel.jolt, landed ? 1 : 0.6);
      feel.hits.push({
        x: event.x,
        y: event.y,
        dx: event.dx ?? 0,
        dy: event.dy ?? 1,
        age: 0,
        life: 0.22,
        power: landed ? 1.25 : 0.85,
      });
      break;
    }
    case 'crestBurst':
      feel.hits.push({
        x: event.x, y: event.y, dx: event.dx ?? 1, dy: event.dy ?? 0,
        age: 0, life: 0.18, power: 0.7,
      });
      break;
    case 'engage':
      feel.engaged = 0;
      break;
    case 'enrage':
      feel.jolt = Math.max(feel.jolt, 0.8);
      feel.announce += 1;
      break;
    case 'charge':
      feel.jolt = Math.max(feel.jolt, 0.9);
      break;
    case 'slam':
      feel.jolt = Math.max(feel.jolt, 1.3);
      feel.hits.push({
        x: event.x, y: event.y,
        dx: event.dx ?? 0, dy: event.dy ?? 1,
        age: 0, life: 0.3, power: 1.6,
      });
      break;
    default:
      break;
  }
}

/**
 * Decay everything, and resolve this frame's wobble.
 *
 * THE IDLE WOBBLE IS THE ENGINE, and it is a function of what he is DOING
 * rather than a constant: hardest during a windup (he is fighting the thing),
 * gone entirely while he is down. Two sines at unrelated rates, because one
 * sine on a 128px sprite reads as a bob and two read as vibration.
 */
export function stepBossFeel(
  feel: BossFeel,
  dt: number,
  time: number,
  config: GameConfig | null = null,
): void {
  // THE TRAIL IS SAMPLED ON THE RENDER CLOCK, not on the snapshot. The bar
  // moves a third of a circle between two 30Hz rows during a sweep, so a
  // ribbon built from snapshot positions is a ribbon with three points in it.
  // `tipAt` re-derives the nose from the row's own playhead, which advances
  // smoothly, so sampling it every frame gives a smooth path from a stepped
  // source — and costs nothing, because it is two trig calls.
  const row = feel.row;
  const tip = row && config ? tipAt(row, config) : null;
  if (tip) {
    feel.trail.unshift({ x: tip.x, y: tip.y, age: 0 });
    if (feel.trail.length > TRAIL_LENGTH) feel.trail.length = TRAIL_LENGTH;
  } else if (feel.trail.length > 0) {
    // Not swinging: let the ribbon run out rather than cutting it. A trail
    // that vanishes on the frame the move ends takes the follow-through with
    // it, and the follow-through is half of what makes a swing feel heavy.
    feel.trail.pop();
  }
  for (const point of feel.trail) point.age += dt;

  for (const hit of feel.hits) hit.age += dt;
  feel.hits = feel.hits.filter((hit) => hit.age < hit.life);

  feel.flash = Math.max(0, feel.flash - dt / FLASH_LIFE);
  feel.jolt = Math.max(0, feel.jolt - dt * 6);
  if (feel.engaged >= 0) feel.engaged += dt;
  if (feel.slainAt !== null) {
    feel.slainAt += dt;
    feel.flash = Math.max(feel.flash, Math.max(0, 1 - feel.slainAt / SLAIN_FLASH) * 0.5);
  }

  if (!row || row.s === 'dead' || row.s === 'sleep') {
    feel.shakeX = 0;
    feel.shakeY = 0;
    return;
  }
  // The engine is loudest while he is fighting the thing, and a running boss
  // is a boss with the throttle wide open — `charge` sits with the windup
  // rather than with the walk.
  const hard = row.s === 'windup' || row.s === 'charge' ? 1
    : row.s === 'strike' ? 0.7 : 0.4;
  const rage = row.rage ? 1.4 : 1;
  const amount = (0.5 * hard * rage) + feel.jolt * 2.2;
  feel.shakeX = Math.sin(time * 41.3) * amount;
  feel.shakeY = Math.sin(time * 33.7 + 1.1) * amount * 0.7;
}

/** His health as a fraction, for the bar. Null when there is no fight. */
export function bossFraction(feel: BossFeel): number | null {
  const row = feel.row;
  if (!row || row.max <= 0) return null;
  return Math.max(0, Math.min(1, row.hp / row.max));
}
