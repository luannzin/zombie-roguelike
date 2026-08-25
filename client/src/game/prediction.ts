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

import { expDamp } from '../lib/math';
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
  /**
   * ON THE FLOOR, and not on a timer — see `PlayerState.down`. Kept beside
   * `alive` rather than derived from it because the two answer different
   * questions: `alive` gates input and prediction, `downed` is what the HUD
   * and the grade read to say the run is one blow from over.
   */
  downed = false;
  hp: number;
  /** Authoritative carried weight. Roster-only; prediction reads it every tick. */
  carryWeight = 0;
  /**
   * The owner's flattened skill mods, or null before the first roster.
   *
   * Mirror of `player.skills.mods` — speed and carry capacity are both
   * multiplied into movement server-side, so prediction has to know them or
   * a party that pulled Passo Leve rubber-bands for the rest of the run. It is
   * on the LOCAL player and nowhere else: remotes are interpolated, never
   * simulated, so their skills are none of this file's business.
   */
  mods: { speed: number; carry: number } | null = null;

  private errorX = 0;
  private errorY = 0;

  constructor(
    initial: PlayerState,
    config: GameConfig,
    resume?: { sequence: number; lastAck: number },
  ) {
    this.state = {
      x: initial.x,
      y: initial.y,
      vx: 0,
      vy: 0,
      ax: initial.ax,
      ay: initial.ay,
      // The breath the server is already holding for this body. A second
      // welcome (forest after camp) rebuilds this object mid-run, and a bar
      // that reset to full there would be a free sprint every zone.
      stamina: initial.st ?? config.staminaMax,
      winded: initial.wind ?? false,
      // Down. A body cannot arrive in a zone already blocking — the shield
      // goes up on a button, and the button is not held across a welcome.
      blockSpeed: 1,
      // Empty arms. `Room._step_carried` drops the pair when a carrier leaves
      // a zone, so a body that has just arrived is never holding one.
      carrySpeed: 1,
      // Clear. Nothing has hit this body on a map it has not stood on yet, and
      // the server clears the drag on every arrival for the same reason.
      stagger: 0,
    };
    this.hp = initial.hp;
    // A second welcome (forest after camp) rebuilds this object. Sequence is
    // the same counter the server has been acking since the lobby — starting
    // at 0 again makes every packet look like a replay and you cannot walk.
    this.sequence = resume?.sequence ?? 0;
    this.lastAck = resume?.lastAck ?? 0;
  }

  nextSequence(): number {
    this.sequence += 1;
    return this.sequence;
  }

  predict(input: InputPacket, world: TileMap, config: GameConfig): void {
    this.pending.push(input);
    if (this.alive) {
      applyInput(this.state, input, world, config, config.dt, this.carryWeight, this.mods ?? undefined);
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
    this.downed = server.down ?? false;
    this.hp = server.hp;
    // Breath is authoritative like position is: snap it, then let the replay
    // below spend the inputs the server has not seen yet. `stepStamina` is a
    // pure function of (running, moving), so the replay lands on the number
    // the server will hold a round trip from now.
    if (server.st !== undefined) this.state.stamina = server.st;
    this.state.winded = server.wind ?? false;
    // AUTHORITATIVE LIKE THE BREATH IS, and absent means zero rather than
    // means unchanged: the server omits the field the moment the drag runs
    // out, so treating absence as "keep what I had" would leave a body limping
    // forever after one hit.
    this.state.stagger = server.sg ?? 0;

    const beforeX = this.state.x;
    const beforeY = this.state.y;

    this.state.x = server.x;
    this.state.y = server.y;
    this.state.vx = server.vx;
    this.state.vy = server.vy;

    this.pending = this.pending.filter((input) => input.sequence > ack);
    if (this.alive) {
      for (const input of this.pending) {
        applyInput(this.state, input, world, config, config.dt, this.carryWeight, this.mods ?? undefined);
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
    const k = expDamp(ERROR_DECAY, dt);
    this.errorX *= k;
    this.errorY *= k;
  }

  /** Smoothed position at the last committed tick. */
  get renderX(): number {
    return this.state.x + this.errorX;
  }

  get renderY(): number {
    return this.state.y + this.errorY;
  }

  /**
   * Render position between two fixed ticks.
   *
   * The simulation only advances 30 times per second, so drawing `renderX`
   * directly makes movement look like 30 fps no matter how fast the display
   * refreshes. This advances a scratch copy of the state by the leftover
   * accumulator time using the same collision-aware `applyInput`, so the
   * sprite moves every frame and lands exactly where the next tick commits it.
   * Caller should pass **live** input (current keys/aim), not the last sent
   * packet, so mid-tick presses start motion this frame. Nothing here is
   * stored — reconciliation is unaffected.
   */
  subTickPosition(
    input: InputPacket | null,
    world: TileMap,
    config: GameConfig,
    remainder: number,
  ): { x: number; y: number } {
    if (!input || !this.alive || remainder <= 0) {
      return { x: this.renderX, y: this.renderY };
    }
    const scratch: MovableState = { ...this.state };
    applyInput(
      scratch, input, world, config, Math.min(remainder, config.dt), this.carryWeight,
      this.mods ?? undefined,
    );
    return { x: scratch.x + this.errorX, y: scratch.y + this.errorY };
  }
}
