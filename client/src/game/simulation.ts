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
 */
export function carryScale(weight: number, config: GameConfig): number {
  const max = config.carryMaxWeight ?? 10;
  const start = config.carrySlowStart ?? 0.2;
  const atMax = config.carrySlowAtMax ?? 0.55;
  const floor = config.carrySlowFloor ?? 0.35;
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
export function carryBurden(weight: number, config: GameConfig): number {
  const max = config.carryMaxWeight ?? 10;
  const start = config.carrySlowStart ?? 0.2;
  if (max <= 0) return 0;
  const ratio = weight / max;
  const span = 1 - start;
  if (span <= 0) return ratio > start ? 1 : 0;
  return Math.max(0, (ratio - start) / span);
}

export function applyInput(
  state: MovableState,
  input: InputPacket,
  world: TileMap,
  config: GameConfig,
  dt: number,
  weight = 0,
): void {
  const { dx, dy } = moveDir(input);
  const speed = config.moveSpeed * carryScale(weight, config);
  state.vx = dx * speed;
  state.vy = dy * speed;

  const hw = config.playerHalfWidth;
  const hh = config.playerHalfHeight;
  state.x = world.moveAxis(state.x, state.y, hw, hh, state.vx * dt, 0);
  state.y = world.moveAxis(state.x, state.y, hw, hh, state.vy * dt, 1);

  state.ax = input.aim.x;
  state.ay = input.aim.y;
}
