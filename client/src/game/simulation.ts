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

export function applyInput(
  state: MovableState,
  input: InputPacket,
  world: TileMap,
  config: GameConfig,
  dt: number,
): void {
  const { dx, dy } = moveDir(input);
  state.vx = dx * config.moveSpeed;
  state.vy = dy * config.moveSpeed;

  const hw = config.playerHalfWidth;
  const hh = config.playerHalfHeight;
  state.x = world.moveAxis(state.x, state.y, hw, hh, state.vx * dt, 0);
  state.y = world.moveAxis(state.x, state.y, hw, hh, state.vy * dt, 1);

  state.ax = input.aim.x;
  state.ay = input.aim.y;
}
