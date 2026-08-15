/**
 * Collect flies: an item lifts off the head and lands in the bag.
 *
 * Membership (spawn / land) is a store React may subscribe to. Pose is
 * written every frame and read in rAF — never component state.
 */

import type { LootRarity } from '../net/protocol';
import type { Unsubscribe } from '../lib/store';

export const LOOT_FLY_LIFE = 0.72;

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
    const t = age / LOOT_FLY_LIFE;
    const ease = 1 - (1 - t) ** 3;
    poses.set(fly.id, {
      x: ends.from.x + (ends.to.x - ends.from.x) * ease,
      y: ends.from.y + (ends.to.y - ends.from.y) * ease,
      scale: 1.55 - 0.7 * ease,
      rotate: ease * 420,
      alpha: t < 0.07 ? t / 0.07 : t > 0.9 ? (1 - t) / 0.1 : 1,
    });
  }
  if (landed > 0) notify();
  return landed;
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
