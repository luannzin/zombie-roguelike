/**
 * Loot atlas: one 16x16 frame per collectable item.
 *
 * Produced by server/tools/make_loot.py and served from /loot/.
 * Frame index comes from welcome.config.loot[key].frame — the client never
 * invents an item or a slot.
 */

import { loadImage, loadJson } from '../lib/image';

export interface LootAtlas {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  items: Record<string, { frame: number }>;
}

interface LootManifest {
  tile: number;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  items: Record<string, { frame: number }>;
}

const ROOT = '/loot';

let atlasPromise: Promise<LootAtlas | null> | null = null;

export function loadLoot(): Promise<LootAtlas | null> {
  atlasPromise ??= fetchLoot();
  return atlasPromise;
}

async function fetchLoot(): Promise<LootAtlas | null> {
  try {
    const manifest = await loadJson<LootManifest>(`${ROOT}/manifest.json`);
    const image = await loadImage(`${ROOT}/sheet.png`);
    return {
      image,
      frameWidth: manifest.frameWidth,
      frameHeight: manifest.frameHeight,
      frames: manifest.frames,
      items: manifest.items,
    };
  } catch (err) {
    console.warn('[loot] no loot atlas, drops disabled:', err);
    return null;
  }
}
