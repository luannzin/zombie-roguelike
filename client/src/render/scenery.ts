/**
 * Scenery atlas: what people left in the forest.
 *
 * Produced by server/tools/make_scenery.py and served from /scenery/.
 *
 * The sibling of `terrain.ts`, and the split is the same one the generators
 * make. Terrain is the PLACE — soil, stone, wood that grew there — and the
 * client scatters it off the map seed, because one rock is as good as another.
 * Scenery was CARRIED in, and it arrives placed, in groups, in the map payload
 * (`server/app/scenery.py`): a tent, a cold firepit and a line of boot prints
 * walking away from both are one sentence, and a hash cannot write a sentence.
 *
 * Two shapes, and the difference is a sorting rule as much as a drawing one:
 *
 *   PROPS stand up. Bottom-anchored on a contact point and depth-sorted with
 *   the party, so a body passes in front of and behind them. `sway` is a peak
 *   lean in world px for the ones the wind moves; `smokes` asks for a wisp off
 *   the anchor.
 *
 *   DECALS lie flat. Centred on their point and baked into the ground canvas
 *   with the rest of the litter, so they cost nothing per frame.
 *
 * Loading is best-effort in the same way the terrain atlas is: a missing
 * manifest resolves to `null` and nothing is drawn, rather than taking the
 * forest down with it.
 */

import { loadImage, loadJson } from '../lib/image';

export interface SceneryProp {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  /** Peak horizontal lean in world px. 0 for anything rooted. */
  sway: number;
  /** Whether a thin column of smoke still rises off it. */
  smokes: boolean;
  /**
   * Crate sheet only. Kinds are packed kind-major: idle is frame 0 of that
   * kind's strip, and the rest is the one-shot break. Absent on every other
   * prop — those frames are still variants.
   */
  kinds?: number;
  breakFrames?: number;
  fps?: number;
}

export interface SceneryDecal {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
}

export interface SceneryAtlas {
  props: Record<string, SceneryProp>;
  decals: Record<string, SceneryDecal>;
}

interface SheetManifest {
  file: string;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  sway?: number;
  smokes?: boolean;
  kinds?: number;
  breakFrames?: number;
  fps?: number;
}

interface SceneryManifest {
  tile: number;
  props: Record<string, SheetManifest>;
  decals: Record<string, SheetManifest>;
}

const ROOT = '/scenery';

/**
 * One atlas per session, shared by every layer — same reason `loadTerrain`
 * memoizes: the lobby and the arena draw the same world and must not spend
 * the handover fetching the same sheets twice.
 */
let atlasPromise: Promise<SceneryAtlas | null> | null = null;

export function loadScenery(): Promise<SceneryAtlas | null> {
  atlasPromise ??= fetchScenery();
  return atlasPromise;
}

async function fetchScenery(): Promise<SceneryAtlas | null> {
  try {
    const manifest = await loadJson<SceneryManifest>(`${ROOT}/manifest.json`);
    const props: Record<string, SceneryProp> = {};
    const decals: Record<string, SceneryDecal> = {};

    // Keyed by the manifest rather than by a hardcoded list, so adding a sheet
    // in `make_scenery.py` plus a scene in `server/app/scenery.py` needs no
    // change here at all.
    await Promise.all([
      ...Object.entries(manifest.props).map(async ([name, sheet]) => {
        props[name] = {
          image: await loadImage(`${ROOT}/${sheet.file}`),
          frameWidth: sheet.frameWidth,
          frameHeight: sheet.frameHeight,
          frames: sheet.frames,
          sway: sheet.sway ?? 0,
          smokes: sheet.smokes ?? false,
          kinds: sheet.kinds,
          breakFrames: sheet.breakFrames,
          fps: sheet.fps,
        };
      }),
      ...Object.entries(manifest.decals).map(async ([name, sheet]) => {
        decals[name] = {
          image: await loadImage(`${ROOT}/${sheet.file}`),
          frameWidth: sheet.frameWidth,
          frameHeight: sheet.frameHeight,
          frames: sheet.frames,
        };
      }),
    ]);

    return { props, decals };
  } catch (err) {
    console.warn('[scenery] no scenery atlas:', err);
    // Not memoized as a permanent failure: a later scene should get another go.
    atlasPromise = null;
    return null;
  }
}
