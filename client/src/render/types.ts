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
import type { BloodStain } from '../game/entity-visuals';
import type { TileMap } from '../game/world';
import type { GameConfig, LootRarity } from '../net/protocol';
import type { Camera } from './camera';
import type { FovField } from './fov';
import type { StoreScene } from './layers/store';

export type EntityKind = 'player' | 'enemy';

export interface DrawableEntity {
  id: string;
  kind: EntityKind;
  /** Sheet name in the SpriteBook ("player", "zombie", …). */
  sheet: string;
  /** Multiply tint over the sheet, or null to keep the art's own colours. */
  tint: string | null;
  /**
   * Overlay sheets, back-to-front. Drawn on the body in the same facing
   * and walk frame. Multiply-tinted with `tint` when one is set — the
   * backpack follows the wearer; enemy hats and clothes bake their own
   * colour and ride an untinted enemy (`tint` is null).
   */
  gear: readonly string[];
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
   * Wounds this body is wearing, oldest first. Stamped on the sprite in the
   * entity pass; positions are normalised to the sprite, so the renderer
   * scales them by whatever sheet it is drawing.
   */
  stains: readonly BloodStain[];
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
  /** Visual kick (world px). Recoil for players, attack lunge / hit shove for enemies. */
  recoilX: number;
  recoilY: number;
  /** Radians of hit tilt around the feet. 0 unless a heavy round just landed. */
  hitSpin: number;
  /**
   * Collision-box half extents. The sprite's bottom edge sits at
   * `y + halfHeight`, so entities of any size anchor with no special casing.
   */
  halfWidth: number;
  halfHeight: number;
  /** Equipped gun key, or null when the hand is empty. */
  weapon: string | null;
  /** Radians of muzzle climb, sprite-local (up is negative before the left-flip). */
  gunKick: number;
  /** Pixels of slide back along aim. */
  gunPump: number;
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
  /** Epic and legendary get the looping beam; the rest get motes. */
  beam: boolean;
  visibility: number;
  animTime: number;
  /** Stable phase so neighbouring auras do not pulse together. */
  phase: number;
  /**
   * Sprite multiplier, 1 for everything the world scatters.
   *
   * Only a condensed core out of an overfed rift sets it, and it is
   * proportional to what was overpaid — so "how much did we bank" is legible
   * from the size of the thing lying in the grass, before anyone walks close
   * enough to read a tooltip.
   */
  scale: number;
}

/**
 * A dead enemy left on the floor. The fall is a real death-sheet timeline;
 * after that it is a prone sprite plus a growing blood pool. Hidden in the
 * dark — a corpse you cannot see is not a free tracker.
 */
export interface DrawableCorpse {
  id: string;
  x: number;
  y: number;
  sheet: string;
  gear: readonly string[];
  ax: number;
  ay: number;
  /** Killing blow. The body falls along this. */
  dx: number;
  dy: number;
  stains: readonly BloodStain[];
  age: number;
  visibility: number;
  halfHeight: number;
}

export interface RenderState {
  world: TileMap;
  camera: Camera;
  config: GameConfig;
  /** Players and enemies together; the renderer depth-sorts them. */
  entities: DrawableEntity[];
  coins: DrawableCoin[];
  loot: DrawableLoot[];
  corpses: DrawableCorpse[];
  /** Night coat. Drives rain/fog in the atmosphere pass. */
  weather: string;
  /**
   * The shop, or null on every other map. Carries the fixtures, the merchant's
   * current clip, and which stall the local player is standing at.
   */
  store: StoreScene | null;
  /**
   * The party's balance. Read by the price tags, which mute a price the group
   * cannot meet — so it has to be here rather than fetched inside the layer.
   */
  balance: number;
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
