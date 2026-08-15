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

export interface LootFlySpec {
  id: string;
  key: string;
  frame: number;
  rarity: LootRarity;
  slot: number;
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
 * centre — both can move (the player walks; the bag opens). Returns how
 * many landed this step so the backpack can bump.
 */
export function stepLootFlies(
  dt: number,
  locate: (fly: LootFlySpec) => LootFlyEnds | null,
): number {
  let landed = 0;
  for (let i = flies.length - 1; i >= 0; i--) {
    const fly = flies[i]!;
    const age = (ages.get(fly.id) ?? 0) + dt;
    if (age >= LOOT_FLY_LIFE) {
      flies.splice(i, 1);
      ages.delete(fly.id);
      poses.delete(fly.id);
      landed += 1;
      continue;
    }
    ages.set(fly.id, age);
    const ends = locate(fly);
    if (!ends) continue;
    poses.set(fly.id, poseAt(age, ends));
  }
  if (landed > 0) notify();
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

/** True while a fly is still the sprite for that cell — the slot stays empty. */
export function incomingHas(slot: number): boolean {
  return snapshot.some((fly) => fly.slot === slot);
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
