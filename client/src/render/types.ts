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
import type { FovField } from './fov';

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
  /**
   * 0..1 how much of this entity is drawn at all.
   *
   * Enemies standing where the team has no light are 0 — genuinely not on
   * screen, not merely dimmed. Dimming leaves a readable silhouette, which
   * turns the darkness into a slight handicap instead of a real unknown, and
   * the whole point of the lantern is that something can be out there.
   * Teammates are always 1: you are never hunting your own party.
   */
  visibility: number;
  /**
   * 0..1 how much this enemy has noticed the party — the colour and the reach
   * of its sight cone, and whether it wears an alert mark. Always 0 for
   * players, who have no cone: `viewRange` 0 is what skips them.
   */
  awareness: number;
  /** Sight cone reach in world px and full width in degrees. 0 draws nothing. */
  viewRange: number;
  viewDegrees: number;
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
  /** Team light + explored memory. Null disables the darkness pass entirely. */
  fov: FovField | null;
  /** 0..1 local low-HP danger for screen vignette (0 = healthy). */
  danger: number;
  /** Elapsed seconds — drives the heartbeat pulse, sway, flicker and drift. */
  time: number;
  /** Seconds since the previous frame — for effects that integrate motion. */
  dt: number;
}
