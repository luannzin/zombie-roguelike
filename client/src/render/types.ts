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
import type { Payout } from '../game/payout';
import type { Grade } from './post/grade';

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
  /**
   * Breath, 0..`staminaMax`, drawn as a thinner bar UNDER the health bar.
   * Always 0/0 for enemies: a zombie does not get tired, and a second meter
   * over every body in a horde would bury the one that matters.
   */
  stamina: number;
  staminaMax: number;
  /** Bar spent, key locked out. Drains the colour out of the run bar. */
  winded: boolean;
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
  /**
   * Radians the weapon is swung off the aim, SCREEN space — a melee arc in
   * flight. Unlike `gunKick` it is never mirrored for a left-facing body:
   * a recoil means "up", which changes sign with the facing, and a swing
   * means "the blade is at this angle", which does not.
   */
  gunSwing: number;
  /** Pixels of slide back along aim — or out along the BLADE, mid-swing. */
  gunPump: number;
  /**
   * The POUR, or null for every body that is not emptying a bag into a
   * platform. `t` is 0..1 through the whole ceremony's grip: 0 is the pack on
   * the back where it always is, 1 is the pack held out at arm's length and
   * upside down. The entity pass takes the backpack out of `gear` while this
   * is set and draws it as something being HELD, because the one thing that
   * makes a pour read is that the bag stops being clothing.
   */
  pour: PourPose | null;
}

/** Where a poured backpack is between the shoulders and arm's length. */
export interface PourPose {
  /** 0 walk, 1 lift, 2 dump, 3 stow. Mirrors `Player.pour.phase`. */
  phase: number;
  /** 0 on the back, 1 held out and inverted. Eased by the game, not here. */
  grip: number;
  /** Seconds into the ceremony. Drives the shake while it is being emptied. */
  age: number;
  /** Which sheet the pack is. Taken out of `gear` for the duration. */
  sheet: string;
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
   * The zone's own light floor, 0..1 (`welcome.zone.ambient`). Zero in every
   * hostile place; the shop is the one exception. See `layers/darkness`.
   */
  ambient: number;
  /**
   * The shop, or null on every other map. Carries the fixtures, the merchant's
   * current clip, and which stall the local player is standing at.
   */
  store: StoreScene | null;
  /**
   * The night's platforms being lowered into the shop's apron, or null — which
   * is every frame outside the first few seconds of a shop arrival. See
   * `game/payout.ts`.
   */
  payout: Payout | null;
  /**
   * The party's balance. Read by the price tags, which mute a price the group
   * cannot meet — so it has to be here rather than fetched inside the layer.
   */
  balance: number;
  effects: Effects;
  /** Team light + explored memory. Null disables the darkness pass entirely. */
  fov: FovField | null;
  /**
   * The local player's LAMP as an object in the world, or null with the switch
   * off. Not the same statement as the fov's `lantern`: that one is how far
   * this player can SEE, this one is where the burning thing IS.
   *
   * It exists because the SHADOW field needs a source and the fov field has
   * none: a shadow has to know where the light is, not how far it reaches. A
   * held lamp sits slightly ahead of the body, down the aim — a light emitted
   * from the middle of a sprite throws that sprite's own shadow nowhere.
   */
  lamp: { x: number; y: number; power: number } | null;
  /**
   * 0..1 local low-HP danger. Only the FALLBACK vignette reads it now — on the
   * normal path danger is one layer in the grade stack like everything else,
   * so it composes with an extraction instead of being painted over one.
   */
  danger: number;
  /**
   * How the frame is finished: exposure, the wheels, bloom, shafts, fog, the
   * lens, the vignette, the grain. Resolved by `Game`'s `GradeStack` — the
   * renderer consumes it and never decides it, the same rule that keeps
   * gameplay state out of every other pass.
   */
  grade: Grade;
  /** Elapsed seconds — drives the heartbeat pulse, sway, flicker and drift. */
  time: number;
  /** Seconds since the previous frame — for effects that integrate motion. */
  dt: number;
}
