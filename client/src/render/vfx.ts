/**
 * VFX atlas: pre-rendered effect animations.
 *
 * Produced by server/tools/make_vfx.py and served from /vfx/
 * (assets/processed is Vite's publicDir).
 *
 * These are not props. A prop sheet's frames are variants of one object and it
 * is bottom-anchored on a tile; an effect sheet's frames are a TIMELINE played
 * once, anchored on the point the effect happens at. That point is `anchorY`
 * pixels down from the top of the frame rather than the bottom edge, because
 * an impact needs rows below the contact line to throw a shockwave into.
 *
 * Every effect here is drawn ADDITIVELY, after the darkness pass — the same
 * rule the arena's renderer follows for muzzle flashes. A beam of light is a
 * light source, not a thing being lit.
 *
 * Loading is best-effort: a missing atlas resolves to `null` and callers skip
 * the effect, so the game still runs with no assets built.
 */

import { loadImage, loadJson } from '../lib/image';

export interface VfxSheet {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  /** Playback rate. The sheet's duration is `frames / fps` seconds. */
  fps: number;
  /** Distance from the top of the frame to the point the effect is anchored on. */
  anchorY: number;
  /** False for one-shot timelines, which is everything here so far. */
  loop: boolean;
}

export interface VfxAtlas {
  /**
   * Tile size the sheets were generated at. Callers drawing into a world on a
   * different scale would need to rescale, which for pixel art means a matching
   * integer factor — in practice both come from the same `--tile`.
   */
  tile: number;
  /** A player materialising: charge, strike, impact, collapse. */
  summon: VfxSheet | null;
}

interface EffectManifest {
  file: string;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  fps: number;
  anchorY: number;
  loop?: boolean;
}

interface VfxManifest {
  tile: number;
  effects: { summon?: EffectManifest };
}

const ROOT = '/vfx';

export async function loadVfx(): Promise<VfxAtlas | null> {
  try {
    const manifest = await loadJson<VfxManifest>(`${ROOT}/manifest.json`);
    const summon = manifest.effects.summon
      ? await loadEffect(manifest.effects.summon)
      : null;
    return { tile: manifest.tile, summon };
  } catch (err) {
    console.warn('[vfx] no effect atlas, effects disabled:', err);
    return null;
  }
}

async function loadEffect(manifest: EffectManifest): Promise<VfxSheet> {
  return {
    image: await loadImage(`${ROOT}/${manifest.file}`),
    frameWidth: manifest.frameWidth,
    frameHeight: manifest.frameHeight,
    frames: manifest.frames,
    fps: manifest.fps,
    anchorY: manifest.anchorY,
    loop: manifest.loop ?? false,
  };
}

/** Frame index for a one-shot sheet, held on the last frame once it is over. */
export function effectFrame(sheet: VfxSheet, elapsed: number): number {
  const index = Math.floor(elapsed * sheet.fps);
  if (sheet.loop) return ((index % sheet.frames) + sheet.frames) % sheet.frames;
  return Math.max(0, Math.min(sheet.frames - 1, index));
}
