/**
 * The single seam between the game loop and the React HUD.
 *
 * `Game` publishes an immutable snapshot here (throttled — see HUD_INTERVAL);
 * components read it through `useSyncExternalStore`. React never participates
 * in the render loop, and the game core never touches the DOM.
 */

import { Store } from '../lib/store';
import type { ConnectionStatus } from '../net/connection';

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

export interface HudSnapshot {
  connection: ConnectionStatus;
  /** Human-readable connection line. */
  status: string;
  /** True once a `welcome` has been received and a world exists. */
  inArena: boolean;
  vitals: HudVitals | null;
  net: HudNetStats | null;
}

export const EMPTY_HUD: HudSnapshot = {
  connection: 'connecting',
  status: 'connecting…',
  inArena: false,
  vitals: null,
  net: null,
};

export type HudStore = Store<HudSnapshot>;

export function createHudStore(): HudStore {
  return new Store<HudSnapshot>(EMPTY_HUD);
}
