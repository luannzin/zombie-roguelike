/**
 * Gore atlas: one small wound decal per frame, worn by a body that was hit.
 *
 * Produced by server/tools/make_gore.py and served from /gore/.
 *
 * Not a `vfx` sheet and not a scenery decal, and the difference is where the
 * pixels land. A vfx sheet is a greyscale TIMELINE tinted at draw time and
 * added over the darkness, because it is light. A scenery decal is baked flat
 * into the ground canvas. These are stamped on a SPRITE, in the entity pass,
 * in the art's own colour and lit by the same night the body is — so a wound
 * on a zombie standing outside the lantern is as invisible as the zombie.
 *
 * The frames are VARIANTS, never an animation: the client rolls one per hit
 * and the creature carries it (see `game/entity-visuals.ts`).
 *
 * Loading is best-effort: a missing atlas resolves to `null` and bodies simply
 * do not show wounds, the same way a missing vfx atlas drops its effects.
 */

import { loadImage, loadJson } from '../lib/image';

export interface GoreAtlas {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
}

interface GoreManifest {
  tile: number;
  frameWidth: number;
  frameHeight: number;
  frames: number;
}

const ROOT = '/gore';

let atlasPromise: Promise<GoreAtlas | null> | null = null;

export function loadGore(): Promise<GoreAtlas | null> {
  atlasPromise ??= fetchGore();
  return atlasPromise;
}

async function fetchGore(): Promise<GoreAtlas | null> {
  try {
    const manifest = await loadJson<GoreManifest>(`${ROOT}/manifest.json`);
    const image = await loadImage(`${ROOT}/sheet.png`);
    return {
      image,
      frameWidth: manifest.frameWidth,
      frameHeight: manifest.frameHeight,
      frames: manifest.frames,
    };
  } catch (err) {
    console.warn('[gore] no wound atlas, bodies will not show hits:', err);
    return null;
  }
}
