/**
 * The renderer's input contract.
 *
 * These types live apart from `renderer.ts` so individual layers can import
 * them without depending on the orchestrator (and without a cycle).
 *
 * Players and enemies are ONE type on purpose. They differ in presentation
 * (a player has a name label and a permanent health bar; an enemy has neither
 * until you hurt it) but not in structure, so the renderer sorts and draws a
 * single depth-ordered list and a new creature needs no new draw path.
 */

import type { Effects } from '../game/effects';
import type { TileMap } from '../game/world';
import type { GameConfig } from '../net/protocol';
import type { Camera } from './camera';

export type EntityKind = 'player' | 'enemy';

export interface DrawableEntity {
  id: string;
  kind: EntityKind;
  /** Sheet name in the SpriteBook ("player", "zombie", …). */
  sheet: string;
  /** Multiply tint over the sheet, or null to keep the art's own colours. */
  tint: string | null;
  /** Identity colour — name label and minimap dot. */
  color: string;
  /** Display name. Empty for enemies, which are never labelled. */
  name: string;
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
  /** Visual kick (world px). Recoil for players, attack lunge for enemies. */
  recoilX: number;
  recoilY: number;
  /**
   * Collision-box half extents. The sprite's bottom edge sits at
   * `y + halfHeight`, so entities of any size anchor with no special casing.
   */
  halfWidth: number;
  halfHeight: number;
}

/** World gold pickup — drawn under entities, spins forever. */
export interface DrawableCoin {
  id: string;
  x: number;
  y: number;
  animTime: number;
}

export interface RenderState {
  world: TileMap;
  camera: Camera;
  config: GameConfig;
  /** Players and enemies together; the renderer depth-sorts them. */
  entities: DrawableEntity[];
  coins: DrawableCoin[];
  effects: Effects;
  /** 0..1 local low-HP danger for screen vignette (0 = healthy). */
  danger: number;
  /** Elapsed seconds — drives heartbeat pulse. */
  time: number;
}
