/**
 * Wire protocol types. Mirrors server/app/protocol.py — keep both in sync.
 * All gameplay tuning arrives from the server in `welcome.config`; never
 * hardcode a gameplay constant here.
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
}

export interface PingPacket {
  type: 'ping';
  t: number;
}

export type ClientMessage = InputPacket | PingPacket;

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
  playerHitRadius: number;
  moveSpeed: number;
  maxHp: number;
  fireCooldown: number;
  shotRange: number;
  shotDamage: number;
  muzzleOffset: number;
}

export interface MapPayload {
  width: number;
  height: number;
  tileSize: number;
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
  hp: number;
  alive: boolean;
  kills: number;
  deaths: number;
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

export interface KillEvent {
  killer: string | null;
  victim: string;
  x: number;
  y: number;
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
  shots: ShotEvent[];
  kills: KillEvent[];
}

export interface PongMessage {
  type: 'pong';
  t: number;
}

export type ServerMessage = WelcomeMessage | SnapshotMessage | PongMessage;
