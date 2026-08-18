/**
 * Store atlas: the merchant's own kit.
 *
 * Produced by server/tools/make_store.py and served from /store/.
 *
 * It is a SMALL atlas on purpose. The camp used to be an interior and shipped
 * its own floor, walls and hanging lamps; it is a clearing now, so the ground
 * is `terrain/`'s forest soil, the shelter is `scenery/`'s tent, and the trees
 * are the same trees as everywhere else. What is left here is only what the
 * trader brought with him: his tables, the mat he trades over, the torches he
 * drove in, and the pool that says which weapon you are standing at.
 *
 * Three shapes, drawn in three different places in the frame:
 *
 *   PROPS stand up — tables and torches. Bottom-anchored on a contact point
 *   and depth-sorted with the party, so a body passes in front of and behind
 *   them.
 *
 *   DECALS lie flat. Just the mat, drawn on the ground under the merchant.
 *
 *   EFFECTS are additive and drawn AFTER the darkness pass, because a fire is
 *   a light source and not a thing being lit. Unlike `vfx.ts`'s greyscale
 *   sheets these carry their own colour (`tinted: false`): a flame is a ramp
 *   from a dull red root to a white core, and a single draw-time multiply
 *   cannot produce a ramp — the same call `make_rift.py` makes.
 *
 * `table.topY` is the one piece of gameplay geometry that lives in the art:
 * the pixel row a weapon rests on, per table frame. Three of the four tables
 * are different heights on purpose, so a single hardcoded offset would float
 * one gun and sink another.
 *
 * Loading is best-effort, like every other atlas here: a missing manifest
 * resolves to `null` and the layer draws nothing rather than taking the zone
 * down with it.
 */

import { loadImage, loadJson } from '../lib/image';

export interface StoreProp {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  /** Table only: the pixel row the stock lies on, per frame. */
  topY?: number[];
  /** Torch only: where its flame burns inside the head, per frame. */
  flameY?: number[];
}

export interface StoreDecal {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
}

export interface StoreEffect {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  fps: number;
  /** The row the effect happens at, measured down from the frame's top. */
  anchorY: number;
  loop: boolean;
}

export interface StoreAtlas {
  table: StoreProp;
  /** His gear: crates, a barrel, a rack, a shelf, a strongbox. Never opened. */
  kit: StoreProp;
  torch: StoreProp;
  rug: StoreDecal;
  torchfire: StoreEffect;
  glow: StoreEffect;
  /**
   * The HUD coin (`/hud/coin.png`), loaded here rather than with the rest of
   * the HUD's icons because the only place the CANVAS ever draws one is the
   * price above a table. It is the same 8x8 disc the bag and the feed quest
   * use, on purpose: a price and a balance have to be denominated in a coin
   * the player already recognises, or the shop reads as its own economy.
   *
   * Null if it is missing — the price still draws, just as a bare number.
   */
  coin: HTMLImageElement | null;
}

/** Frame size of `/hud/coin.png`. Must match make_hud_icons.py. */
export const COIN_PX = 8;

interface SheetManifest {
  file: string;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  topY?: number[];
  flameY?: number[];
  fps?: number;
  anchorY?: number;
  loop?: boolean;
}

interface StoreManifest {
  tile: number;
  props: Record<'table' | 'kit' | 'torch', SheetManifest>;
  decals: Record<'rug', SheetManifest>;
  effects: Record<'torchfire' | 'glow', SheetManifest>;
}

const ROOT = '/store';

/**
 * One atlas per session. The camp is entered once a day and left again, and
 * re-fetching the sheets on every arrival would spend the hand-over frames
 * painting an empty clearing.
 */
let atlasPromise: Promise<StoreAtlas | null> | null = null;

export function loadStore(): Promise<StoreAtlas | null> {
  atlasPromise ??= fetchStore();
  return atlasPromise;
}

async function fetchStore(): Promise<StoreAtlas | null> {
  try {
    const manifest = await loadJson<StoreManifest>(`${ROOT}/manifest.json`);
    const [table, kit, torch, rug, torchfire, glow, coin] = await Promise.all([
      loadProp(manifest.props.table),
      loadProp(manifest.props.kit),
      loadProp(manifest.props.torch),
      loadDecal(manifest.decals.rug),
      loadEffect(manifest.effects.torchfire),
      loadEffect(manifest.effects.glow),
      // Not fatal: a price with no coin beside it is still a price.
      loadImage('/hud/coin.png').catch(() => null),
    ]);
    return { table, kit, torch, rug, torchfire, glow, coin };
  } catch (err) {
    console.warn('[store] no store atlas:', err);
    // Not memoized as a permanent failure: the next day should get another go.
    atlasPromise = null;
    return null;
  }
}

async function loadProp(sheet: SheetManifest): Promise<StoreProp> {
  return {
    image: await loadImage(`${ROOT}/${sheet.file}`),
    frameWidth: sheet.frameWidth,
    frameHeight: sheet.frameHeight,
    frames: sheet.frames,
    topY: sheet.topY,
    flameY: sheet.flameY,
  };
}

async function loadDecal(sheet: SheetManifest): Promise<StoreDecal> {
  return {
    image: await loadImage(`${ROOT}/${sheet.file}`),
    frameWidth: sheet.frameWidth,
    frameHeight: sheet.frameHeight,
    frames: sheet.frames,
  };
}

async function loadEffect(sheet: SheetManifest): Promise<StoreEffect> {
  return {
    image: await loadImage(`${ROOT}/${sheet.file}`),
    frameWidth: sheet.frameWidth,
    frameHeight: sheet.frameHeight,
    frames: sheet.frames,
    fps: sheet.fps ?? 12,
    anchorY: sheet.anchorY ?? sheet.frameHeight,
    loop: sheet.loop !== false,
  };
}

/** The row a weapon rests on for table frame `variant`, in frame pixels. */
export function tableTopY(table: StoreProp, variant: number): number {
  const rows = table.topY;
  if (!rows || rows.length === 0) return 0;
  return rows[variant % rows.length];
}

/** Where a torch's flame burns for frame `variant`, in frame pixels. */
export function torchFlameY(torch: StoreProp, variant: number): number {
  const rows = torch.flameY;
  if (!rows || rows.length === 0) return 0;
  return rows[variant % rows.length];
}
