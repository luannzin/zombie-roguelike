/**
 * Local player: client-side prediction + server reconciliation.
 *
 * Flow per client tick:
 *   1. build an InputPacket with a fresh sequence number
 *   2. apply it locally right away (prediction) and keep it in `pending`
 *   3. send it
 * On every snapshot:
 *   4. snap authoritative state, drop inputs the server already processed,
 *      replay the rest (reconciliation)
 *   5. push the resulting positional delta into a decaying visual error so the
 *      correction is smoothed out instead of snapping the sprite
 */

import type { GameConfig, InputPacket, PlayerState } from '../net/protocol';
import { applyInput, type MovableState } from './simulation';
import type { TileMap } from './world';

/** Above this correction (world px) we snap instead of smoothing: respawn/teleport. */
const SNAP_THRESHOLD = 24;
/** Error decay rate; higher = corrections resolve faster but more visibly. */
const ERROR_DECAY = 14;

export class LocalPlayer {
  readonly state: MovableState;
  pending: InputPacket[] = [];
  sequence = 0;
  lastAck = 0;
  alive = true;
  hp: number;

  private errorX = 0;
  private errorY = 0;

  constructor(initial: PlayerState) {
    this.state = {
      x: initial.x,
      y: initial.y,
      vx: 0,
      vy: 0,
      ax: initial.ax,
      ay: initial.ay,
    };
    this.hp = initial.hp;
  }

  nextSequence(): number {
    this.sequence += 1;
    return this.sequence;
  }

  predict(input: InputPacket, world: TileMap, config: GameConfig): void {
    this.pending.push(input);
    if (this.alive) {
      applyInput(this.state, input, world, config, config.dt);
    } else {
      this.state.vx = 0;
      this.state.vy = 0;
      this.state.ax = input.aim.x;
      this.state.ay = input.aim.y;
    }
  }

  reconcile(server: PlayerState, ack: number, world: TileMap, config: GameConfig): void {
    this.lastAck = ack;
    this.alive = server.alive;
    this.hp = server.hp;

    const beforeX = this.state.x;
    const beforeY = this.state.y;

    this.state.x = server.x;
    this.state.y = server.y;
    this.state.vx = server.vx;
    this.state.vy = server.vy;

    this.pending = this.pending.filter((input) => input.sequence > ack);
    if (this.alive) {
      for (const input of this.pending) {
        applyInput(this.state, input, world, config, config.dt);
      }
    }

    this.errorX += beforeX - this.state.x;
    this.errorY += beforeY - this.state.y;
    if (Math.hypot(this.errorX, this.errorY) > SNAP_THRESHOLD) {
      this.errorX = 0;
      this.errorY = 0;
    }
  }

  decayError(dt: number): void {
    const k = Math.exp(-ERROR_DECAY * dt);
    this.errorX *= k;
    this.errorY *= k;
  }

  /** Smoothed position used for rendering and for the camera. */
  get renderX(): number {
    return this.state.x + this.errorX;
  }

  get renderY(): number {
    return this.state.y + this.errorY;
  }
}
