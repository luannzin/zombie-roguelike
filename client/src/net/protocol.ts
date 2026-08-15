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
  /** Hotbar slot in hand. -1 is holstered. Empty slots are treated as -1. */
  held: number;
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

export type ClientMessage =
  | InputPacket
  | PingPacket
  | StartPacket
  | ReadyPacket
  | CollectPacket
  | BreakPacket
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
  /** How far a bonfire throws light, in tiles. The camp's only light source. */
  campfireLightTiles: number;
  /** The fire plus the seat ring, in tiles: nothing grows inside it. */
  hearthTiles: number;
  /** Seat ring radii, in tiles. Elliptical — see server/app/camp.py. */
  ringTilesX: number;
  ringTilesY: number;
  /** How close to the fire (tiles, feet to flame) the ready prompt answers. */
  readyRangeTiles: number;
  /** How close to a drop (tiles, feet to item) E will collect. */
  lootCollectTiles?: number;
  /** How close to a crate (tiles, feet to contact) E will smash. */
  crateBreakTiles?: number;
  /** Crate shot box width, in tiles. Bottom-anchored on the contact. */
  crateHitWTiles?: number;
  /** Crate shot box height, in tiles. Covers the barrel, not just the foot. */
  crateHitHTiles?: number;
  /** Catalog of world loot. Keyed by item key; `frame` indexes the loot atlas. */
  loot?: Record<string, LootItemConfig>;
  /** Combat stats for guns. Keyed by the same keys as loot rows with pocket `hotbar`. */
  weapons?: Record<string, WeaponConfig>;
  /** Starting bag size. A later upgrade grows it. */
  inventorySlots?: number;
  /** Gun belt size. */
  hotbarSlots?: number;
  /** Weight the walk is tuned around. The bag may go past this. */
  carryMaxWeight?: number;
  /** Fraction of max weight that is still full speed. */
  carrySlowStart?: number;
  /** Speed multiplier at exactly max weight. */
  carrySlowAtMax?: number;
  /** Slowest the walk is allowed to get, even overweight. */
  carrySlowFloor?: number;
}

export type LootRarity = 'common' | 'uncommon' | 'rare' | 'epic' | 'legendary';

export interface LootItemConfig {
  name: string;
  rarity: LootRarity;
  frame: number;
  weight: number;
  value: number;
  /** Where a collect puts it. Guns are `hotbar`; valuables are `bag`. */
  pocket?: 'bag' | 'hotbar';
}

export type WeaponKind = 'pistol' | 'rifle' | 'sniper' | string;

/** Combat block for one gun. Mirrors server/app/weapons.py. */
export interface WeaponConfig {
  name: string;
  kind: WeaponKind;
  ammo: string;
  damage: number;
  fireCooldown: number;
  range: number;
  muzzle: number;
  noise: number;
  aimDelay: number;
  scopeZoom: number;
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
}

/** One world drop. `k` keys into `GameConfig.loot`. */
export interface LootState {
  id: string;
  k: string;
  x: number;
  y: number;
}

/** A drop that just entered a player's pocket. */
export interface LootPickupEvent {
  id: string;
  by: string;
  k: string;
  x: number;
  y: number;
  /** Bag or hotbar slot it landed in. The fly aims at this cell. */
  slot: number;
  /** `hotbar` for a gun; omitted for the pocket. */
  dest?: 'bag' | 'hotbar';
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
  kind: 'camp' | 'forest' | string;
  day: number;
  title: string;
  subtitle: string;
  /** Enemies spawn and weapons fire. */
  hostile: boolean;
  /** The lantern switch works. False in the camp: the bonfire is the light. */
  lantern: boolean;
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
}

/** One live crate. `v` is the kind row on the crate sheet (box, barrel, …). */
export interface CrateState {
  id: string;
  x: number;
  y: number;
  v: number;
  flip: number;
}

export type CrateDrop = 'empty' | 'coin' | 'item';

/** A crate that just broke. Juice for the smash sheet and the empty-wind puff. */
export interface CrateBreakEvent {
  id: string;
  x: number;
  y: number;
  v: number;
  flip: number;
  drop: CrateDrop;
  /** Catalog key when `drop` is `item`. */
  k?: string;
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
  /** Camp only: standing at the fire and confirmed. */
  ready?: boolean;
  /** Hotbar index in hand. -1 is holstered. */
  held?: number;
  /** True while a scoped gun is being held to fire. */
  ads?: boolean;
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
}

/** One bag slot on the wire. `n` is the stack. */
export interface InventorySlotState {
  k: string;
  n: number;
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

export interface ShotEvent {
  id: number;
  by: string;
  /** Weapon key. Absent on a server too old to send it. */
  k?: string;
  x: number;
  y: number;
  dx: number;
  dy: number;
  dist: number;
  hit: string | null;
  /** Damage dealt. 0 on a miss / crate. */
  dmg?: number;
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
}

export interface SnapshotMessage {
  type: 'snapshot';
  tick: number;
  /** Camp walk-out: input is locked and bodies are puppeted toward the exit. */
  departing?: boolean;
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
  attacks: AttackEvent[];
  kills: KillEvent[];
  pickups: PickupEvent[];
  /** Remaining world drops. Present only when the set changed. */
  loot?: LootState[];
  /** Drops collected since the last snapshot. */
  lootPickups?: LootPickupEvent[];
  /** Remaining crates. Present only when the set changed. */
  crates?: CrateState[];
  /** Crates smashed since the last snapshot. */
  crateBreaks?: CrateBreakEvent[];
  /** Remaining corpses. Present only when one was added. */
  corpses?: CorpseState[];
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
