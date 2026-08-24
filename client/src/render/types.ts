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
import type { BossRow } from '../net/protocol';
import type { BossHit } from '../game/boss';
import type { TrailPoint } from './layers/boss-vfx';

export type EntityKind = 'player' | 'enemy';

/** One overlay sheet on a body, and whether it wears that body's colour. */
/**
 * `EnemyTypeConfig.rank` for a placed, crowned creature. The string is the
 * server's (`enemies.RANK_MINIBOSS`) and is mirrored here rather than
 * inferred, because the rank is a thing the catalog says and not a thing this
 * side works out from the numbers.
 */
export const RANK_MINIBOSS = 'miniboss';

export interface GearLayer {
  sheet: string;
  /** Multiply the wearer's `tint` through it. False for baked material art. */
  tint: boolean;
}

export interface DrawableEntity {
  id: string;
  kind: EntityKind;
  /** Sheet name in the SpriteBook ("player", "zombie", …). */
  sheet: string;
  /** Multiply tint over the sheet, or null to keep the art's own colours. */
  tint: string | null;
  /**
   * Overlay sheets, back-to-front. Drawn on the body in the same facing
   * and walk frame.
   *
   * EACH LAYER SAYS WHETHER IT WEARS THE BODY'S COLOUR, because two kinds of
   * thing ride a body and they want opposite treatment. A backpack is
   * greyscale and takes the wearer's `tint`: it is issued kit, and wearing
   * your own colour is the point of it. A steel plate is baked: its colour IS
   * its material, which is the entire armour ladder, and multiplying a
   * player's identity swatch through it would turn the rungs into whatever
   * that player happens to be. Enemy hats and clothes bake their own colour
   * too and ride an untinted enemy (`tint` is null), which is the same answer
   * arrived at from the other side.
   */
  gear: readonly GearLayer[];
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
  /**
   * ON THE FLOOR. Players only.
   *
   * The one state where `alive:false` still DRAWS. Everything else in this
   * renderer that is not alive is either gone or has become a corpse; a downed
   * player is neither, and has to stay on screen because a teammate finding
   * the body is the entire rescue mechanic. It plays its own one-shot sheet
   * (`player-down`) rather than a rotated walk frame — see the rule on
   * `drawCorpseSprites`.
   */
  downed: boolean;
  /** Seconds since this body went down. Drives the collapse timeline. */
  downAge: number;
  /**
   * 0..1 through a heal, or 0. Players only.
   *
   * Drawn as a RING over the head — see `drawHealRing`. It is on every body
   * and not only the local one, because a teammate standing still with a ring
   * closing over them is the clearest "do not expect them for two seconds"
   * this game can give.
   */
  healing: number;
  /**
   * True when `healing` is measuring a VAULT rather than a kit.
   *
   * The ring is the same widget for both — it answers "how much longer", which
   * is the same question — but it must not be the same COLOUR. A green ring
   * over somebody forcing a vault reads as healing, and a teammate you think
   * is topping up is a teammate you do not walk over to cover.
   */
  forcing: boolean;
  /**
   * 0..1 through a ranged windup, or 0. Creatures only.
   *
   * DRAWN AS A SWELL ON THE BODY rather than as a meter beside it. Everything
   * else the HUD tells you about a creature is a widget — a health bar, a hunt
   * diamond — and those are read by looking AT the thing. A telegraph has to
   * be read while looking somewhere else, out of the corner of the eye, which
   * is what a shape changing size does and what a small bar over a head does
   * not. See `drawWindup`.
   */
  windup: number;
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
  /**
   * What kind of thing this is, straight off `EnemyTypeConfig.rank`. `''` for
   * players and for everything the director spawns; `'miniboss'` puts a crown
   * over the head and keeps the health bar on at full.
   *
   * A STRING RATHER THAN A BOOLEAN because the rank belongs to the server's
   * catalog, and a `isMiniboss` flag here would be this side deciding what
   * the ranks are.
   */
  rank: string;
  /**
   * This creature is curled up with its eyes shut. It is drawn from another
   * sheet entirely (`EnemyTypeConfig.sleepSprite`), it wears no hunt diamond,
   * and its crown is unlit. Always false for players.
   */
  asleep: boolean;
  /**
   * Audio library prefix for this creature's own voice — the growl it makes
   * in the dark and the call it makes on finding you. Carried on the drawable
   * rather than looked up per sound, because the growl loop already has the
   * body in hand and re-resolving a type key per frame per creature is a
   * dictionary lookup a horde does not need. Empty for players.
   */
  voice: string;
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
   * World px the grip rides UP from the chest line: the walk under the
   * weapon, the breath, and the dip it comes out of the holster from.
   * Screen-space vertical, never rotated with the aim.
   */
  gunLift: number;
  /**
   * The action is standing OPEN this frame — slide back, port showing. The
   * entity layer swaps to the atlas's `cycleFrame` while it is true and to
   * the closed frame the moment it is not.
   */
  gunOpen: boolean;
  /** Barrel heat, 0..1. The bore glows and smokes off it. */
  gunHeat: number;
  /**
   * Hands on the weapon: 2 for a shoulder weapon, 1 for a sidearm or a blade.
   * The second arm is what makes a rifle read as a rifle rather than as a
   * long pistol somebody is waving.
   */
  gunHands: number;
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
  gear: readonly GearLayer[];
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

/** One creature projectile, mid-flight. `dx`/`dy` point it; it does not move here. */
export interface DrawableSpit {
  id: number;
  x: number;
  y: number;
  dx: number;
  dy: number;
  /** World px. The disc's own half-width, off the thrower's stat block. */
  radius: number;
}

/**
 * One thing an ultimate put in the air.
 *
 * THE SIBLING OF `DrawableSpit` AND NOT THE SAME TYPE, which is the whole
 * point: they run on one mechanic server-side (`projectiles.py`) and they are
 * two completely different pictures — a wet disc of bile coming at you, and an
 * arc of steel you threw. Merging them would put one draw function in front of
 * both and the first thing anybody would add to it is a branch on which kind
 * it was.
 */
export interface DrawableVolley {
  id: number;
  /** Which picture. `Volley.look` server-side; today only `slash`. */
  kind: string;
  x: number;
  y: number;
  dx: number;
  dy: number;
  /** World px of SWEEP — the arc's half-width, straight off the catalog row. */
  radius: number;
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
  /**
   * Creature projectiles in the air, straight off the snapshot.
   *
   * NOT depth-sorted with the bodies, and deliberately: a disc is the one
   * thing on screen the player must never lose behind a tree or a shoulder,
   * because losing it is taking the hit. It is drawn over everything for the
   * same reason a health bar is.
   */
  spits: DrawableSpit[];
  /**
   * What the party's ultimates put in the air. Same not-interpolated rule the
   * spits keep, and for the same reason — see `spits` above.
   */
  volleys: DrawableVolley[];
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
  /**
   * THE SAWYER, or null on every map but one.
   *
   * He is not in `entities` and that is deliberate: everything in that list is
   * a 16px body drawn out of one sheet by `drawEntity`, with a walk row picked
   * off velocity, a gear overlay, a held gun and a name label. He shares none
   * of it. What he does share is the DEPTH SORT — a player standing north of
   * him has to be drawn behind him — so he joins that as a prop-shaped row
   * rather than as an entity.
   */
  boss: DrawableBoss | null;
}

/** The boss, his crescents, his trail, and the flashes his blows leave. */
export interface DrawableBoss {
  row: BossRow;
  /** The bar's recent path, newest first. Drawn as a hot ribbon. */
  trail: readonly TrailPoint[];
  /** Live impact crescents. */
  hits: readonly BossHit[];
  /** 0..1, decaying. Painted as a white wash over the whole sprite. */
  hitFlash: number;
  /**
   * Screen-space wobble, in world px. He is a heavy thing and the only way a
   * 128px sprite says so is by not being perfectly still.
   */
  shakeX: number;
  shakeY: number;
}
