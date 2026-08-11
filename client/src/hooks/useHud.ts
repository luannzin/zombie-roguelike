/**
 * Read the game's HUD snapshot.
 *
 * The store publishes at 5 Hz (HUD_INTERVAL), so this drives ~5 re-renders a
 * second of a handful of text nodes. React is deliberately kept out of the
 * 60 Hz render loop — everything per-frame is drawn to canvas instead.
 */

import { useSyncExternalStore } from 'react';
import type { HudSnapshot, HudStore } from '../game/hud-store';

export function useHud(store: HudStore): HudSnapshot {
  return useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
}
