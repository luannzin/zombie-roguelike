/**
 * Upgrade machine atlas: the cabinet, its parts and its light.
 *
 * Produced by server/tools/make_machine.py and served from /machine/.
 *
 * FOUR SHAPES, and the split is the same one every other atlas here keeps:
 *
 *   The CABINET is a bottom-anchored PROP. It stands in the entity depth sort
 *   beside the tables and the merchant, so a body walks in front of and behind
 *   it, and it takes the darkness multiply like any other object in a clearing.
 *
 *   The BAND and the LEVER are PARTS. They are blitted into the cabinet's own
 *   frame at offsets the manifest carries (`reels`, `lever`), because where a
 *   window is on the front panel is a property of the ART and a hardcoded
 *   offset here would drift the first time the cabinet was redrawn.
 *
 *   THE BAND IS ONE TALL IMAGE, NOT A STRIP OF FRAMES. `strip.png` holds the
 *   ten cells of the reel in a fixed order and the client scrolls a
 *   `reelHeight` window over it, wrapping — see `game/machine.ts`
 *   `reelScroll`. That is what makes a spin a strip going past instead of a
 *   frame index changing, and it is where the slow-down, the near miss and the
 *   motion blur all come from for free.
 *
 *   The EFFECTS — marquee, window backlight, payout burst — are additive and
 *   drawn AFTER the darkness pass, because they are light rather than things
 *   being lit. Unlike the store's fire they are GREYSCALE (`tinted: true`), so
 *   one sheet burns `--scene-neon` while the machine idles and the winning
 *   rarity's colour while a canister is on its way out.
 *
 * The CANISTER lives in a different atlas (`/skills/`) on purpose: it is a
 * thing the machine produces rather than a part of it, and the same sheet is
 * what the HUD tray draws.
 *
 * Loading is best-effort, like every other atlas here: a missing manifest
 * resolves to `null` and the layer draws nothing rather than taking the zone
 * down with it.
 */

import { loadImage, loadJson } from '../lib/image';

export interface MachinePart {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
}

export interface MachineEffect extends MachinePart {
  fps: number;
  /** The row the effect happens at, measured down from the frame's top. */
  anchorY: number;
  loop: boolean;
}

export interface MachineAtlas {
  /** Frame 0 is idle; frame 1 is the shell settled after a pull. */
  cabinet: MachinePart;
  /** The reel BAND: one image, `bandCells` cells tall, scrolled and wrapped. */
  strip: MachinePart;
  lever: MachinePart;
  marquee: MachineEffect;
  window: MachineEffect;
  burst: MachineEffect;
  /** Top-left of each reel window inside the cabinet frame. */
  reelSlots: Array<[number, number]>;
  reelWidth: number;
  reelHeight: number;
  /** How many cells the band holds, and what each of them is. */
  bandCells: number;
  band: string[];
  /** The row the three windows have to agree on, in cabinet-frame pixels. */
  payLine: number;
  /** Where the lever's pivot lands in the cabinet frame. */
  leverAnchor: [number, number];
  /** Where that pivot is inside the lever sheet. */
  leverPivot: [number, number];
  /** The hole a canister is launched out of, in cabinet-frame pixels. */
  trayMouth: [number, number];
  /** Centre of the crown, where the marquee is pinned. */
  crown: [number, number];
}

interface SheetManifest {
  file: string;
  frameWidth: number;
  frameHeight: number;
  frames?: number;
  fps?: number;
  anchorY?: number;
  loop?: boolean;
  pivot?: [number, number];
  /** Band only: how many cells the strip holds, and their rarity order. */
  cells?: number;
  band?: string[];
}

interface CabinetManifest extends SheetManifest {
  reels: Array<[number, number]>;
  reelWidth: number;
  reelHeight: number;
  lever: [number, number];
  trayMouth: [number, number];
  crown: [number, number];
  payLine: number;
}

interface MachineManifest {
  cabinet: CabinetManifest;
  /** The band. `file` is strip.png; `frameHeight` is the WINDOW, not the sheet. */
  reel: SheetManifest;
  lever: SheetManifest;
  effects: Record<'marquee' | 'window' | 'burst', SheetManifest>;
}

const ROOT = '/machine';

/** One atlas per session — the shop is entered once a day and left again. */
let atlasPromise: Promise<MachineAtlas | null> | null = null;

export function loadMachine(): Promise<MachineAtlas | null> {
  atlasPromise ??= fetchMachine();
  return atlasPromise;
}

async function fetchMachine(): Promise<MachineAtlas | null> {
  try {
    const manifest = await loadJson<MachineManifest>(`${ROOT}/manifest.json`);
    const [cabinet, strip, lever, marquee, window_, burst] = await Promise.all([
      loadPart(manifest.cabinet),
      loadPart(manifest.reel),
      loadPart(manifest.lever),
      loadEffect(manifest.effects.marquee),
      loadEffect(manifest.effects.window),
      loadEffect(manifest.effects.burst),
    ]);
    return {
      cabinet,
      strip,
      lever,
      marquee,
      window: window_,
      burst,
      reelSlots: manifest.cabinet.reels,
      reelWidth: manifest.cabinet.reelWidth,
      reelHeight: manifest.cabinet.reelHeight,
      bandCells: manifest.reel.cells ?? 1,
      band: manifest.reel.band ?? [],
      payLine: manifest.cabinet.payLine ?? manifest.cabinet.reelHeight / 2,
      leverAnchor: manifest.cabinet.lever,
      leverPivot: manifest.lever.pivot ?? [0, 0],
      trayMouth: manifest.cabinet.trayMouth,
      crown: manifest.cabinet.crown,
    };
  } catch (err) {
    console.warn('[machine] no machine atlas:', err);
    // Not memoized as a permanent failure: the next day should get another go.
    atlasPromise = null;
    return null;
  }
}

async function loadPart(sheet: SheetManifest): Promise<MachinePart> {
  return {
    image: await loadImage(`${ROOT}/${sheet.file}`),
    frameWidth: sheet.frameWidth,
    frameHeight: sheet.frameHeight,
    frames: sheet.frames ?? 1,
  };
}

async function loadEffect(sheet: SheetManifest): Promise<MachineEffect> {
  return {
    ...(await loadPart(sheet)),
    fps: sheet.fps ?? 12,
    anchorY: sheet.anchorY ?? sheet.frameHeight,
    loop: sheet.loop !== false,
  };
}

/**
 * Which CELL of the band shows `rarity` for reel `index`.
 *
 * A rarity sits in the band more than once (commons four times), and the three
 * reels deliberately pick DIFFERENT occurrences of it: three windows landing on
 * the identical cell would mean the band ran the same distance three times,
 * which is visible in the last half second as three reels stopping in lockstep.
 * Walking round the occurrences by reel index lands them on the same COLOUR out
 * of three different places on the strip, which is what a real machine does.
 *
 * Falls back to cell 0 rather than throwing: a reel that settled on a tier the
 * band has never heard of should still stop somewhere, because a window that
 * keeps spinning after the machine has paid out reads as a hung ceremony.
 */
export function bandCell(atlas: MachineAtlas, rarity: string, index: number): number {
  const hits: number[] = [];
  for (let cell = 0; cell < atlas.band.length; cell++) {
    if (atlas.band[cell] === rarity) hits.push(cell);
  }
  if (hits.length === 0) return 0;
  return hits[index % hits.length];
}
