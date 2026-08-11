/**
 * The renderer's input contract.
 *
 * These types live apart from `renderer.ts` so individual layers can import
 * them without depending on the orchestrator (and without a cycle).
 */

import type { Effects } from '../game/effects';
import type { TileMap } from '../game/world';
import type { GameConfig } from '../net/protocol';
import type { Camera } from './camera';

export interface DrawablePlayer {
  id: string;
  name: string;
  color: string;
  x: number;
  y: number;
  ax: number;
  ay: number;
  hp: number;
  maxHp: number;
  alive: boolean;
  moving: boolean;
  animTime: number;
  isLocal: boolean;
  /** 0..1 white flash intensity after taking a hit. */
  hitFlash: number;
  /** Visual kick opposite aim (world px). Does not affect simulation. */
  recoilX: number;
  recoilY: number;
}

export interface RenderState {
  world: TileMap;
  camera: Camera;
  config: GameConfig;
  players: DrawablePlayer[];
  effects: Effects;
  /** 0..1 local low-HP danger for screen vignette (0 = healthy). */
  danger: number;
  /** Elapsed seconds — drives heartbeat pulse. */
  time: number;
}
