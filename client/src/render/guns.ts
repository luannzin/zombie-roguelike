/**
 * Held-gun atlas: one side-view frame per weapon, pointing right.
 *
 * Produced by server/tools/make_guns.py and served from /guns/.
 * The client rotates around `grip` and flips when aim is left.
 * Ground / HUD icons stay on the loot atlas — this sheet is IN HAND.
 */

import { loadImage, loadJson } from '../lib/image';

export interface GunFrame {
  frame: number;
  gripX: number;
  gripY: number;
  muzzleX: number;
  muzzleY: number;
}

export interface GunAtlas {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  items: Record<string, GunFrame>;
}

interface GunManifest {
  tile: number;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  items: Record<string, GunFrame>;
}

const ROOT = '/guns';

let atlasPromise: Promise<GunAtlas | null> | null = null;

export function loadGuns(): Promise<GunAtlas | null> {
  atlasPromise ??= fetchGuns();
  return atlasPromise;
}

async function fetchGuns(): Promise<GunAtlas | null> {
  try {
    const manifest = await loadJson<GunManifest>(`${ROOT}/manifest.json`);
    const image = await loadImage(`${ROOT}/sheet.png`);
    return {
      image,
      frameWidth: manifest.frameWidth,
      frameHeight: manifest.frameHeight,
      frames: manifest.frames,
      items: manifest.items,
    };
  } catch (err) {
    console.warn('[guns] no gun atlas, weapons draw as the old aim line:', err);
    return null;
  }
}
