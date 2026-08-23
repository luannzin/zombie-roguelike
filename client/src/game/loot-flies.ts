/**
 * Collect flies: hold the item over the head, then send it into the bag.
 *
 * Membership (spawn / land) is a store React may subscribe to. Pose is
 * written every frame and read in rAF — never component state.
 */

import type { LootRarity } from '../net/protocol';
import type { Unsubscribe } from '../lib/store';

/** How long the item sits over the head before it travels. */
export const LOOT_FLY_HOLD = 0.55;
/** Head → slot. The bag is already open by the time this starts. */
export const LOOT_FLY_TRAVEL = 0.62;
export const LOOT_FLY_LIFE = LOOT_FLY_HOLD + LOOT_FLY_TRAVEL;

/**
 * Where a fly is going, and — separately — whose sprite it is.
 *
 * `ammo` LANDS ON A BELT CELL AND IS NOT THAT CELL'S ITEM. It flies at the
 * gun it just topped up, so it travels to the same anchor `hotbar` does, but
 * the cell already holds the weapon: folding the two together made the gun
 * blink out for the length of every ammo pickup, because a cell with a fly
 * incoming draws nothing.
 *
 * `skill` IS THE MACHINE'S PAYOUT and it is here rather than in a file of its
 * own because it is the same event: a thing you did not have appears over your
 * head and then goes into the part of the HUD that keeps it. The only
 * differences are the sprite (a tin, not a loot icon) and the target (the tray
 * as a whole, not a cell), and neither is worth a second copy of the hold,
 * the arc and the rAF pose.
 */
export type LootFlyDest = 'bag' | 'hotbar' | 'ammo' | 'worn' | 'skill';

export interface LootFlySpec {
  id: string;
  key: string;
  frame: number;
  rarity: LootRarity;
  slot: number;
  dest?: LootFlyDest;
  /**
   * Copies held once this one lands. `skill` flies only — it is what the tray
   * row counts up to, and it rides the fly because the count must not appear
   * until the tin is actually in the tray.
   */
  copies?: number;
}

/**
 * The anchor id a fly is aiming at.
 *
 * HERE RATHER THAN AT THE CALL SITE, because the mapping is part of what a
 * `dest` MEANS: `ammo` deliberately shares the belt cell's anchor with
 * `hotbar`, and a reader who only saw `dest === 'bag' ? ... : ...` at the
 * caller would have to work that out from the ternary.
 */
export const SKILL_TRAY_ANCHOR = 'skill-tray';

export function anchorFor(fly: LootFlySpec): string {
  switch (fly.dest ?? 'bag') {
    case 'skill':
      return SKILL_TRAY_ANCHOR;
    case 'hotbar':
    case 'ammo':
      return `hotbar-${fly.slot}`;
    // A plate flies at the armour row it went on. `slot` is an index into
    // `config.armorSlots`, not a bag cell — see `Room.wear_armor`.
    case 'worn':
      return `armor-${fly.slot}`;
    default:
      return `slot-${fly.slot}`;
  }
}

export interface LootFlyPose {
  x: number;
  y: number;
  scale: number;
  rotate: number;
  alpha: number;
}

export interface LootFlyEnds {
  from: { x: number; y: number };
  to: { x: number; y: number };
  /** Slot is on screen. Travel waits for this so we never fly at a collapsed cell. */
  ready: boolean;
}

const flies: LootFlySpec[] = [];
const ages = new Map<string, number>();
const poses = new Map<string, LootFlyPose>();
const listeners = new Set<() => void>();
let snapshot: readonly LootFlySpec[] = [];

function notify(): void {
  snapshot = flies.slice();
  for (const listener of listeners) listener();
}

export function spawnLootFly(spec: LootFlySpec): void {
  flies.push(spec);
  ages.set(spec.id, 0);
  notify();
}

/**
 * Advance every fly. `locate` is the current head and the current slot
 * centre — both can move (the player walks; the bag opens). Returns the ones
 * that LANDED this step, so the backpack can bump and the skill tray can take
 * delivery of what was in the tin.
 */
export function stepLootFlies(
  dt: number,
  locate: (fly: LootFlySpec) => LootFlyEnds | null,
): LootFlySpec[] {
  const landed: LootFlySpec[] = [];
  for (let i = flies.length - 1; i >= 0; i--) {
    const fly = flies[i]!;
    const ends = locate(fly);
    if (!ends) continue;
    let age = (ages.get(fly.id) ?? 0) + dt;
    if (age >= LOOT_FLY_HOLD && !ends.ready) {
      age = LOOT_FLY_HOLD - 0.0001;
    }
    if (age >= LOOT_FLY_LIFE) {
      flies.splice(i, 1);
      ages.delete(fly.id);
      poses.delete(fly.id);
      landed.push(fly);
      continue;
    }
    ages.set(fly.id, age);
    poses.set(fly.id, poseAt(age, ends));
  }
  if (landed.length > 0) notify();
  return landed;
}

function poseAt(age: number, ends: LootFlyEnds): LootFlyPose {
  if (age < LOOT_FLY_HOLD) {
    const pop = Math.min(1, age / 0.12);
    const bob = Math.sin(age * 7.5) * 3;
    return {
      x: ends.from.x,
      y: ends.from.y + bob,
      scale: 1.2 + 0.4 * pop,
      rotate: 0,
      alpha: pop,
    };
  }
  const t = (age - LOOT_FLY_HOLD) / LOOT_FLY_TRAVEL;
  const ease = 1 - (1 - t) ** 3;
  return {
    x: ends.from.x + (ends.to.x - ends.from.x) * ease,
    y: ends.from.y + (ends.to.y - ends.from.y) * ease,
    scale: 1.6 - 0.6 * ease,
    rotate: ease * 420,
    alpha: 1,
  };
}

/** How many flies are still the sprite for that cell. */
export function incomingCount(slot: number, dest: LootFlyDest = 'bag'): number {
  let n = 0;
  for (const fly of snapshot) {
    if (fly.slot === slot && (fly.dest ?? 'bag') === dest) n += 1;
  }
  return n;
}

/** True while a fly is still the sprite for that cell — the slot stays empty. */
export function incomingHas(slot: number): boolean {
  return incomingCount(slot) > 0;
}

export function listLootFlies(): readonly LootFlySpec[] {
  return snapshot;
}

export function readLootFlyPose(id: string): LootFlyPose | null {
  return poses.get(id) ?? null;
}

export function subscribeLootFlies(listener: () => void): Unsubscribe {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function clearLootFlies(): void {
  if (flies.length === 0) return;
  flies.length = 0;
  ages.clear();
  poses.clear();
  notify();
}
