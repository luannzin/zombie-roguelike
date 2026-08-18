/**
 * Upgrade machine atlas: the cabinet, its parts and its light.
 *
 * Produced by server/tools/make_machine.py and served from /machine/.
 *
 * FOUR SHAPES, and the split is the same one every other atlas here keeps:
 *
 *   The CABINET is a bottom-anchored PROP. It stands in the entity depth sort
 *   beside the tables and the merchant, so a body walks in front of and behind
 *   it, and it takes the darkness multiply like any other object in a glade.
 *
 *   The REEL and the LEVER are PARTS. They are blitted into the cabinet's own
 *   frame at offsets the manifest carries (`reels`, `lever`), because where a
 *   window is on the front panel is a property of the ART and a hardcoded
 *   offset here would drift the first time the cabinet was redrawn.
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
  cabinet: MachinePart;
  /** Frame 0 is idle; frame 1 is the shell settled after a pull. */
  reel: MachinePart;
  lever: MachinePart;
  marquee: MachineEffect;
  window: MachineEffect;
  burst: MachineEffect;
  /** Top-left of each reel window inside the cabinet frame. */
  reelSlots: Array<[number, number]>;
  reelWidth: number;
  reelHeight: number;
  /** How many of the reel sheet's frames are spin blur, before the faces. */
  spinFrames: number;
  /** Rarity order of the reel faces, after the blur frames. */
  rarities: string[];
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
  frames: number;
  fps?: number;
  anchorY?: number;
  loop?: boolean;
  pivot?: [number, number];
  spinFrames?: number;
  rarities?: string[];
}

interface CabinetManifest extends SheetManifest {
  reels: Array<[number, number]>;
  reelWidth: number;
  reelHeight: number;
  lever: [number, number];
  trayMouth: [number, number];
  crown: [number, number];
}

interface MachineManifest {
  cabinet: CabinetManifest;
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
    const [cabinet, reel, lever, marquee, window_, burst] = await Promise.all([
      loadPart(manifest.cabinet),
      loadPart(manifest.reel),
      loadPart(manifest.lever),
      loadEffect(manifest.effects.marquee),
      loadEffect(manifest.effects.window),
      loadEffect(manifest.effects.burst),
    ]);
    return {
      cabinet,
      reel,
      lever,
      marquee,
      window: window_,
      burst,
      reelSlots: manifest.cabinet.reels,
      reelWidth: manifest.cabinet.reelWidth,
      reelHeight: manifest.cabinet.reelHeight,
      spinFrames: manifest.reel.spinFrames ?? 4,
      rarities: manifest.reel.rarities ?? [],
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
    frames: sheet.frames,
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
 * Which reel-sheet frame shows rarity `rarity`.
 *
 * Falls back to the FIRST face rather than to a blur frame: a reel that
 * settled on a tier the sheet has never heard of should stop on something,
 * because a window that keeps spinning after the machine has paid out reads as
 * the ceremony having hung.
 */
export function reelFace(atlas: MachineAtlas, rarity: string): number {
  const index = atlas.rarities.indexOf(rarity);
  return atlas.spinFrames + (index >= 0 ? index : 0);
}

/** The blur frame for `time`, offset per reel so the three never lock step. */
export function reelBlur(atlas: MachineAtlas, time: number, reel: number): number {
  const spin = Math.max(1, atlas.spinFrames);
  return Math.floor(time * 26 + reel * 1.7) % spin;
}
