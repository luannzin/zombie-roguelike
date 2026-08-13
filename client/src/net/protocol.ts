/**
 * Wire protocol types. Mirrors server/app/protocol.py — keep both in sync.
 * All gameplay tuning arrives from the server in `welcome.config`; never
 * hardcode a gameplay constant here.
 *
 * One socket carries both phases of a room: `hello` + `lobby` while the party
 * gathers, then `welcome` and the snapshot stream once the host starts. There
 * is no second connection — see `hooks/useRoomSession`.
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
}

export interface PingPacket {
  type: 'ping';
  t: number;
}

/** Leave the lobby and start the run. Ignored from anyone but the host. */
export interface StartPacket {
  type: 'start';
}

export type ClientMessage = InputPacket | PingPacket | StartPacket;

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
  /** Omnidirectional glow every player carries, in tiles. */
  visionAmbientTiles: number;
  /** Reach of the directional lantern cone, in tiles. */
  visionLanternTiles: number;
  /** Full width of the lantern cone, in degrees. */
  visionConeDegrees: number;
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
  gold: number;
  hitRadius: number;
  spriteHeight: number;
  halfWidth: number;
  halfHeight: number;
}

export interface MapPayload {
  width: number;
  height: number;
  tileSize: number;
  /**
   * Generator seed. Decoration (grass tufts, which prop variant a tile gets) is
   * hashed from this plus the tile coordinate rather than transmitted, so the
   * payload stays exactly as big as the map itself.
   */
  seed: number;
  /** Tile kinds — see game/world.ts. */
  tiles: number[][];
}

export interface PlayerState {
  id: string;
  name: string;
  color: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  /** normalized aim direction */
  ax: number;
  ay: number;
  /** Whether this player's lantern switch is on. */
  lantern: boolean;
  hp: number;
  alive: boolean;
  kills: number;
  deaths: number;
  /** Lifetime xp. The server also sends it pre-split into the level below. */
  xp: number;
  gold: number;
  level: number;
  xpInLevel: number;
  xpToLevel: number;
}

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
  /** normalized facing */
  ax: number;
  ay: number;
  hp: number;
}

/** One world gold pickup. Value is always 1 — enemies drop one per gold point. */
export interface CoinState {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

export interface ShotEvent {
  id: number;
  by: string;
  x: number;
  y: number;
  dx: number;
  dy: number;
  dist: number;
  hit: string | null;
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
  /** Coins scattered at the corpse — not auto-credited. */
  gold: number;
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

/** One row of the lobby roster. Colour is this player's identity everywhere. */
export interface LobbyPlayer {
  id: string;
  name: string;
  color: string;
}

/**
 * Sent once, before anything else. `lobby` is one payload broadcast to the
 * whole room, so which row is yours has to arrive in a message only you get.
 */
export interface HelloMessage {
  type: 'hello';
  playerId: string;
  code: string;
}

/** Room membership + phase. Pushed on every change, not on a tick. */
export interface LobbyMessage {
  type: 'lobby';
  code: string;
  hostId: string | null;
  phase: RoomPhase;
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
  player: PlayerState;
  config: GameConfig;
  map: MapPayload;
}

export interface SnapshotMessage {
  type: 'snapshot';
  tick: number;
  /** last input sequence the server processed for THIS client */
  ack: number;
  players: PlayerState[];
  /** Live enemies only — an id that disappears is dead or despawned. */
  enemies: EnemyState[];
  /** Live gold pickups. */
  coins: CoinState[];
  shots: ShotEvent[];
  attacks: AttackEvent[];
  kills: KillEvent[];
  pickups: PickupEvent[];
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
