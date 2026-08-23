/**
 * Wire protocol types. Mirrors server/app/protocol.py — keep both in sync.
 * All gameplay tuning arrives from the server in `welcome.config`; never
 * hardcode a gameplay constant here.
 *
 * One socket carries both phases of a room: `hello` + `lobby` while the party
 * gathers, then `welcome` and the snapshot stream once the host starts. There
 * is no second connection — see `hooks/useRoomSession`.
 *
 * `{type:"ready"}` toggles ready at the campfire. When everyone is ready the
 * snapshots flip `departing` and the server walks the party out; a second
 * `welcome` is the forest. That welcome carries `ack` so the client keeps
 * numbering inputs above what the server already processed — resetting to 0
 * makes every later packet look like a replay.
 *
 * `{type:"drop","slot"}` tosses a bag cell onto the ground near the feet.
 * The server places it; the client never sends a position.
 *
 * `{type:"break","id"}` smashes a crate. The server validates range; a
 * shot that hits the crate's sprite box does the same.
 */

export interface MovementInput {
  up: boolean;
  down: boolean;
  left: boolean;
  right: boolean;
}

export interface InputPacket {
  type: 'input';
  sequence: number;
  movement: MovementInput;
  aim: { x: number; y: number };
  shoot: boolean;
  /** Switch state. Battery/flicker stay client-local; remotes only need on/off. */
  lantern: boolean;
  /**
   * SHIFT. A REQUEST to run: the server decides what it buys against the
   * breath the body has left, and so does prediction — see
   * `game/simulation.ts` `isRunning`.
   */
  sprint: boolean;
  /** Hotbar slot in hand. -1 is holstered. Empty slots are treated as -1. */
  held: number;
  /**
   * RIGHT MOUSE. A REQUEST to raise the shield, exactly as `sprint` is a
   * request to run: the server decides what it buys against what is in the
   * hand and whether the shield is still in one piece, and so does prediction
   * — see `Room.sync_block` and `game/simulation.ts`.
   */
  block: boolean;
}

export interface PingPacket {
  type: 'ping';
  t: number;
}

/** Leave the lobby and start the run. Ignored from anyone but the host. */
export interface StartPacket {
  type: 'start';
}

/** Toggle ready at the campfire. Ignored unless you are in the camp, near the fire. */
export interface ReadyPacket {
  type: 'ready';
}

/** Pick up a world drop. Server ignores it unless you are close enough. */
export interface CollectPacket {
  type: 'collect';
  id: string;
}

/** Toss a bag slot onto the ground near your feet. Server places it. */
export interface DropPacket {
  type: 'drop';
  slot: number;
}

/** Smash a crate. Server ignores it unless you are close enough. */
export interface BreakPacket {
  type: 'break';
  id: string;
}

/**
 * Press an extraction console: wake the platform, load it, or launch it.
 * `id` is the pad; omitted means nearest in range. Server ignores it unless
 * you are close enough, alive, and the pad will take the press.
 */
export interface ActivatePacket {
  type: 'activate';
  id?: string;
}

/**
 * Take the weapon off a shop table. `id` is the stall; omitted means nearest
 * in range. Server ignores it unless you are close enough, alive, in the
 * store, the table is unsold, the party can afford it, and the belt has a
 * cell or a legal trade.
 */
export interface BuyPacket {
  type: 'buy';
  id?: string;
}

/**
 * Pull the upgrade machine's lever. No id: there is exactly one cabinet in the
 * clearing, so naming it would be a field that could only ever hold one value.
 *
 * The server refuses silently when the feet are out of range, when no level is
 * owed, or while somebody else's pull is still running — all three are things
 * the HUD already knows, so the prompt is what says which and this packet is
 * simply not sent.
 */
export interface SpinPacket {
  type: 'spin';
}

export type ClientMessage =
  | InputPacket
  | PingPacket
  | StartPacket
  | ReadyPacket
  | CollectPacket
  | BreakPacket
  | ActivatePacket
  | BuyPacket
  | SpinPacket
  | DropPacket;

/**
 * Canonical scale, decided server-side (see server/app/config.py):
 *   tile 32x32 · sprite frame 32x48 · collision box 18x14 (feet footprint)
 * Position is the CENTRE of the collision box; the sprite's bottom edge sits
 * at `y + playerHalfHeight`.
 */
export interface GameConfig {
  tickRate: number;
  dt: number;
  tileSize: number;
  spriteWidth: number;
  spriteHeight: number;
  playerHalfWidth: number;
  playerHalfHeight: number;
  /** Radius of the vertical full-body hit capsule (stadium). */
  playerHitRadius: number;
  moveSpeed: number;
  maxHp: number;
  fireCooldown: number;
  shotRange: number;
  shotDamage: number;
  muzzleOffset: number;
  /** Every enemy stat block, keyed by type. Mirrors server/app/enemies.py. */
  enemyTypes: Record<string, EnemyTypeConfig>;
  /** Processed asset folder for world gold pickups. */
  coinSprite: string;
  /** Processed asset folder for the pack worn on a player's back. */
  backpackSprite: string;
  /** Omnidirectional glow every player carries, in tiles. */
  visionAmbientTiles: number;
  /** Reach of the directional lantern cone, in tiles. */
  visionLanternTiles: number;
  /** Full width of the lantern cone, in degrees. */
  visionConeDegrees: number;
  /**
   * SIGHT SYMMETRY: how far a creature sees a body, as a fraction of
   * `visionLanternTiles` — with the lamp off, and with it on.
   *
   * `render/fov.ts` draws its naked-eye and lit washes at exactly these
   * reaches, which is what makes the rule true: an enemy sees a shape as far
   * as the shape sees it. Mirrors `ENEMY_VIEW_DARK_SCALE` /
   * `ENEMY_VIEW_LIT_SCALE` in server/app/config.py — and it is a SHIPPED
   * number rather than a copied one, because a mismatch here has no symptom
   * except a game that is quietly wrong.
   */
  enemyViewDarkScale: number;
  enemyViewLitScale: number;
  /**
   * Share of floor tiles `layers/terrain` puts a bush on. A RULE, not a paint
   * setting: `ai.look` re-derives the same tiles from the map seed and cuts a
   * creature's reach over them, so this decides how much cover a forest has.
   * What it cuts the reach TO stays server-side — the client never asks.
   */
  bushChance: number;
  /** How far a bonfire throws light, in tiles. The camp's only light source. */
  campfireLightTiles: number;
  /**
   * The boss's name and what he was. Shipped rather than kept client-side:
   * `server/app/boss.py` owns him, and the HUD renders what the world says it
   * contains. Required (not optional) like every other key `client_config`
   * always sends — see `test_config_parity.py`.
   */
  bossName: string;
  bossTitle: string;
  /**
   * Every move's CLOCK and reach, keyed by clip name.
   *
   * The client puts a trail on the nose of the bar and needs to know where in
   * its swing the bar is; these are the server's own timings, which are in
   * turn the art's (see `boss._clip`). Shipped rather than copied because a
   * trail timed off a second opinion drifts off the sprite it is supposed to
   * be leaving.
   */
  bossMoves: Record<string, BossMove>;
  /** The thrown crescent's geometry. Sizes the throw's trail. */
  bossCrescent: BossCrescentSpec;
  /**
   * His hit capsule, in world px — the three numbers `game/combat.ts` wants.
   *
   * Shipped for ONE reason and it is worth writing down: `predictShot` draws
   * the local player's tracer the frame the trigger goes down, against a
   * target list it builds itself, and the boss was not in it. The server had
   * him in `targets` from the day he shipped, so the damage always landed —
   * but the round visibly flew THROUGH the biggest body in the game, with no
   * stop, no marker and no number, and a shot that looks like a miss is a
   * miss as far as the player is concerned.
   */
  bossHit: BossHitSpec;
  /** The fire plus the seat ring, in tiles: nothing grows inside it. */
  hearthTiles: number;
  /** Seat ring radii, in tiles. Elliptical — see server/app/camp.py. */
  ringTilesX: number;
  ringTilesY: number;
  /** How close to the fire (tiles, feet to flame) the ready prompt answers. */
  readyRangeTiles: number;
  /** How close to a drop (tiles, feet to item) E will collect. */
  lootCollectTiles: number;
  /**
   * How close to an object (tiles) E will use it. Measured feet to the
   * nearest point of the FOOTPRINT, not to the contact point — a bus is four
   * tiles long and a centre-to-centre reach would refuse the prompt at the
   * exact doors the art is pointing at.
   */
  crateBreakTiles: number;
  /** Fallback shot box, in tiles. Per-object boxes ride `objects` and win. */
  crateHitWTiles: number;
  crateHitHTiles: number;
  /** How close to the extraction console (tiles, feet to contact) E activates. */
  riftActivateTiles: number;
  /** How close to a shop table (tiles, feet to contact) E will buy. */
  storeBuyTiles: number;
  /** How far the weapon on that table lifts while somebody is in range, in tiles. */
  storeLiftTiles: number;
  /** How close to the upgrade machine (tiles, feet to contact) E pulls. */
  storeSpinTiles: number;
  /** The upgrade machine's clock. One source: `server/app/machine.py`. */
  machine: MachineTimingConfig;
  /** Catalog of skills. Keyed by key; `frame` indexes the skill icon atlas. */
  skills: Record<string, SkillConfig>;
  /** The extraction platform's clock. One source: `server/app/rift.py`. */
  rift: RiftTimingConfig;
  /** Catalog of world loot. Keyed by item key; `frame` indexes the loot atlas. */
  loot: Record<string, LootItemConfig>;
  /** Combat stats for guns. Keyed by the same keys as loot rows with pocket `hotbar`. */
  weapons: Record<string, WeaponConfig>;
  /** The object vocabulary: sheet, verb, prompt and hit box per kind. */
  objects: Record<string, ObjectDef>;
  /** Ammunition: the calibres, their boxes and how much of each fits. */
  ammo: AmmoConfig;
  /**
   * Catalog of wearable armour. Keyed by piece key, same keys as the loot
   * rows with pocket `worn`. Mirrors `server/app/armor.py` — the client has
   * no numbers of its own here: the durability bar, the overlay sheet and the
   * tooltip all read this.
   */
  armor: Record<string, ArmorConfig>;
  /**
   * The worn slots, top to bottom. The HUD stacks its rows in this order and
   * a `lootPickups` row with `dest: "worn"` indexes it, so the order is a
   * contract rather than a convenience.
   */
  armorSlots: string[];
  /** Portuguese for each slot, for a HUD row and a tooltip line. */
  armorSlotNames: Record<string, string>;
  /**
   * What share of blows land on each slot. The player sprite's own anatomy —
   * see `armor.COVERAGE` — so it is a fact about the art rather than a tuning
   * knob. The HUD needs it to say what a whole set actually stops.
   */
  armorCoverage: Record<string, number>;
  /** Starting bag size. A later upgrade grows it. */
  inventorySlots: number;
  /** Gun belt size. */
  hotbarSlots: number;
  /**
   * How many of those cells are GUN cells. The rest is the blade cell — see
   * `bladeSlot` — and the split is what tells the client that key 3 is never
   * empty and that a lâmina REPLACES rather than stows.
   */
  gunSlots: number;
  /** Index of the blade cell. Always the last one; never empty. */
  bladeSlot: number;
  /**
   * What the blade cell falls back to. Needed for exactly one thing: a knife
   * replaced by a better lâmina does NOT land on the floor — it is the
   * promise that the cell is full, not an object the party owns — so the
   * pickup prompt must not offer it as something you are giving up.
   */
  startingBlade: string;
  /** Weight the walk is tuned around. The bag may go past this. */
  carryMaxWeight: number;
  /** Fraction of max weight that is still full speed. */
  carrySlowStart: number;
  /** Speed multiplier at exactly max weight. */
  carrySlowAtMax: number;
  /** Slowest the walk is allowed to get, even overweight. */
  carrySlowFloor: number;
  /**
   * Running. SHIFT multiplies the walk by `sprintSpeed` and spends
   * `staminaDrain` points a second doing it; letting go pays back
   * `staminaRegenWalk` on the move or `staminaRegenRest` standing still, and a
   * bar spent to zero refuses the key until `staminaRecover` of it is back.
   * Mirrors `SPRINT_SPEED` / `STAMINA_*` in server/app/config.py.
   */
  sprintSpeed: number;
  staminaMax: number;
  staminaDrain: number;
  staminaRegenWalk: number;
  staminaRegenRest: number;
  staminaRecover: number;
  /**
   * What the walk is multiplied by while a blow's drag is still on the body,
   * and how long one blow leaves it there. Mirrors `HIT_STAGGER_*` in
   * server/app/config.py; `stepStagger` in game/simulation.ts is the mirror
   * that spends it.
   *
   * The client needs the SCALE because prediction multiplies by it every
   * frame. It needs the TIME only to draw with — nothing local ever starts a
   * stagger, because only the server sees a swing land.
   */
  hitStaggerScale: number;
  hitStaggerTime: number;
}

export type LootRarity = 'common' | 'uncommon' | 'rare' | 'epic' | 'legendary';

/**
 * One wearable piece. Mirrors `server/app/armor.ArmorDef`.
 *
 * MATERIAL SETS THE NUMBERS, SLOT SETS WHERE THE HITS LAND — every field here
 * but `slot` and `sheet` is a function of the material's tier, which is why
 * a player who has learnt what leather does has learnt it for all three
 * slots.
 */
export interface ArmorConfig {
  name: string;
  /** `head` / `body` / `legs`. Indexes `GameConfig.armorSlots`. */
  slot: string;
  /** `cloth` / `leather` / `steel` / `kevlar`. */
  material: string;
  /** The material's Portuguese name — "pano", "couro", "aço", "kevlar". */
  materialName: string;
  /** 1..4. The one number the rest is derived from. */
  tier: number;
  /**
   * DAMAGE POINTS taken off every blow that lands on this part. Flat, not a
   * fraction — see `server/app/armor.py`: a proportional mitigation cannot be
   * printed as a number without naming the blow it is a proportion of, and
   * the moment a stat card names one it is anchored on one creature.
   */
  armor: number;
  /** Points of damage a fresh one absorbs before it comes apart. */
  maxHp: number;
  /** Kilos. On the WALK, never in the bag — see `Game.moveWeight`. */
  weight: number;
  value: number;
  rarity: LootRarity;
  /**
   * The overlay sheet drawn on the body. Registered to the player's own
   * 16x16 grid and drawn by the same `blitGear` that draws the backpack and
   * a zombie's hat — armour is visible through the system that was already
   * there.
   */
  sheet: string;
}

export interface LootItemConfig {
  name: string;
  rarity: LootRarity;
  frame: number;
  weight: number;
  value: number;
  /**
   * Where a collect puts it, and there are four containers. Weapons are
   * `hotbar` (a gun into a gun cell, a lâmina into the blade cell);
   * valuables are `bag`; rounds are `ammo` and armour is `worn`, and neither
   * of those takes a slot anywhere. An `ammo` row's `value` is 0 on purpose:
   * ammunition is upkeep, not cargo, and an extraction platform will not
   * carry it.
   */
  pocket?: 'bag' | 'hotbar' | 'ammo' | 'worn';
  /** `ammo` rows only: which calibre this fills, and by how many rounds. */
  ammo?: string;
  rounds?: number;
}

/**
 * One interactive object kind, from `server/app/crates.py`.
 *
 * The client has no table of its own — see `game/objects.ts`. `sheet` plus
 * `variant` locate the art (several kinds share one sheet: every vehicle is a
 * row of `vehicle.png`), `verb` decides whether E breaks or opens it and
 * whether a bullet counts, and `label` is the line the prompt shows.
 */
export interface ObjectDef {
  sheet: string;
  variant: number;
  verb: 'break' | 'open';
  label: string;
  /** Footprint width in tiles. A vehicle is 4; almost everything else is 1. */
  tilesW: number;
  /** Shot box, in world pixels, bottom-centred on the contact. */
  hitW: number;
  hitH: number;
}

/** Calibres, which catalog row is a box of each, and the reserve caps. */
export interface AmmoConfig {
  types: string[];
  boxes: Record<string, string>;
  max: Record<string, number>;
}

export type WeaponKind =
  | 'pistol'
  | 'smg'
  | 'shotgun'
  | 'rifle'
  | 'sniper'
  | 'melee'
  | 'shield'
  | string;

/** What a combo step reads as. `cut` is the finisher. */
export type ComboKind = 'slash' | 'cut' | string;

/**
 * One beat of a melee chain. Mirrors `ComboStep` in server/app/weapons.py.
 *
 * The GEOMETRY (`reach`, `arcDegrees`) rides the config rather than the
 * swing event, the same way an enemy's sight cone does: it never changes
 * between ticks, and the client needs it to draw an arc for a swing it
 * predicted before any server row existed.
 */
export interface ComboStepConfig {
  kind: ComboKind;
  damage: number;
  cooldown: number;
  /** World px from the body centre to the far edge of the arc. */
  reach: number;
  /** Full width of the arc, in degrees. */
  arcDegrees: number;
  /** Seconds the chain stays open after this step. 0 ends it. */
  window: number;
  maxTargets: number;
  /** Body lunge along aim, world px. */
  lunge: number;
  trauma: number;
  /** +1 / -1 — which way the arc travels. The two slashes cross. */
  sweep: number;
  /**
   * HALF-WIDTH of the blade's travel, in radians — half of `arcDegrees`.
   *
   * The held sprite tracks the drawn white path edge for edge (see
   * `EntityVisuals.startSwing`), so this and `arcDegrees` are two readings
   * of one number and a disagreement puts the steel outside its own arc.
   */
  swing: number;
  /** Seconds the blade takes to travel the arc, wind-up included. */
  swingTime: number;
  /** World px the grip is thrust out along the blade at mid-swing. */
  swingThrust: number;
}

/** The swinging half of a weapon. Absent on everything that shoots. */
export interface MeleeConfig {
  steps: ComboStepConfig[];
}

/** Combat block for one weapon. Mirrors server/app/weapons.py. */
export interface WeaponConfig {
  name: string;
  kind: WeaponKind;
  ammo: string;
  /**
   * Damage of ONE ray. On the shotgun that is one PELLET — `shotDamage` is
   * what a whole trigger pull is worth against a single body.
   */
  damage: number;
  /** Rays cast per trigger pull. 1 on everything but the shotgun. */
  pellets: number;
  /** Full width of the pellet cone, in degrees. Meaningless at 1 pellet. */
  spreadDegrees: number;
  /** `damage * pellets` — the number a player would quote for the weapon. */
  shotDamage: number;
  fireCooldown: number;
  range: number;
  muzzle: number;
  noise: number;
  aimDelay: number;
  /**
   * RELEASE IS THE SHOT. With this set the weapon never fires while the
   * button is down — holding it aims (`scopeZoom`) and letting go fires,
   * and only if the hold lasted `aimDelay`. Mirrors `Room.handle_attack`;
   * a client that fired on the press would predict a shot the server never
   * took and then have to un-draw it.
   */
  fireOnRelease: boolean;
  scopeZoom: number;
  /** Playback rate for the shot sample. Under 1 is a bigger gun. */
  shotPitch: number;
  kick: number;
  trauma: number;
  gunKick: number;
  gunPump: number;
  tracerLife: number;
  tracerWidth: number;
  flash: number;
  casings: number;
  lightRadius: number;
  lightLife: number;
  /**
   * Present only on melee weapons, and it is what the client branches on —
   * not the `kind` string. A second blade is a catalog row and no code.
   */
  melee?: MeleeConfig;
  /**
   * THE BLOCK. Present on shields and absent on everything that attacks —
   * the third thing a belt cell can hold, and the client dispatches on which
   * block a row carries exactly as `Room.handle_attack` does. A row with
   * this has no trigger at all.
   */
  shield?: ShieldConfig;
}

/** Mirrors `server/app/weapons.ShieldDef`. */
export interface ShieldConfig {
  /** Points of damage it eats before it comes apart. */
  hp: number;
  /** Full width of the protected arc, in degrees, centred on the AIM. */
  arcDegrees: number;
  /** What the walk is multiplied by while it is up. */
  speed: number;
}

/** One world drop. `k` keys into `GameConfig.loot`. */
export interface LootState {
  id: string;
  k: string;
  x: number;
  y: number;
  /**
   * PER-DROP OVERRIDES, and the catalog is the default for all three.
   *
   * Everything the world scatters is worth what its `LootItemConfig` row says,
   * which is why the catalog ships once in `welcome.config` and the wire only
   * carries a key. A condensed core out of an overfed pad is worth whatever
   * was overpaid into it, so those numbers travel with the object instead.
   */
  v?: number;
  w?: number;
  /** Sprite multiplier. Only a core sets it; everything else draws at 1. */
  s?: number;
  /**
   * WHAT IS LEFT OF IT. Only a piece of armour that has been WORN sets this —
   * a cracked steel plate taken off to put a fresh one on has to still be
   * cracked when somebody picks it back up. A piece that has never been worn
   * omits it and arrives whole.
   */
  hp?: number;
}

/** A drop that just entered a player's pocket. */
export interface LootPickupEvent {
  id: string;
  by: string;
  k: string;
  x: number;
  y: number;
  /** The index it landed on, in whichever container took it. */
  slot: number;
  /**
   * Where it landed. `hotbar` is a weapon; `ammo` is rounds that went into a
   * reserve — `slot` then names the belt cell holding the weapon they feed,
   * so the sprite flies onto the gun it topped up; `worn` is a piece of
   * armour and `slot` indexes `config.armorSlots`. Omitted for the pocket.
   */
  dest?: 'bag' | 'hotbar' | 'ammo' | 'worn';
}

/**
 * One blow landing on a plate or on the shield.
 *
 * THE ROSTER CARRIES THE DURABILITY AND THIS CARRIES THE EVENT — the same
 * split `kills` keeps from `enemies`. A client that missed a packet must
 * never replay a piece breaking, so the bar is resynced from `PlayerMeta` and
 * this is only ever juice: a spark off steel, a crack, and the one frame the
 * piece came apart on.
 */
export interface ArmorHitEvent {
  /** The body wearing it. */
  by: string;
  /** `head` / `body` / `legs`, or the literal `shield`. */
  slot: string;
  /** The piece. Keys into `config.armor`, or into `config.weapons`. */
  k: string;
  /** What it stopped. On the shield that is the whole blow. */
  dmg: number;
  /** What is still on it. 0 on the frame it broke. */
  left: number;
  /** The one frame it came apart on. */
  broke: boolean;
  x: number;
  y: number;
}

/**
 * One item leaving a backpack and landing on a platform's deck.
 *
 * The load is a POUR now, not a press: the server tips the pocket out one unit
 * at a time on its own clock and sends one of these per item, so the bag
 * emptying on the HUD and the sprites piling up on the deck are the same
 * event. `n` is the pad's running pile index and it is authoritative — it is
 * what makes two players watching one pour watch one pile.
 */
export interface PourEvent {
  /** The body doing it. */
  by: string;
  /** The pad being loaded. */
  r: string;
  /** Catalog key — the atlas frame and the rarity. */
  k: string;
  /** What it paid toward the quota. */
  v: number;
  /** Drawn size. Only a condensed core sets it. */
  s?: number;
  /** How many items were already on that deck. The pile's index. */
  n: number;
  /** Where the body was standing, in world pixels (feet). */
  x: number;
  y: number;
}

/**
 * Where the room is, and how that place behaves. Mirrors server/app/zones.py.
 *
 * `title` / `subtitle` are fiction the server authors — "Preparação" over
 * "Dia 1", later "Dia 3" over a rolled clock ("21:44 da noite") — so a new
 * level announces itself with no client change. The two booleans are rules,
 * not flavour, and the client must not infer either of them from the map.
 */
export interface ZoneInfo {
  /** Stable identity for one arrival. A change is what replays the intro. */
  key: string;
  kind: 'camp' | 'forest' | 'store' | 'arena' | string;
  day: number;
  title: string;
  subtitle: string;
  /** Enemies spawn and weapons fire. */
  hostile: boolean;
  /** The lantern switch works. False in the camp: the bonfire is the light. */
  lantern: boolean;
  /**
   * How much light this PLACE has of its own, 0..1, under the darkness pass.
   *
   * Zero everywhere a player can be killed — a forest with a floor under its
   * darkness is a forest with no reason to own a lantern. The shop is the one
   * exception and it is what the shop is for: walking out of a black wood into
   * somewhere with visible edges is the reward, and the contrast only exists
   * because everywhere else is at zero.
   */
  ambient?: number;
  /**
   * Night coat, rolled with the clock. `clear` is a dry forest; `rain` and
   * `fog` are the same map in a different coat, so day 2 can feel like
   * somewhere else without a new generator. Camp is always `clear`.
   */
  weather?: 'clear' | 'rain' | 'fog' | string;
}

/**
 * One creature's stat block, authored server-side in `enemies.py`. Everything
 * the client needs to draw it, shoot it and show its numbers — nothing here is
 * ever hardcoded on this side.
 */
export interface EnemyTypeConfig {
  key: string;
  /** Processed asset folder: /<sprite>/sheet.png. */
  sprite: string;
  maxHp: number;
  damage: number;
  xp: number;
  /** Most coins this creature can drop. The roll happens server-side per kill. */
  goldMax: number;
  hitRadius: number;
  spriteHeight: number;
  halfWidth: number;
  halfHeight: number;
  /**
   * The sight cone the server tests against: reach in world px, full width in
   * degrees, both measured off the creature's own facing (`ax`/`ay`). Not
   * drawn — the hunt diamond is the tell. The numbers still ride the config
   * so a client that needs them (reach vs the local lamp) does not invent
   * them.
   *
   * Two reaches, because sight is symmetric and the dark is shared: `viewRange`
   * is how far it makes out a shape, `viewRangeLit` how far it makes out
   * somebody carrying a lit lantern. The server picks per target by that
   * player's switch, including while it hunts — killing the lamp shortens
   * a hunter too.
   */
  viewRange: number;
  viewRangeLit: number;
  viewDegrees: number;
  /** Body sheets rolled on spawn. `EnemyState.v` indexes this. */
  variants?: string[];
  /** Hat overlay sheets. `EnemyState.hat` indexes this. */
  hats?: string[];
  /** Clothes overlay sheets. `EnemyState.cloth` indexes this. */
  clothes?: string[];
  /**
   * What KIND of thing this is, for the HUD only: `''` for everything the
   * director spawns, `'miniboss'` for a placed one. It drives the crown over
   * the head and the always-visible health bar, and nothing else — the
   * simulation has no concept of a rank.
   *
   * DATA RATHER THAN A KEY THE CLIENT KNOWS. The whole point is that the
   * second miniboss is a stat block in `enemies.py` and no change here.
   */
  rank?: string;
  /**
   * The sheet to draw this creature with while `EnemyState.sl` is set —
   * curled up, breathing, eyes shut. Empty for everything that never sleeps,
   * which is every zombie in the game.
   */
  sleepSprite?: string;
  /**
   * WHAT IT SOUNDS LIKE, as a library prefix: this side asks for
   * `<voice>-idle`, `<voice>-alert` and `<voice>-death`. A creature's whole
   * vocabulary is one string on its stat block, exactly the way `sprite` is
   * its whole art — so a new creature that sounds like something else is a
   * server change and nothing here.
   */
  voice?: string;
}

/**
 * One placed scenery piece: `[kindIndex, x, y, variant, flip, layer]`.
 *
 * Compact arrays rather than objects because a map ships a hundred of these
 * and the keys would cost more than the data. `kindIndex` reads
 * `MapPayload.propKinds`; `x`/`y` are world pixels — a contact point for a
 * standing prop, a centre for a flat one; `variant` is taken modulo the
 * sheet's frame count; `flip` mirrors horizontally; `layer` is 0 flat / 1
 * standing.
 */
export type PropRow = [
  kind: number,
  x: number,
  y: number,
  variant: number,
  flip: number,
  layer: number,
];

/**
 * One light the MAP owns: `[x, y, radiusTiles, kind]` in world pixels.
 *
 * `kind` indexes a tone table on the client (0 lamp, 1 ember, 2 beacon). It is
 * a NUMBER rather than a colour because the point is that the server decides
 * what a light MEANS and the client decides what that looks like — the
 * extraction beacon is going to arrive through this same row.
 */
export type LightRow = [x: number, y: number, radiusTiles: number, kind: number];

export type EntranceSide = 'e' | 'w' | 'n' | 's';
export type EntranceState = 'open' | 'sealing' | 'gone';

/**
 * The forest's black corridor, the camp exit continued. Mouth is where the
 * party walks onto floor; dir is into the woods; back is the map edge.
 */
export interface EntrancePayload {
  side: EntranceSide;
  mouth: [number, number];
  back: [number, number];
  dir: [number, number];
  state: EntranceState;
  t: number;
  /**
   * Contact points of the torches marking the way out, in world pixels.
   *
   * Only an EXIT has them — an arrival is a corridor you are already inside
   * and about to lose. Two ranks of two straddling the centreline, ordered the
   * way the party walks past them. Placed by `entrance._torches` rather than
   * hashed, because a torch standing inside a trunk is a light with no visible
   * source and only the server knows which tiles survived the carve.
   */
  torches?: [number, number][];
}

/** One run objective. The HUD mirrors this list and never invents a row. */
export interface QuestState {
  id: string;
  label: string;
  have: number;
  need: number;
  done?: boolean;
  /** Dangerous work — the HUD paints the count in the danger tone. */
  risk?: boolean;
  /** Progress is catalog gold — the HUD draws the coin badge next to it. */
  gold?: boolean;
}

export interface MapPayload {
  width: number;
  height: number;
  tileSize: number;
  /**
   * Generator seed. The FOREST — soil, grass, ferns, litter, which prop
   * variant a tile gets — is hashed from this plus the tile coordinate rather
   * than transmitted, so texture costs four bytes and never repeats.
   */
  seed: number;
  /** Tile kinds — see game/world.ts. */
  tiles: number[][];
  /**
   * The other half of the world, and the opposite kind of thing: the SCENES
   * the server placed (`server/app/scenery.py`). These cannot be re-derived
   * from the seed because their whole value is that the pieces know about each
   * other — the blood is at the doorway, the tracks lead into it. Optional
   * because a locally generated map (the title screen's clearing) has none.
   */
  propKinds?: string[];
  props?: PropRow[];
  /**
   * Anything on this map that is still burning: a lamp at a cabin door, embers
   * in a camp that has only just gone out. These feed the same light field the
   * bonfires do, so a scene with one is visible from across the dark — which
   * is what turns it from decoration into a place you decide to walk to.
   */
  lights?: LightRow[];
  /**
   * Breakable crates pulled out of scenery. Drawn as standing props; smashed
   * ones leave this list and play their sheet, then the tile becomes floor.
   */
  crates?: CrateState[];
  /**
   * Extraction points. Absent or empty on a map without any — every camp,
   * and any forest the generator could not fit a 7x7 plot into.
   */
  rifts?: RiftPayload[];
  /**
   * Forest arrival corridor. Absent on the camp. Geometry is placed at
   * generation; `state` is rewritten as the woods swallow the path.
   */
  entrance?: EntrancePayload | null;
  /**
   * Extraction exit, carved when the feed quota is paid. Absent until then.
   * Same shape as `entrance`.
   */
  egress?: EntrancePayload | null;
  /**
   * The shop's fixtures. Absent on every map that is not the store.
   *
   * On the MAP payload rather than the snapshot for the same reason a pad's
   * geometry is: where the merchant stands and where his tables are is decided
   * once, when the corridor is built. Only what SELLS moves, and that rides
   * `SnapshotMessage.stands`.
   */
  store?: StorePayload | null;
}

/**
 * One table in the shop, and the weapon lying on it.
 *
 * `x` is the CENTRE of the table and `y` its contact — the row its feet stand
 * on — so the client can bottom-anchor the table sprite and centre the stock
 * over it from the same pair. Which pixel row the weapon rests at comes off
 * the store atlas (`table.topY[v]`), not from here: the tables are three
 * different heights on purpose and the offset belongs to the art.
 */
export interface StandState {
  id: string;
  /** Weapon catalog key — reads `welcome.config.weapons` / `.loot`. */
  k: string;
  price: number;
  x: number;
  y: number;
  /** Which table sheet frame this stall uses. */
  v: number;
  /**
   * Bought. The row STAYS — the gap where a weapon was is information, and a
   * table that vanished when somebody took its gun would make the corridor
   * look shorter every time the party spent something.
   */
  sold?: boolean;
}

/**
 * One AMMUNITION CRATE on the shop's south wall. Mirror of `store.AmmoBox`.
 *
 * IT IS NOT A STALL AND IT DOES NOT SELL OUT. A table holds one specific
 * weapon and empties when somebody takes it; a crate is a SUPPLY, and the row
 * stays exactly as it is however many boxes come out of it — which is what
 * stops the fourth player in a room walking into the night dry.
 *
 * A ROW APPEARING IS AN EVENT. Which calibres are on the wall is a fact about
 * the party's belts rather than about the map, so the server sends the list
 * again whenever it grows, and a crate the client has not seen before is the
 * one it drops in (see `render/layers/store.ts`). Nothing on the wire says
 * "this one is new": the client already knows what it was drawing last frame,
 * and a flag would be a second opinion that can arrive twice.
 */
export interface AmmoBoxState {
  id: string;
  /** Calibre key — indexes `welcome.config.ammo.max` and a weapon's `ammo`. */
  c: string;
  /** The loot catalog row this fills, e.g. `ammo_rifle` — name and icon. */
  k: string;
  price: number;
  /** Rounds ONE purchase hands over. The same box the forest scatters. */
  n: number;
  x: number;
  y: number;
  /**
   * Frame on the ammunition sheet — the calibre's index in the server's own
   * `weapons.AMMO_TYPES`. Shipped rather than derived here so the art's frame
   * order stays one side's fact.
   */
  v: number;
}

/**
 * One skill, out of `welcome.config.skills`. Mirror of `skills.catalog_payload`.
 *
 * The server only ever names a skill by KEY — on the roster and on a spin
 * event — and everything drawable about it is here, exactly the way the loot
 * catalog works. `frame` indexes `/skills/sheet.png`.
 */
export interface SkillConfig {
  name: string;
  rarity: LootRarity;
  /** One line stating the effect, in the player's language. */
  blurb: string;
  frame: number;
  /** How many copies still move the number. Past it a pull still counts. */
  cap: number;
}

/**
 * The upgrade machine's timeline, in seconds from the lever coming down.
 * Mirror of `server/app/machine.py`; the client flies the whole four seconds
 * off these plus the one spin event, on its own render clock.
 */
export interface MachineTimingConfig {
  armTime: number;
  spinUp: number;
  reelOne: number;
  reelTwo: number;
  /**
   * Extra spin on the THIRD reel, per rarity. This is the anticipation, and it
   * is the only part of the clock that varies: two reels have already agreed
   * and the last one is taking its time, longer the better the pull was.
   */
  reelHold: Record<string, number>;
  ejectLag: number;
  ejectFlight: number;
  holdTime: number;
  resetTime: number;
  reachTiles: number;
}

/**
 * Where the shop's fixtures stand. Placed by `server/app/store.py`.
 *
 * Only what is FITTED is here. The masonry itself is not — the walls and the
 * floor are TILE KINDS on the ordinary grid (`BRICK` / `TILEFLOOR`), so the
 * client's collision, its lighting and its terrain bake all pick them up with
 * nothing on this payload, and the building can never disagree with the map it
 * is standing in. The apron outside is an ordinary forest map for the same
 * reason: soil hashed from the seed, `props` and `lights` like anywhere else.
 *
 * EVERY LIST HERE IS OPTIONAL AND THE CLIENT DRAWS NOTHING FOR A MISSING ONE.
 * Same rule the wagon and the machine already had: a payload from a server
 * that predates a fixture is a shop without that fixture, not an error. It is
 * what lets a fixture be added on the server first and drawn a commit later.
 */
export interface StorePayload {
  merchant: [number, number];
  /**
   * Contact point of his CART, parked out in the yard — not in the shop. See
   * the design doc: a covered cart says he drives and a building says he does
   * not, so the cart is what he ARRIVED in and the shop is what he unloaded
   * into.
   */
  wagon?: [number, number];
  /**
   * THE COUNTER, as one row per tiling section: `[x, y, kind]`, where kind is
   * 0 elbow, 1 running east, 2 running south.
   *
   * A LIST RATHER THAN A POINT, because the counter is an L now and the shape
   * of the L is a layout decision. Shipping sections means the server can
   * lengthen an arm by adding an offset and the client needs to know nothing;
   * shipping one point and one big sprite would have put the geometry in the
   * art, where nothing can flood-fill it.
   */
  counter?: [number, number, number][];
  stands: StandState[];
  /**
   * The ammunition crates, one per calibre somebody in the room is carrying.
   * Absent on a map nobody has walked into yet — the room fills this in as it
   * reads the belts, so an empty list is the normal opening state and not a
   * shop that has run out.
   */
  boxes?: AmmoBoxState[];
  /** Torch contact points, all OUTDOORS: `[x, y, variant]`. */
  torches: [number, number, number][];
  /** Contact point of the shop's door, in the middle of its south wall. */
  door?: [number, number];
  /** Wall shelving behind the counter: `[x, y, variant]`. Decoration. */
  shelves?: [number, number, number][];
  /** Shop-floor decoration crates: `[x, y, variant]`. None of them opens. */
  crates?: [number, number, number][];
  /**
   * The mats: `[x, y, variant]` per mat, CENTRES not contacts — they lie flat
   * and are baked into the ground canvas.
   */
  rugs?: [number, number, number][];
  /**
   * The hanging lamps, at their FLOOR CONTACTS: `[x, y]`.
   *
   * The contact, not the bulb, because that is what the renderer sorts by and
   * hangs from — how far above it the lamp body sits is `lamp.hangY` off the
   * store atlas, which is art. Sending the bulb's position would put the same
   * number on the wire and in the manifest and let the two drift.
   */
  lamps?: [number, number][];
  /**
   * Contact point of the upgrade machine, on the north-west arc. Absent on a
   * map built before the cabinet existed, which the layer treats as "no
   * machine here" rather than as an error.
   */
  machine?: [number, number];
  /**
   * His own gear: `[x, y, variant]` per piece, all of it out in the YARD
   * around his cart.
   *
   * It is on the store payload rather than in `props` because it is his, the
   * same way the tables and the torches are. Nothing here is interactive; the
   * art is drawn roped and padlocked so the silhouette says so.
   */
  kit?: [number, number, number][];
  /**
   * THE APRON: one row per platform that came home tonight, as
   * `[x, y, value]` — where it sets down and what it was carrying.
   *
   * Empty on a night nobody extracted, which is the one case with nothing to
   * show. The BALANCE is not derived from this: the server credited it when
   * the party crossed the corridor, and everything the client does with these
   * rows is presentation. See `client/src/game/payout.ts`.
   */
  payout?: [number, number, number][];
}

/**
 * One lever pull, for the frame it happened on — and the whole ceremony.
 *
 * Everything the next four seconds look like is decided from this row: which
 * reel face the strip lands on, how long the third one holds, what colour the
 * canister is, and which icon is stamped on it. The roll is already resolved
 * server-side, so the reels are TELLING the player something rather than
 * deciding it while they watch.
 */
export interface SpinEvent {
  /** Who pulled. Only their own client flies the canister into the HUD tray. */
  by: string;
  /** Skill key — index it against `config.skills`. */
  k: string;
  r: LootRarity;
  /** Copies held after this one. The tray tile counts up to it. */
  n: number;
  /** Pulls still banked afterwards. */
  left: number;
  /**
   * What the party paid, when this pull was BOUGHT rather than owed. Absent on
   * a level's free spin, which is most of them.
   */
  cost?: number;
  x: number;
  y: number;
}

/** One purchase, for the frame it happened on. */
export interface BuyEvent {
  id: string;
  by: string;
  k: string;
  price: number;
  /** The index it landed on, in whichever container took it. */
  slot: number;
  /**
   * Where the sprite is going. Absent (a weapon off a table) means the belt
   * cell in `slot`; `"ammo"` is a crate-load, which flies at the GUN it just
   * fed — `slot` is that weapon's cell and no cell was spent; `"worn"` is a
   * piece of armour off a table, and `slot` indexes `config.armorSlots`.
   */
  dest?: 'hotbar' | 'ammo' | 'worn';
  /** Rounds handed over. Ammunition only. */
  n?: number;
  x: number;
  y: number;
}

/**
 * The extraction point's geometry plus its state at the moment the map was
 * sent. Placed by `server/app/rift.py`, which ships ABSOLUTE world positions
 * rather than the plot offsets — the client never re-derives the arrangement,
 * for the same reason it never re-derives where a cabin's door is.
 */
export interface RiftPayload {
  id: string;
  tx: number;
  ty: number;
  plot: number;
  /** Middle of the deck's footprint: the imprint, the light, the core drop. */
  x: number;
  y: number;
  /** Contact point of the skid — the row its beams stand on. */
  deck: [number, number];
  /** The console you press. */
  console: [number, number];
  /** The torch that marks the pad. Burning from the moment the map is built. */
  torch: [number, number];
  /**
   * The bearing the drones come in on, in radians, and the one the loaded
   * platform leaves on. Rolled by the map, and the departure is the approach
   * CONTINUED — the flight is one pass, not a round trip.
   */
  approach: number;
  heading: number;
  lightTiles: number;
  /** Scene-light kind. 2 is `beacon` — see `theme/palette.ts`. */
  lightKind: number;
  state: 'dormant' | 'charging' | 'open' | 'spent';
  /** Seconds into the sequence. */
  t: number;
  /** When the launch begins, in the same clock as `t`. Absent while holding. */
  closeAt?: number | null;
  /** Catalog value put into THIS pad, and what it asked for. */
  fed?: number;
  need?: number;
  /** Quota settled and the pickup not yet called. */
  ready?: boolean;
}

/**
 * The extraction platform's clock, in seconds, straight off
 * `server/app/rift.py`.
 *
 * Every number here is a claim about a machine: how long four rotors take to
 * reach lift speed, how long a rope takes to come straight, how long a tonne
 * of iron argues with the ground before it lets go. The client animates the
 * rig off them and the server ends the sequence on them, so there is one
 * clock.
 */
export interface RiftTimingConfig {
  consoleLag: number;
  openAt: number;
  lightTiles: number;
  /** How many corners the lift takes, and so how many aircraft answer. Four. */
  drones: number;
  /**
   * THE PICKUP. The client flies the whole thing off these plus the single
   * `closeAt` on the wire — sirens alone for `liftAlarm`, then drone `i` leaves
   * the treeline at `liftAlarm + i * droneStagger`, crosses in `droneInbound`,
   * and spends `droneDrop` paying its line down to its corner. `tiedAt` is
   * when the last of them is on and the lift can start.
   */
  liftAlarm: number;
  droneStagger: number;
  droneInbound: number;
  droneDrop: number;
  tiedAt: number;
  /**
   * Then the lift: straining against ground that will not let go, breaking
   * free, and the flight out. `breakAt` is also the moment the deck's tiles
   * become walkable — the server patches them on that tick.
   */
  liftStrain: number;
  liftBreak: number;
  liftClimb: number;
  breakAt: number;
  /**
   * The window, and the way it ends. NULL means NEVER — the platform waits
   * until a player launches it. Not `Infinity`: that is not valid JSON and
   * would throw on parse, taking the whole config with it.
   */
  openTime: number | null;
  collapseAt: number | null;
  collapseTime: number;
  spentAt: number | null;
}

/**
 * One live interactive object.
 *
 * `t` is the TYPE key — `barrel`, `ambulance`, `altar` — and it indexes
 * `config.objects`. `v` is the row inside that type's sheet, carried on the
 * wire rather than looked up so a break event can still draw an object that
 * has already left the live list.
 */
export interface CrateState {
  id: string;
  t: string;
  x: number;
  y: number;
  v: number;
  flip: number;
  /** 1 once it has been used. It stays on the map, holding its last frame. */
  o?: number;
}

export type CrateDrop = 'empty' | 'coin' | 'item';

/** An object that was just used. Juice for the sheet and the empty-wind puff. */
export interface CrateBreakEvent {
  id: string;
  t: string;
  x: number;
  y: number;
  v: number;
  flip: number;
  drop: CrateDrop;
  /** Catalog key when `drop` is `item`. */
  k?: string;
  /** Set when what came out was a passenger rather than loot. */
  amb?: number;
}

/**
 * One player, as a 30 Hz snapshot row: only what moves.
 *
 * Identity and the score board are NOT here — they live in `PlayerMeta`,
 * arrive on the snapshot's `roster` a few times a second, and are cached by
 * the client. Nothing on this side may assume a name is on a snapshot.
 */
export interface PlayerState {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  /** normalized aim direction */
  ax: number;
  ay: number;
  /**
   * Last input sequence the server processed FOR THIS PLAYER. It rides on the
   * row instead of the snapshot so the server serialises one payload for the
   * whole room; only your own row's `seq` means anything to you.
   */
  seq: number;
  /** Whether this player's lantern switch is on. */
  lantern: boolean;
  hp: number;
  alive: boolean;
  /**
   * ON THE FLOOR, AND NOT COMING BACK ON A TIMER.
   *
   * `alive` says whether this body acts; `down` says WHY it stopped. A death
   * in the camp or the shop is `alive:false` with a two-second respawn behind
   * it — a fumble. A death in a hostile zone is `alive:false` AND `down`, with
   * no timer at all: the only thing that stands it back up is the party
   * reaching the next zone, and if nobody is left standing to get them there
   * the run is over (`wipe` below).
   *
   * The client draws a body on the floor rather than an absence, and the HUD
   * counts how many of the party are still up — which is the only warning
   * anybody gets that the run is one blow from ending.
   */
  down: boolean;
  /** Camp only: standing at the fire and confirmed. */
  ready?: boolean;
  /** Hotbar index in hand. -1 is holstered. */
  held?: number;
  /** True while a scoped gun is being held to fire. */
  ads?: boolean;
  /**
   * Breath left, in `config.staminaMax` points. On the TICK row rather than
   * the roster because it moves every tick a key is down, and because the bar
   * under the health bar is drawn over every body, not only your own.
   */
  st?: number;
  /**
   * The exhaustion latch: the bar was spent to zero and SHIFT is refused until
   * `config.staminaRecover` of it is back. Omitted while there is breath left,
   * which is almost always.
   */
  wind?: boolean;
  /**
   * Seconds of drag left from the last blow that connected — see
   * `MovableState.stagger`. On the tick row beside the breath and for the same
   * two reasons: it moves every tick it exists, and every client draws it,
   * because a staggered body lurches for whoever is looking at it. Omitted at
   * zero, which is almost always.
   */
  sg?: number;
  /**
   * THE SHIELD IS UP. On the tick row and not the roster because it is a
   * POSE: every client draws a raised shield over every body that has one up,
   * and a five-hertz pose would let a player watch a blow land on a shield
   * that had not come up yet. Omitted when down, which is almost always.
   */
  blk?: boolean;
  /**
   * Which beat of a POUR this body is on — 0 walk, 1 lift, 2 dump, 3 stow.
   * Absent for everybody who is not emptying their pocket into a platform,
   * which is everybody almost all of the time. The client runs its own clock
   * inside a beat; the beat is the only thing it cannot know for itself.
   */
  pour?: number;
}

/**
 * Who a player is and how they are doing — everything that does not change
 * from tick to tick. Sent on `welcome.player` and on the snapshot `roster`.
 */
export interface PlayerMeta {
  id: string;
  name: string;
  color: string;
  kills: number;
  deaths: number;
  /** Lifetime xp. The server also sends it pre-split into the level below. */
  xp: number;
  gold: number;
  level: number;
  xpInLevel: number;
  xpToLevel: number;
  /** The pocket. Slots, contents and current weight. */
  inv?: InventoryState;
  /** The gun belt. Slots and which one is in hand. */
  guns?: HotbarState;
  /**
   * Rounds by calibre, every calibre, including the zeroes.
   *
   * On the 5 Hz roster rather than the snapshot: the client spends its own
   * rounds locally as it predicts the trigger, so this is the resync, not the
   * counter. A run opens at all zeroes because it opens with no gun.
   */
  ammo?: Record<string, number>;
  /**
   * WHAT THIS BODY IS WEARING. Worn slots only — an absent key is a bare
   * part, not a null.
   *
   * On the roster and not the tick row because a plate changes when somebody
   * picks one up or one comes apart, which is a handful of times a night.
   * Every client gets it rather than only the owner, because armour is DRAWN
   * (`DrawableEntity.gear`): a teammate's helmet is a thing you can see from
   * across a clearing.
   */
  armor?: Record<string, ArmorPieceState>;
  /**
   * What is left of the shield on the belt, or absent when there is none.
   *
   * Not inside `armor`, because you hold it rather than wear it, and not on
   * `guns`, because a belt cell holds a KEY and this is state. The POSE —
   * whether it is up right now — is on the tick row (`blk`), because that
   * moves every time a finger does.
   */
  shield?: ArmorPieceState;
  /**
   * What the levels bought: `{k, n}` per skill, sorted by catalog order.
   *
   * On the roster for the same reason `ammo` is, taken further — a stack
   * changes once a day, in a shop, in front of a machine. Names and icons are
   * not here: `config.skills` has them, keyed by `k`.
   */
  skills?: SkillStackState[];
  /** Pulls owed to the machine. One per level gained, spendable any night. */
  spins?: number;
  /**
   * The flattened numbers the OWNER's client has to mirror. Movement and carry
   * scale are predicted locally and the health bar and the battery are drawn
   * locally, so a client that had to guess at its own ceiling would draw the
   * wrong bar for exactly the frames somebody just changed it.
   */
  mods?: PlayerMods;
}

/**
 * One thing with a durability on it: a worn plate, or the shield.
 *
 * It carries its own ceiling rather than looking one up, which is what lets
 * the same shape describe a helmet (whose numbers live in `config.armor`) and
 * a riot shield (whose numbers live in `config.weapons[k].shield`).
 */
export interface ArmorPieceState {
  k: string;
  hp: number;
  max: number;
}

/** One skill and how many copies of it are held. */
export interface SkillStackState {
  k: string;
  n: number;
}

/** Mirror of `skills.Mods.payload()` — see `server/app/skills.py`. */
export interface PlayerMods {
  /** Move speed multiplier, on top of the carry scale. */
  speed: number;
  /** This body's health ceiling. `config.maxHp` is only where a run OPENS. */
  maxHp: number;
  /** Carry capacity in kg. Replaces `config.carryMaxWeight` for this player. */
  carry: number;
  /** Extra bag cells already granted. The server has grown the pocket. */
  slots: number;
  /** How much longer the lantern lasts. The battery is client-local. */
  lamp: number;
}

/**
 * One bag slot on the wire. `n` is the stack.
 *
 * `v` / `w` / `s` are the same per-item overrides `LootState` carries, kept on
 * the slot so a condensed core is still worth what it was worth after it has
 * been picked up. A slot carrying them never stacks — see
 * `server/app/inventory.py`.
 */
export interface InventorySlotState {
  k: string;
  n: number;
  v?: number;
  w?: number;
  s?: number;
}

export interface InventoryState {
  cap: number;
  bag: Array<InventorySlotState | null>;
  w: number;
}

export interface HotbarState {
  cap: number;
  slots: Array<string | null>;
  held: number;
}

/** A player with everything known about them: `welcome` and roster rows. */
export type PlayerFull = PlayerState & PlayerMeta;

/**
 * A live enemy. Per-type constants are NOT repeated here — `t` keys into
 * `GameConfig.enemyTypes`, so a 30 Hz snapshot stays small.
 */
export interface EnemyState {
  id: string;
  /** Enemy type key, e.g. "zombie". */
  t: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  /** normalized facing — and so where its sight cone points (server-side) */
  ax: number;
  ay: number;
  hp: number;
  /**
   * 0..1 how much of the party this enemy has noticed. It fills while somebody
   * stands in its sight cone, and is pinned at 1 for as long as it is hunting.
   * The hunt diamond is drawn from this: hidden when idle, filling while it
   * works you out, full once it has committed.
   */
  aw: number;
  /** Body variant index into `enemyTypes[t].variants`. 0 when omitted. */
  v?: number;
  /** Hat overlay index into `enemyTypes[t].hats`. Absent means none. */
  hat?: number;
  /** Clothes overlay index into `enemyTypes[t].clothes`. Absent means none. */
  cloth?: number;
  /**
   * 1 while this creature is ASLEEP. The only piece of the server's AI mode
   * that ships, and it ships because it is the only one that changes what is
   * drawn: a sleeper uses `enemyTypes[t].sleepSprite` instead of its body
   * sheet, wears no hunt diamond, and — if it is a miniboss — wears an unlit
   * crown rather than a lit one. Absent means awake.
   */
  sl?: number;
}

/**
 * One world gold pickup. Value is always 1 — enemies drop one per gold point.
 * Velocity is omitted while the coin is settled; absent means zero.
 */
export interface CoinState {
  id: string;
  x: number;
  y: number;
  vx?: number;
  vy?: number;
}

/** One body a shot opened, and what it owes for it. */
export interface ShotHit {
  id: string;
  dmg: number;
}

/**
 * One pellet's ray: `[dx, dy, dist, hit]`, where `hit` is 1 when it stopped
 * on a body. A tuple rather than an object because a shell carries six of
 * them thirty times a second and the field names would be most of the row.
 */
export type PelletRay = [number, number, number, number];

export interface ShotEvent {
  id: number;
  by: string;
  /** Weapon key. Absent on a server too old to send it. */
  k?: string;
  x: number;
  y: number;
  /** The AIM the pull was centred on. Pellets fan out around it. */
  dx: number;
  dy: number;
  /** How far the DEEPEST ray of the pull travelled. */
  dist: number;
  /** The body the pull hurt most, or null. */
  hit: string | null;
  /** Damage the primary victim took, all pellets in. 0 on a miss / crate. */
  dmg?: number;
  /**
   * Every ray of a multi-pellet pull, in the order the pattern was cast.
   * Absent on a one-ray weapon, which is every gun but the shotgun.
   */
  p?: PelletRay[];
  /**
   * Present only when a single pull opened MORE than one body — a shell
   * through two zombies. `hit` / `dmg` are still the worst-hurt of these,
   * so nothing that only understands one victim has to change.
   */
  hits?: ShotHit[];
}

/** One body a player's blade opened. */
export interface SwingHit {
  id: string;
  dmg: number;
}

/**
 * One PLAYER melee arc that connected. Whiffs are never sent — the swinger
 * already drew their own, and a remote waving a blade at nothing is not news.
 *
 * There is no `dist` and no single `hit`, which is the whole reason this is
 * not a `ShotEvent`: a swing is an area, and the finisher goes through more
 * than one body. The reach and width of the arc are `step`'s, read off
 * `GameConfig.weapons[k].melee.steps` — the tick carries which beat it was,
 * never the geometry of it.
 */
export interface SwingEvent {
  id: number;
  by: string;
  /** Weapon key — the row in `GameConfig.weapons` carrying the combo. */
  k: string;
  /** Which beat of the chain: 0 and 1 are slashes, 2 is the cut. */
  step: number;
  /** Swinger's body centre at the moment of the swing. */
  x: number;
  y: number;
  /** Aim direction the arc was centred on. */
  dx: number;
  dy: number;
  hits: SwingHit[];
}

/** One enemy melee swing. `dmg` is 0 when the victim's i-frames ate it. */
export interface AttackEvent {
  /** Attacking enemy id. */
  by: string;
  /** Victim player id. */
  target: string;
  x: number;
  y: number;
  /** Swing direction, attacker -> victim. */
  dx: number;
  dy: number;
  dmg: number;
  blocked: boolean;
}

export interface KillEvent {
  kind: 'player' | 'enemy';
  killer: string | null;
  victim: string;
  x: number;
  y: number;
  /** Paid to the killer immediately. Zero for player kills. */
  xp: number;
  /**
   * Coins actually scattered at the corpse — not auto-credited, and rolled
   * per kill out of the creature's `goldMax`, so it varies from one to the
   * next. Zero is a real outcome.
   */
  gold: number;
  /** Enemy type key. Present on enemy kills so the corpse can wear the right sheet. */
  t?: string;
  /** Body variant index. */
  v?: number;
  hat?: number;
  cloth?: number;
  /** Last facing. */
  ax?: number;
  ay?: number;
  /** Killing blow, so the body falls away from the shot. */
  dx?: number;
  dy?: number;
}

/** A dead enemy left on the floor. Does not move; the list only grows. */
export interface CorpseState {
  id: string;
  x: number;
  y: number;
  t: string;
  v: number;
  hat?: number;
  cloth?: number;
  ax: number;
  ay: number;
  dx: number;
  dy: number;
}

/** A coin that just entered a player's pocket. */
export interface PickupEvent {
  id: string;
  by: string;
  x: number;
  y: number;
  gold: number;
}

export type RoomPhase = 'lobby' | 'playing';

/**
 * One row of the lobby roster. Colour is this player's identity everywhere.
 *
 * `x`/`y` are the player's REAL position in the camp — the same numbers the
 * simulation will hand back in a snapshot the moment the host starts. The lobby
 * scene draws them rather than inventing a seating plan of its own, which is
 * what makes the party you are looking at the party you are about to play with.
 */
export interface LobbyPlayer {
  id: string;
  name: string;
  color: string;
  x: number;
  y: number;
}

/**
 * Sent once, before anything else. `lobby` is one payload broadcast to the
 * whole room, so which row is yours has to arrive in a message only you get.
 *
 * It also carries the camp: the lobby is not a picture of the clearing, it is
 * the clearing, drawn before anybody may walk on it. Sending the map here means
 * it travels once per socket rather than on every roster change.
 */
export interface HelloMessage {
  type: 'hello';
  playerId: string;
  code: string;
  config: GameConfig;
  map: MapPayload;
  zone: ZoneInfo;
}

/** Room membership + phase. Pushed on every change, not on a tick. */
export interface LobbyMessage {
  type: 'lobby';
  code: string;
  hostId: string | null;
  phase: RoomPhase;
  zone: ZoneInfo;
  players: LobbyPlayer[];
}

/** A refusal, followed by the server closing the socket. */
export interface ErrorMessage {
  type: 'error';
  code: 'room_not_found' | string;
}

export interface WelcomeMessage {
  type: 'welcome';
  playerId: string;
  player: PlayerFull;
  config: GameConfig;
  map: MapPayload;
  /** Where the run now is. Entering it is what plays the zone intro. */
  zone: ZoneInfo;
  /**
   * Last input sequence the server processed for this player. Same meaning as
   * snapshot `ack`. A second welcome (forest after camp) must resume above
   * this or `queue_input` drops every packet as a replay.
   */
  ack: number;
  /** Remaining world drops. Replaces the client's list on every welcome. */
  loot?: LootState[];
  /** Dead bodies still on this map. Replaces the client's list on every welcome. */
  corpses?: CorpseState[];
  /** Run objectives. Absent until the entrance seals. */
  quests?: QuestState[];
  /** Lamps are dead. The extraction chase; latched until the next welcome. */
  blackout?: boolean;
  /**
   * THE PARTY'S money — what the group loaded onto the platforms, converted on the
   * way out of the forest. Always sent, even at zero: a client that had to wait
   * for the first change to learn it would draw an empty purse over a corridor
   * full of price tags. `PlayerFull.gold` is the other, personal one: coins
   * picked up off corpses, which nobody pooled.
   */
  balance?: number;
  /**
   * What the next BOUGHT pull costs at the cabinet — see
   * `SnapshotMessage.spinPrice`. Always sent, for the same reason the balance
   * is: the lever names a price the moment somebody stands at it.
   */
  spinPrice?: number;
}

export interface SnapshotMessage {
  type: 'snapshot';
  tick: number;
  /** Camp walk-out: input is locked and bodies are puppeted toward the exit. */
  departing?: boolean;
  /** Forest emerge: same lock, walking out of the VOID corridor. */
  arriving?: boolean;
  /** Drop the snapshot if this does not match `welcome.zone.key` — a stale camp tick after embark. */
  zoneKey?: string;
  players: PlayerState[];
  /**
   * Identity + score board for the same players. Present only every few ticks
   * (and whenever somebody joins or leaves) — cache it; a snapshot without one
   * is not a snapshot without players.
   */
  roster?: PlayerFull[];
  /**
   * Live enemies only — an id that disappears is dead or despawned.
   * `v` / `hat` / `cloth` are the look rolled at spawn; see `EnemyState`.
   */
  enemies: EnemyState[];
  /** Live gold pickups. */
  coins: CoinState[];
  shots: ShotEvent[];
  /** Player melee arcs that connected. Absent on ticks where none did. */
  swings?: SwingEvent[];
  attacks: AttackEvent[];
  kills: KillEvent[];
  pickups: PickupEvent[];
  /** Remaining world drops. Present only when the set changed. */
  loot?: LootState[];
  /** Drops collected since the last snapshot. */
  lootPickups?: LootPickupEvent[];
  /** Items tipped out of a backpack onto a pad since the last snapshot. */
  pours?: PourEvent[];
  /** Remaining crates. Present only when the set changed. */
  crates?: CrateState[];
  /** Crates smashed since the last snapshot. */
  crateBreaks?: CrateBreakEvent[];
  /**
   * Blows that landed on GEAR. Absent on almost every tick — the roster is
   * what carries the durability, and this is only the frames it moved.
   */
  armorHits?: ArmorHitEvent[];
  /** Remaining corpses. Present only when one was added. */
  corpses?: CorpseState[];
  /**
   * Extraction pads that changed state. The client runs the ceremony between
   * these snapshots off its own clock.
   */
  rifts?: RiftStateRow[];
  /** Entrance changed state (open → sealing → gone). */
  entrance?: { state: EntranceState; t: number };
  /** Extraction exit, sent once when the feed quota is paid. */
  egress?: EntrancePayload;
  /** Tiles rewritten this tick — the forest swallowing the corridor, or the exit opening. */
  tilePatches?: Array<[tx: number, ty: number, kind: number]>;
  /** Objectives. Present when the list changed (appear, tick, complete). */
  quests?: QuestState[];
  /** Lamps just died. Latched locally until the next welcome. */
  blackout?: boolean;
  /** The shop's tables. Present only when one was bought from. */
  stands?: StandState[];
  /** Purchases since the last snapshot. */
  /**
   * The whole crate list, when the wall changed — arriving, and buying a
   * calibre nobody had. Replaces what the client is holding.
   */
  boxes?: AmmoBoxState[];
  buys?: BuyEvent[];
  spins?: SpinEvent[];
  /** The party's balance. Present only when it changed. */
  balance?: number;
  /**
   * What the NEXT bought pull costs, for a player holding no level. The
   * cabinet takes gold once the free spins are gone; every purchase doubles
   * this and the walk into each night's shop puts it back at the bottom.
   * Party-wide like the balance it spends, and present only when it moved.
   */
  spinPrice?: number;
  /**
   * THE SAWYER. Present only on the boss map, and only on ticks he changed —
   * which during a fight is all of them. Absent is not "he is gone": the
   * client keeps the last row it saw until the zone changes, exactly the way
   * it keeps the roster.
   */
  boss?: BossRow;
  /** What he DID this tick: shake, dust, sound, gore. Never replayed. */
  bossEvents?: BossEvent[];
  /**
   * THE RUN IS OVER. Present on every tick of the death card's hold and absent
   * on every other one, which makes it a STATE rather than an event on
   * purpose: a client that happened to miss the single frame a run ended would
   * otherwise walk a party out of a camp it never saw them arrive in. Anybody
   * who joins or reconnects mid-hold gets the black screen too, and the fresh
   * `welcome` that follows is what clears it.
   */
  wipe?: WipeRow;
  /**
   * A WAVE IS COMING, and from over there. One row per horde announced this
   * tick; the bodies arrive as ordinary `enemies` a few seconds later and need
   * no wire of their own.
   *
   * An EVENT and never replayed. A client that missed it gets the horde
   * without the warning — bad, but strictly better than a phantom howl for a
   * wave that already landed on somebody.
   */
  hordes?: HordeEvent[];
}

/**
 * One horde announced. `x`/`y` is where the howl comes FROM, which is the same
 * bearing the bodies will walk in on — the sound IS the warning, and it is
 * spatial so it works with the player facing the other way.
 */
export interface HordeEvent {
  x: number;
  y: number;
}

/** The run that just ended. `day` is the night it ended ON, captured when the
 *  party went down — by the time the reset runs the day is already back to 1. */
export interface WipeRow {
  day: number;
}

/**
 * The boss, as one row with his own PLAYHEAD on it.
 *
 * `s` is the state and `t` is how long he has been in it, and the client
 * animates off those two rather than off a local clock. That is the one
 * unusual thing about this row and it is deliberate: every other animated
 * thing in the game is either locally timed (the merchant) or driven by
 * velocity (a walk cycle), and neither works for a body whose windup IS the
 * mechanic. A locally timed chop and a server-timed hitbox disagree about
 * which frame the bar landed on, and that frame is the entire fight.
 */
export interface BossRow {
  id: string;
  x: number;
  y: number;
  /** Facing, as a unit vector. Picks the sprite row like any other body. */
  ax: number;
  ay: number;
  hp: number;
  max: number;
  /** One of `sleep` | `arrive` | `idle` | `walk` | `windup` | `strike` | `recover` | `dead`. */
  s: BossState;
  /** Seconds into `s`. The clip's playhead. */
  t: number;
  /**
   * Which move is being performed: `chop` / `sweep` / `rip` / `charge` / `rev`.
   *
   * A MOVE NAME, NOT A SHEET NAME. They were the same string until the charge,
   * which plays three clips; resolve the sheet through
   * `welcome.config.bossMoves[m].clip` / `.after` rather than using this
   * directly. `render/boss.ts`'s `clipFor` is where that happens.
   */
  m?: string | null;
  /** Past half health: he is faster and he waits less. */
  rage?: boolean;
  /** Crescents in the air. Absent when there are none. */
  crest?: BossCrescent[];
}

/** One attack's clock and reach. See `boss.Move.client_payload`. */
export interface BossMove {
  key: string;
  /**
   * The SHEET the windup (and, for a swing, the strike) plays.
   *
   * A move is no longer guaranteed to be a clip. Every swing sets `key`,
   * `clip` and `after` to the same string, but the charge telegraphs on `rev`,
   * runs on `walk` and pulls up on `idle` — one move, three animations —
   * because it is the one attack that is not a pose.
   */
  clip: string;
  /** The sheet the RECOVERY plays. Equal to `clip` for every swing. */
  after: string;
  /** Seconds from the start of the clip to the frame the blow lands. */
  windup: number;
  /** Seconds the hitbox is open. */
  active: number;
  /** World px, centre to the nose of the bar. Zero for a move that throws. */
  reach: number;
}

/** His capsule, in world px. Mirrors `Boss.radius` / `half_height` / `sprite_height`. */
export interface BossHitSpec {
  radius: number;
  halfHeight: number;
  spriteHeight: number;
}

export interface BossCrescentSpec {
  /** World px per second. */
  speed: number;
  /** Seconds before it expires. */
  life: number;
  /** World px. Its own hit radius. */
  radius: number;
  /** `speed * life` — how far it actually gets. */
  reach: number;
}

export type BossState =
  | 'sleep' | 'arrive' | 'idle' | 'walk'
  // `charge` is the run: the ONE state in which his hitbox is moving, and the
  // only one whose clip is not the move's own (`walk`, not `rev`).
  | 'windup' | 'strike' | 'charge' | 'recover' | 'dead';

/** One thrown crescent, mid-flight. */
export interface BossCrescent {
  id: number;
  x: number;
  y: number;
  /** Velocity, in world px/s. The heading the sheet is baked in comes off it. */
  dx: number;
  dy: number;
  /** Seconds of life left. */
  t: number;
}

/**
 * Something he did. Each kind is a different piece of juice and they are
 * deliberately not one "effect" event with a magnitude: the shake, the sound
 * and the light for a chop landing are nothing like the ones for a roar.
 */
export interface BossEvent {
  kind:
    | 'arrive'    // the shadow starts growing; the cinematic has begun
    | 'engage'    // the cinematic is over, the fight is on
    | 'windup'    // he has committed to a move — `move` names it
    | 'impact'    // a melee blow landed (or missed): `hits` is how many bodies
    | 'rip'       // crescents left the bar: `hits` is how many (3 when enraged)
    | 'charge'    // the roar landed and he is running: `dx`/`dy` is the heading
    | 'slam'      // the run ended in the treeline — the fight's biggest window
    | 'crestBurst'// a crescent hit something and came apart
    | 'roar'      // the rev's own beat
    | 'enrage'    // half health
    | 'hit'       // HE was hurt: `dmg`, `hp`, and the direction it came from
    | 'hurt'      // a PLAYER was hurt by him
    | 'slain';    // he is going down
  x: number;
  y: number;
  dx?: number;
  dy?: number;
  move?: string;
  hits?: number;
  dmg?: number;
  hp?: number;
  target?: string;
  /** A windup that skipped its cooldown: the enraged double chop. */
  encore?: boolean;
}

/** The live half of an extraction pad. */
export interface RiftStateRow {
  id: string;
  state: 'dormant' | 'charging' | 'open' | 'spent';
  /** Seconds into the sequence, so a late joiner picks it up in progress. */
  t: number;
  /** When the launch begins, in the same clock as `t`. */
  closeAt?: number | null;
  /** Catalog value put into THIS pad, and what it asked for. */
  fed?: number;
  need?: number;
  /**
   * The quota is settled and the pickup has not been called: the console is a
   * CALL button now. Nothing about it is automatic — a paid pad waits as long
   * as the party wants.
   */
  ready?: boolean;
}

export interface PongMessage {
  type: 'pong';
  t: number;
}

export type ServerMessage =
  | HelloMessage
  | LobbyMessage
  | ErrorMessage
  | WelcomeMessage
  | SnapshotMessage
  | PongMessage;
