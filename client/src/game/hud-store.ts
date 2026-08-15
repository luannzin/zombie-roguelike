/**
 * The single seam between the game loop and the React HUD.
 *
 * `Game` publishes an immutable snapshot here (throttled — see HUD_INTERVAL);
 * components read it through `useSyncExternalStore`. React never participates
 * in the render loop, and the game core never touches the DOM.
 */

import { Store } from '../lib/store';
import type { LanternReading } from './lantern';
import type { ConnectionStatus } from '../net/connection';
import type { LootRarity, ZoneInfo } from '../net/protocol';

export interface HudInventorySlot {
  key: string;
  qty: number;
  name: string;
  rarity: LootRarity;
  frame: number;
  value: number;
  weight: number;
}

export interface HudInventory {
  open: boolean;
  cap: number;
  slots: Array<HudInventorySlot | null>;
  weight: number;
  maxWeight: number;
  /** Sum of item values in the bag. In-flight collects are not counted yet. */
  gold: number;
  lootFrames: number;
  /** Bumps the pack when a fly lands. Count, not a boolean — 5 Hz. */
  catches: number;
  /** Full-bag refusals. Same counter contract as the lantern. */
  refusals: number;
}

export interface HudLootPrompt {
  id: string;
  name: string;
  rarity: LootRarity;
  /** No empty slot and no stack of this key. The tooltip turns red. */
  full: boolean;
}

/** How often the game republishes HUD state. 5 Hz is plenty for text. */
export const HUD_INTERVAL = 0.2;

export interface HudVitals {
  name: string;
  color: string;
  kills: number;
  deaths: number;
  hp: number;
  maxHp: number;
  alive: boolean;
  /** Progression, paid out by the enemies you kill. */
  level: number;
  xpInLevel: number;
  xpToLevel: number;
  gold: number;
}

export interface HudNetStats {
  players: number;
  enemies: number;
  rttMs: number;
  interpMs: number;
  pending: number;
  fps: number;
}

/**
 * One arrival in a zone, announced once.
 *
 * `key` is the zone's, not a counter: the card is a statement about a PLACE, so
 * re-entering the same one replays it and a reconnect into the zone you are
 * already standing in does not. Components key their entry animation off it.
 */
export interface HudArrival {
  key: string;
  zone: ZoneInfo;
}

export interface HudSnapshot {
  connection: ConnectionStatus;
  /** Human-readable connection line. */
  status: string;
  /** True once a `welcome` has been received and a world exists. */
  inArena: boolean;
  vitals: HudVitals | null;
  net: HudNetStats | null;
  /**
   * Battery + switch. Published at 5 Hz like everything else here, which is
   * deliberate: the gauge shows CHARGE, and the per-frame blinking belongs to
   * the light in the world, not to a React re-render.
   */
  lantern: LanternReading | null;
  /** Where the run is. Decides what the HUD offers and what it greys out. */
  zone: ZoneInfo | null;
  /** Set on entering a zone; the title card plays and then leaves it alone. */
  arrival: HudArrival | null;
  /**
   * True while the arrival is still holding the player.
   *
   * The HUD stays OFF the glass for this beat. What is on screen is the place
   * and your own character standing in it, and a full set of corners over that
   * turns an establishing shot into a gameplay frame with a caption. It comes
   * back at the same moment the controls do, which is what makes the HUD
   * arriving read as "you're up".
   *
   * It DEFAULTS TO TRUE, and that default is the whole point. The store is
   * created when the arena mounts and the game only reaches `onWelcome` a
   * moment later, after its sheets have loaded — so a default of `false` would
   * paint the corners at full strength for those frames and then hide them,
   * which is a flash of HUD exactly where the transition is supposed to be
   * seamless. Hidden until something says otherwise; only the end of the hold
   * (or a dropped connection, which has news to show) turns it off.
   */
  introducing: boolean;
  /**
   * Camp walk-out. Chrome off, letterbox on, same as an arrival — the party
   * is leaving and the HUD has nothing to say about it.
   */
  cinematic: boolean;
  /** Living players ready / total, camp only. Null in the forest. */
  ready: { here: number; total: number } | null;
  /** Proximity prompt at the fire. Null when it should not be on screen. */
  prompt: 'ready' | null;
  /** Proximity prompt on a world drop. `full` is a bag that cannot take it. */
  lootPrompt: HudLootPrompt | null;
  /** Proximity prompt on a crate. */
  cratePrompt: boolean;
  /** The pocket. Null before welcome. Open/close is client-local (TAB). */
  inventory: HudInventory | null;
}

export const EMPTY_HUD: HudSnapshot = {
  connection: 'connecting',
  status: 'connecting…',
  inArena: false,
  vitals: null,
  net: null,
  lantern: null,
  zone: null,
  arrival: null,
  introducing: true,
  cinematic: false,
  ready: null,
  prompt: null,
  lootPrompt: null,
  cratePrompt: false,
  inventory: null,
};

export type HudStore = Store<HudSnapshot>;

export function createHudStore(): HudStore {
  return new Store<HudSnapshot>(EMPTY_HUD);
}
