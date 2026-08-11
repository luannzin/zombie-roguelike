/**
 * Remote players: snapshot buffer + entity interpolation.
 *
 * Remote entities are rendered INTERP_DELAY_MS in the past so there are always
 * two snapshots to interpolate between. No extrapolation: on a late packet the
 * last known state is held, which reads as a brief pause instead of a rubber
 * band. Zombies will use this exact same buffer.
 */

import type { PlayerState, SnapshotMessage } from '../net/protocol';

export const INTERP_DELAY_MS = 100;
const BUFFER_KEEP_MS = 1500;

interface Frame {
  tick: number;
  /** local receive time (performance.now) */
  time: number;
  players: Map<string, PlayerState>;
}

export interface RenderedPlayer extends PlayerState {
  moving: boolean;
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export class SnapshotBuffer {
  private frames: Frame[] = [];

  push(snapshot: SnapshotMessage, now: number): void {
    const players = new Map<string, PlayerState>();
    for (const p of snapshot.players) players.set(p.id, p);
    this.frames.push({ tick: snapshot.tick, time: now, players });

    const cutoff = now - BUFFER_KEEP_MS;
    while (this.frames.length > 2 && this.frames[0].time < cutoff) {
      this.frames.shift();
    }
  }

  get latest(): Frame | undefined {
    return this.frames[this.frames.length - 1];
  }

  /** Interpolated state of every player at `now - INTERP_DELAY_MS`. */
  sample(now: number, excludeId?: string): RenderedPlayer[] {
    if (this.frames.length === 0) return [];
    const renderTime = now - INTERP_DELAY_MS;

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

    const span = newer ? newer.time - older.time : 0;
    const t = span > 0 ? Math.min(1, Math.max(0, (renderTime - older.time) / span)) : 1;

    const out: RenderedPlayer[] = [];
    const source = newer ?? older;
    for (const [id, target] of source.players) {
      if (id === excludeId) continue;
      const from = older.players.get(id) ?? target;
      const speed = Math.hypot(target.vx, target.vy);
      let ax = lerp(from.ax, target.ax, t);
      let ay = lerp(from.ay, target.ay, t);
      const len = Math.hypot(ax, ay);
      if (len > 1e-4) {
        ax /= len;
        ay /= len;
      } else {
        ax = target.ax;
        ay = target.ay;
      }
      out.push({
        ...target,
        x: lerp(from.x, target.x, t),
        y: lerp(from.y, target.y, t),
        ax,
        ay,
        moving: speed > 1,
      });
    }
    return out;
  }
}
