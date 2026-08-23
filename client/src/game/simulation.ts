/**
 * Movement simulation — mirror of server/app/simulation.py.
 *
 * This is the ONLY place the client is allowed to move the local player.
 * Prediction and reconciliation both call `applyInput`, so if this drifts from
 * the Python version the local player will visibly snap back.
 */

import type { GameConfig, InputPacket } from '../net/protocol';
import type { TileMap } from './world';

const SQRT1_2 = 0.7071067811865476;

export interface MovableState {
  x: number;
  y: number;
  vx: number;
  vy: number;
  ax: number;
  ay: number;
  /** Breath left, in the server's points. Mirror of `Player.stamina`. */
  stamina: number;
  /** Bar spent: SHIFT is refused until `staminaRecover` of it is back. */
  winded: boolean;
  /**
   * What the walk is multiplied by right now because of the shield. 1
   * whenever it is down. Mirror of `Player.block_speed`.
   *
   * A RESOLVED NUMBER RATHER THAN A LOOKUP, because this file is a
   * line-for-line mirror of `simulation.py` and movement code on either side
   * must not have to reach into a weapon catalog to know how fast a body is.
   * Both sides decide it in the same place — the frame the button is read —
   * and this just multiplies. See `Room.sync_block` and `Game.syncBlock`.
   */
  blockSpeed: number;
}

export function moveDir(input: InputPacket): { dx: number; dy: number } {
  let dx = (input.movement.right ? 1 : 0) - (input.movement.left ? 1 : 0);
  let dy = (input.movement.down ? 1 : 0) - (input.movement.up ? 1 : 0);
  if (dx !== 0 && dy !== 0) {
    dx *= SQRT1_2;
    dy *= SQRT1_2;
  }
  return { dx, dy };
}

/**
 * How much of `moveSpeed` a body gets at this carried weight.
 * Mirror of `carry_scale` in server/app/simulation.py.
 *
 * `maxWeight` overrides the config ceiling, because a skill moves it
 * (`skills.Mods.carry`, shipped on the roster as `mods.carry`). The curve is
 * still one decision; only where the free band ends slides.
 */
export function carryScale(
  weight: number,
  config: GameConfig,
  maxWeight?: number,
): number {
  const max = maxWeight ?? config.carryMaxWeight;
  const start = config.carrySlowStart;
  const atMax = config.carrySlowAtMax;
  const floor = config.carrySlowFloor;
  if (max <= 0) return 1;
  const ratio = weight / max;
  if (ratio <= start) return 1;
  const span = 1 - start;
  const t = span > 0 ? (ratio - start) / span : 1;
  const scale = 1 + (atMax - 1) * t;
  return scale < floor ? floor : scale;
}

/**
 * How heavy the walk *feels* past the free band. 0 at `carrySlowStart`,
 * 1 at max weight, and it keeps climbing if they go over. Footprints and
 * dust read this; speed uses `carryScale`.
 */
export function carryBurden(
  weight: number,
  config: GameConfig,
  maxWeight?: number,
): number {
  const max = maxWeight ?? config.carryMaxWeight;
  const start = config.carrySlowStart;
  if (max <= 0) return 0;
  const ratio = weight / max;
  const span = 1 - start;
  if (span <= 0) return ratio > start ? 1 : 0;
  return Math.max(0, (ratio - start) / span);
}

/**
 * Whether this body is actually RUNNING this tick.
 * Mirror of `running` in server/app/simulation.py.
 *
 * SHIFT is a request, not a state: a body standing still is not running, and a
 * body that spent the bar is locked out until it has recovered.
 */
export function isRunning(state: MovableState, input: InputPacket, moving: boolean): boolean {
  return moving && input.sprint && !state.winded && state.stamina > 0;
}

/**
 * Spend or refill the breath, and work the exhaustion latch.
 * Mirror of `step_stamina` in server/app/simulation.py.
 *
 * Stateless apart from the latch, which is what lets reconciliation replay it:
 * snap `stamina` / `winded` from the authoritative row, replay the pending
 * inputs through here, and the client lands on the number the server holds.
 */
export function stepStamina(
  state: MovableState,
  running: boolean,
  moving: boolean,
  config: GameConfig,
  dt: number,
): void {
  const max = config.staminaMax;
  if (running) {
    state.stamina -= config.staminaDrain * dt;
    if (state.stamina <= 0) {
      state.stamina = 0;
      state.winded = true;
    }
    return;
  }
  const regen = moving ? config.staminaRegenWalk : config.staminaRegenRest;
  state.stamina = Math.min(max, state.stamina + regen * dt);
  if (state.winded && state.stamina >= max * config.staminaRecover) {
    state.winded = false;
  }
}

export function applyInput(
  state: MovableState,
  input: InputPacket,
  world: TileMap,
  config: GameConfig,
  dt: number,
  weight = 0,
  /**
   * The owner's flattened skill mods. Mirror of `player.skills.mods` on the
   * server — a default of 1 / undefined is a body with no skills, which is
   * every body on the opening night.
   */
  mods?: { speed: number; carry: number },
): void {
  const { dx, dy } = moveDir(input);
  const moving = dx !== 0 || dy !== 0;
  const running = isRunning(state, input, moving);
  stepStamina(state, running, moving, config, dt);

  let speed = config.moveSpeed * (mods?.speed ?? 1) * carryScale(weight, config, mods?.carry);
  if (running) speed *= config.sprintSpeed;
  // THE SHIELD IS THE LAST TERM AND IT MULTIPLIES EVERYTHING. A body behind
  // one is slow whatever else is true about it — sprinting behind a riot
  // shield is still slower than walking without one, which is the whole
  // reason raising it is a decision rather than a posture.
  speed *= state.blockSpeed;
  state.vx = dx * speed;
  state.vy = dy * speed;

  const hw = config.playerHalfWidth;
  const hh = config.playerHalfHeight;
  state.x = world.moveAxis(state.x, state.y, hw, hh, state.vx * dt, 0);
  state.y = world.moveAxis(state.x, state.y, hw, hh, state.vy * dt, 1);

  state.ax = input.aim.x;
  state.ay = input.aim.y;
}
