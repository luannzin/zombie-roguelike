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
import type { GameConfig, LootRarity } from '../net/protocol';
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
  /**
   * Equipped overlay sheet, or null. Drawn on the body in the same facing
   * and walk frame, multiply-tinted with `tint` so it follows the wearer.
   * Always the backpack for players right now; enemies never wear one.
   */
  gear: string | null;
  /** Identity colour — name label and minimap dot. */
  color: string;
  /** Display name. Empty for enemies, which are never labelled. */
  name: string;
  /**
   * Camp only: this player is at the fire and has confirmed. Puts a tick on
   * their nameplate — the readout for "who are we still waiting on", answered
   * by looking at the party rather than at a counter in the corner.
   *
   * Always false outside the camp and always false for enemies.
   */
  ready: boolean;
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
   * 0..1 how much this enemy has noticed the party. Fills the hunt diamond
   * over its head; at 1 it is hunting. Always 0 for players.
   */
  awareness: number;
  /**
   * This client has seen this enemy while it was already alerting or hunting.
   * The hunt diamond may sit on the night only then — a hunter you never
   * laid eyes on stays a free unknown. Always false for players.
   */
  alertKnown: boolean;
  /**
   * Sight reach the server tests against, in world px, and the cone's full
   * width in degrees. Not drawn — the diamond is the tell. 0 for players.
   */
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

/** A collectable drop. Does not move; `visibility` hides it in the dark. */
export interface DrawableLoot {
  id: string;
  key: string;
  x: number;
  y: number;
  frame: number;
  rarity: LootRarity;
  /** Epic and legendary get the looping beam. */
  beam: boolean;
  visibility: number;
  animTime: number;
  /** Stable phase so neighbouring auras do not pulse together. */
  phase: number;
}

export interface RenderState {
  world: TileMap;
  camera: Camera;
  config: GameConfig;
  /** Players and enemies together; the renderer depth-sorts them. */
  entities: DrawableEntity[];
  coins: DrawableCoin[];
  loot: DrawableLoot[];
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
