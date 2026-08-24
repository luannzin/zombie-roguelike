/**
 * The ultimate icon atlas: which frame of `/ultimates/sheet.png` a key is on.
 *
 * A MANIFEST AND NO IMAGE, which is what separates this from every other
 * loader in this directory. The other atlases are read by the CANVAS, so they
 * have to resolve an `HTMLImageElement` and hand it to a draw call. This one
 * is read by REACT — the panel above the belt is a DOM element and the sheet
 * is a CSS background, exactly the way `SkillIcon` works — so the only thing
 * the game core has to know is the frame index, and loading the picture twice
 * (once for a canvas that never draws it, once for the browser's own image
 * cache) would be a wasted fetch.
 *
 * BEST EFFORT, like every atlas here. A missing manifest resolves to an empty
 * map, every ultimate lands on frame 0, and the panel still says its name, its
 * bar and its requirements — which is the right way round for an art gap: the
 * mechanic keeps working and the picture is wrong.
 */

import { loadJson } from '../lib/image';

interface UltimateManifest {
  cell: number;
  frames: number;
  items: Record<string, { frame: number }>;
}

/** Frame index per ultimate key. Empty when the sheet has not been built. */
export type UltimateFrames = Map<string, number>;

export async function loadUltimateFrames(): Promise<UltimateFrames> {
  const frames: UltimateFrames = new Map();
  const manifest = await loadJson<UltimateManifest>('/ultimates/manifest.json').catch(
    () => null,
  );
  if (!manifest?.items) return frames;
  for (const [key, row] of Object.entries(manifest.items)) {
    if (typeof row?.frame === 'number') frames.set(key, row.frame);
  }
  return frames;
}
