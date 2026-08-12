/**
 * Remote entities: snapshot buffer + entity interpolation.
 *
 * Remotes render `delayMs` in the past so two snapshots exist to lerp between.
 * Delay adapts to snapshot arrival jitter (and a light RTT floor): LAN sits
 * near ~50–66 ms, choppy nets climb toward MAX_DELAY_MS.
 *
 * Past the newest frame we briefly extrapolate with velocity instead of
 * freezing — late packets read as continued motion, then catch up on the
 * next snapshot. Cap keeps rubber-banding bounded.
 *
 * Players and enemies go through the same code: both are server-driven bodies
 * with position, velocity and facing, and the local player is the only entity
 * that is ever predicted instead of interpolated. Coins share the position
 * lerp path but have no facing.
 */

import { clamp, lerp, normalize } from '../lib/math';
import type { CoinState, EnemyState, PlayerState, SnapshotMessage } from '../net/protocol';

/** Fallback before enough arrival samples exist. */
export const INTERP_DELAY_MS = 66;
const MIN_DELAY_MS = 50;
const MAX_DELAY_MS = 150;
/** How far past the newest snapshot we coast on velocity. */
const MAX_EXTRAP_MS = 100;
const BUFFER_KEEP_MS = 1500;
const INTERVAL_SAMPLES = 30;

/** The shape interpolation needs: a body that moves and faces somewhere. */
interface Body {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  ax: number;
  ay: number;
}

/** Coins have no facing — blend only position / velocity. */
interface MovingBody {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

interface Frame {
  tick: number;
  /** local receive time (performance.now) */
  time: number;
  players: Map<string, PlayerState>;
  enemies: Map<string, EnemyState>;
  coins: Map<string, CoinState>;
}

export type Moving<T> = T & { moving: boolean };
export type RenderedPlayer = Moving<PlayerState>;
export type RenderedEnemy = Moving<EnemyState>;
export type RenderedCoin = Moving<CoinState>;

export interface RenderedWorld {
  players: RenderedPlayer[];
  enemies: RenderedEnemy[];
  coins: RenderedCoin[];
}

/** Speed (world px/s) above which a body reads as walking, not drifting. */
const MOVING_SPEED = 1;

export class SnapshotBuffer {
  private frames: Frame[] = [];
  private lastPushTime = 0;
  private intervals: number[] = [];
  /** Current adaptive render delay (ms behind `now`). */
  delayMs = INTERP_DELAY_MS;

  push(snapshot: SnapshotMessage, now: number): void {
    if (this.lastPushTime > 0) {
      const gap = now - this.lastPushTime;
      // Ignore reconnect / tab-sleep outliers (>0.5s).
      if (gap > 0 && gap < 500) {
        this.intervals.push(gap);
        if (this.intervals.length > INTERVAL_SAMPLES) this.intervals.shift();
        this.recomputeDelay();
      }
    }
    this.lastPushTime = now;

    this.frames.push({
      tick: snapshot.tick,
      time: now,
      players: index(snapshot.players),
      enemies: index(snapshot.enemies),
      coins: index(snapshot.coins ?? []),
    });

    const cutoff = now - BUFFER_KEEP_MS;
    while (this.frames.length > 2 && this.frames[0].time < cutoff) {
      this.frames.shift();
    }
  }

  get latest(): Frame | undefined {
    return this.frames[this.frames.length - 1];
  }

  /** Drop every buffered frame — disconnect, or joining a new room. */
  clear(): void {
    this.frames.length = 0;
    this.intervals.length = 0;
    this.lastPushTime = 0;
    this.delayMs = INTERP_DELAY_MS;
  }

  /**
   * Interpolated (or briefly extrapolated) world at `now - delayMs`.
   * `rttMs` raises the delay floor slightly on high-latency links.
   */
  sample(now: number, excludeId?: string, rttMs = 0): RenderedWorld {
    if (this.frames.length === 0) return { players: [], enemies: [], coins: [] };

    const renderTime = now - this.effectiveDelay(rttMs);

    let older: Frame | undefined;
    let newer: Frame | undefined;
    for (let i = this.frames.length - 1; i >= 0; i--) {
      if (this.frames[i].time <= renderTime) {
        older = this.frames[i];
        newer = this.frames[i + 1];
        break;
      }
    }
    if (!older) {
      older = this.frames[0];
      newer = this.frames[1];
    }

    const newest = this.frames[this.frames.length - 1];

    // Past newest snapshot: coast on velocity instead of freezing.
    if (renderTime > newest.time) {
      const dtSec = Math.min(renderTime - newest.time, MAX_EXTRAP_MS) / 1000;
      return {
        players: extrapolate(newest.players, dtSec, excludeId),
        enemies: extrapolate(newest.enemies, dtSec),
        coins: extrapolatePlain(newest.coins, dtSec),
      };
    }

    const span = newer ? newer.time - older.time : 0;
    const t = span > 0 ? clamp((renderTime - older.time) / span, 0, 1) : 1;

    return {
      players: blend(older.players, (newer ?? older).players, t, excludeId),
      enemies: blend(older.enemies, (newer ?? older).enemies, t),
      coins: blendPlain(older.coins, (newer ?? older).coins, t),
    };
  }

  /** Delay actually used for rendering (jitter adaptive + RTT floor). */
  effectiveDelay(rttMs = 0): number {
    // One-way estimate nudges the floor; snapshots already include transit,
    // so only a fraction is applied — stops high-RTT links from dipping too
    // low when arrival looks steady.
    const rttFloor = clamp(rttMs * 0.15, 0, 40);
    return clamp(Math.max(this.delayMs, MIN_DELAY_MS + rttFloor), MIN_DELAY_MS, MAX_DELAY_MS);
  }

  private recomputeDelay(): void {
    const n = this.intervals.length;
    if (n < 3) {
      this.delayMs = INTERP_DELAY_MS;
      return;
    }
    let sum = 0;
    for (const v of this.intervals) sum += v;
    const avg = sum / n;
    let absDev = 0;
    for (const v of this.intervals) absDev += Math.abs(v - avg);
    const jitter = absDev / n;
    // Two intervals of buffer + jitter padding.
    this.delayMs = clamp(avg * 2 + jitter * 2, MIN_DELAY_MS, MAX_DELAY_MS);
  }
}

function index<T extends { id: string }>(list: T[]): Map<string, T> {
  const map = new Map<string, T>();
  for (const item of list) map.set(item.id, item);
  return map;
}

/**
 * Interpolate every body present in `source`, pairing it with its state in
 * `older`. Bodies that appeared this frame simply hold their new state.
 */
function blend<T extends Body>(
  older: Map<string, T>,
  source: Map<string, T>,
  t: number,
  excludeId?: string,
): Moving<T>[] {
  const out: Moving<T>[] = [];
  for (const [id, target] of source) {
    if (id === excludeId) continue;
    const from = older.get(id) ?? target;
    // Aim is a direction, so lerp then re-normalize; a degenerate blend keeps
    // the authoritative aim rather than collapsing to an arbitrary axis.
    const aim = normalize(lerp(from.ax, target.ax, t), lerp(from.ay, target.ay, t), {
      x: target.ax,
      y: target.ay,
    });
    out.push({
      ...target,
      x: lerp(from.x, target.x, t),
      y: lerp(from.y, target.y, t),
      ax: aim.x,
      ay: aim.y,
      moving: Math.hypot(target.vx, target.vy) > MOVING_SPEED,
    });
  }
  return out;
}

function blendPlain<T extends MovingBody>(
  older: Map<string, T>,
  source: Map<string, T>,
  t: number,
): Moving<T>[] {
  const out: Moving<T>[] = [];
  for (const [, target] of source) {
    const from = older.get(target.id) ?? target;
    out.push({
      ...target,
      x: lerp(from.x, target.x, t),
      y: lerp(from.y, target.y, t),
      moving: Math.hypot(target.vx, target.vy) > MOVING_SPEED,
    });
  }
  return out;
}

function extrapolate<T extends Body>(
  bodies: Map<string, T>,
  dtSec: number,
  excludeId?: string,
): Moving<T>[] {
  const out: Moving<T>[] = [];
  for (const [id, body] of bodies) {
    if (id === excludeId) continue;
    out.push({
      ...body,
      x: body.x + body.vx * dtSec,
      y: body.y + body.vy * dtSec,
      moving: Math.hypot(body.vx, body.vy) > MOVING_SPEED,
    });
  }
  return out;
}

function extrapolatePlain<T extends MovingBody>(bodies: Map<string, T>, dtSec: number): Moving<T>[] {
  const out: Moving<T>[] = [];
  for (const [, body] of bodies) {
    out.push({
      ...body,
      x: body.x + body.vx * dtSec,
      y: body.y + body.vy * dtSec,
      moving: Math.hypot(body.vx, body.vy) > MOVING_SPEED,
    });
  }
  return out;
}
