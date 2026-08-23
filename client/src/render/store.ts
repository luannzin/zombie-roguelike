/**
 * Store atlas: the shop, and everything in it.
 *
 * Produced by server/tools/make_store.py and served from /store/.
 *
 * IT SHIPS A BUILDING AGAIN. The zone was a clearing for a long time and this
 * atlas was small because of it — soil from `terrain/`, the same trees as
 * everywhere else, and only what the trader carried in. The shop is a BRICK
 * BUILDING now at the north end of an outdoor apron, so two surfaces came
 * back: `brick`, the masonry, and `tilefloor`, the laid floor inside it. What
 * did not come back is the old interior's argument — the building is the far
 * end of a walk across a lit yard, not the whole zone.
 *
 * Four shapes, drawn in four different places in the frame:
 *
 *   GROUND is baked flat into the ground canvas with the soil, under
 *   everything, with no keyline and no shadow. Just `tilefloor`.
 *
 *   PROPS stand up — the masonry, the counter, the shelves, the tables, the
 *   lamps, his crates, his cart and the torches. Bottom-anchored on a contact
 *   point and depth-sorted with the party, so a body passes in front of and
 *   behind them. `brick` is a prop for exactly that reason: a wall tile is two
 *   tiles of sprite on a one-tile footprint, so it has to sort like a tree's
 *   canopy does, and each wall tile covers the face of the one behind it — see
 *   `make_store.make_brick` on why there is no autotile mask.
 *
 *   DECALS lie flat. The mats, drawn on the ground under the furniture.
 *
 *   EFFECTS are additive and drawn AFTER the darkness pass, because a fire is
 *   a light source and not a thing being lit. Unlike `vfx.ts`'s greyscale
 *   sheets these carry their own colour (`tinted: false`): a flame is a ramp
 *   from a dull red root to a white core, and a single draw-time multiply
 *   cannot produce a ramp — the same call `make_rift.py` makes.
 *
 * THREE NUMBERS LIVE IN THE ART RATHER THAN IN THE CLIENT, and all three are
 * pose data. `table.topY` is the pixel row the goods rest on, per pedestal
 * frame — the four pedestals are deliberately different heights, so a single
 * hardcoded offset would float one gun and sink another. `lamp.hangY` is how
 * far above its floor contact a lamp's body hangs, and `lamp.flameY` is where
 * `lampfire` burns inside its glass. A lamp is anchored on the FLOOR like
 * every other prop and is simply transparent for the two tiles between; if
 * the client picked the hang height instead, the sprite, the flame and the
 * pool of light the server places would end up at three different heights.
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
  /**
   * Torch: where its flame burns inside the head, per frame.
   * Lamp: the single row its flame burns at, shared by both frames.
   */
  flameY?: number[] | number;
  /** Lamp only: how far its body hangs above its floor contact, in pixels. */
  hangY?: number;
  /**
   * Brick only: how many TALL frames come first on the sheet. The rest are the
   * knee-high ones. Shipped by the generator rather than assumed, so the split
   * is never a constant on this side — see `make_store.make_brick`.
   */
  tall?: number;
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
  /**
   * THE MASONRY: two wear variants at each of two HEIGHTS, `tall` of them
   * first. A back or side wall stands a full tile above its own footprint; the
   * front wall is knee-high so the camera looks over it into the room. Which
   * one a tile gets is decided by whether the shop's floor is north of it —
   * see `make_store.make_brick`.
   */
  brick: StoreProp;
  /** The shop's laid floor, baked into the ground canvas with the soil. */
  tilefloor: StoreDecal;
  /** Six round pedestals. `topY` is the row the goods rest on, per frame. */
  table: StoreProp;
  /** Wall shelving behind the counter. Decoration; none of it opens. */
  shelf: StoreProp;
  /** Shop-floor decoration. None of it opens either — see the generator. */
  crate: StoreProp;
  /**
   * THE AMMUNITION CRATES, one frame per calibre, and the only boxes in this
   * atlas drawn OPEN. That is deliberate and it is the whole tell: `crate` is
   * roped and lidded because nothing in it may be touched, and these are lidless
   * with rounds standing out of them because they are what the party buys from.
   * Which frame a crate wears is the server's word — see `AmmoBox.variant`.
   */
  ammo: StoreProp;
  /**
   * The lamps that light the room, on chains from the beams. Anchored on the
   * FLOOR; `hangY` is where the body sits above that contact.
   */
  lamp: StoreProp;
  /** His gear: crates, a barrel, a rack, a shelf, a strongbox. Never opened. */
  kit: StoreProp;
  /**
   * HIS CART, one frame, parked on the west rim — the biggest sprite in the
   * zone and the one that says where the stock came from. See the section
   * comment above `make_wagon` in server/tools/make_store.py.
   */
  wagon: StoreProp;
  /**
   * The L he trades over, as three tiling sections: 0 elbow, 1 running east,
   * 2 running south. The server ships one row per section with its kind, so
   * the shape of the L is an offset table rather than a sprite.
   */
  counter: StoreProp;
  torch: StoreProp;
  rug: StoreDecal;
  torchfire: StoreEffect;
  /** The same fire as `torchfire`, smaller, burning inside a lamp's glass. */
  lampfire: StoreEffect;
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
  flameY?: number[] | number;
  hangY?: number;
  tall?: number;
  fps?: number;
  anchorY?: number;
  loop?: boolean;
}

type PropName =
  | 'brick' | 'table' | 'shelf' | 'crate' | 'ammo' | 'lamp'
  | 'kit' | 'wagon' | 'counter' | 'torch';

interface StoreManifest {
  tile: number;
  ground: Record<'tilefloor', SheetManifest>;
  props: Record<PropName, SheetManifest>;
  decals: Record<'rug', SheetManifest>;
  effects: Record<'torchfire' | 'lampfire' | 'glow', SheetManifest>;
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
    const [
      brick, tilefloor, table, shelf, crate, ammo, lamp,
      kit, wagon, counter, torch, rug, torchfire, lampfire, glow, coin,
    ] = await Promise.all([
      loadProp(manifest.props.brick),
      loadDecal(manifest.ground.tilefloor),
      loadProp(manifest.props.table),
      loadProp(manifest.props.shelf),
      loadProp(manifest.props.crate),
      loadProp(manifest.props.ammo),
      loadProp(manifest.props.lamp),
      loadProp(manifest.props.kit),
      loadProp(manifest.props.wagon),
      loadProp(manifest.props.counter),
      loadProp(manifest.props.torch),
      loadDecal(manifest.decals.rug),
      loadEffect(manifest.effects.torchfire),
      loadEffect(manifest.effects.lampfire),
      loadEffect(manifest.effects.glow),
      // Not fatal: a price with no coin beside it is still a price.
      loadImage('/hud/coin.png').catch(() => null),
    ]);
    return {
      brick, tilefloor, table, shelf, crate, ammo, lamp,
      kit, wagon, counter, torch, rug, torchfire, lampfire, glow, coin,
    };
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
    hangY: sheet.hangY,
    tall: sheet.tall,
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

/** The row the goods rest on for table frame `variant`, in frame pixels. */
export function tableTopY(table: StoreProp, variant: number): number {
  const rows = table.topY;
  if (!rows || rows.length === 0) return 0;
  return rows[variant % rows.length];
}

/**
 * Where a prop's flame burns for frame `variant`, in frame pixels.
 *
 * Takes a number OR a list, because the two lit props answer the question
 * differently and both answers are art. A torch's two heads are different
 * shapes and hold their fire at different heights, so it ships a row per
 * frame; a lamp's two shades hang the same body off the same chain, so it
 * ships one row for both. Reading a scalar as a one-element list is cheaper
 * than making the generator pad it.
 */
export function flameRow(prop: StoreProp, variant: number): number {
  const rows = prop.flameY;
  if (rows == null) return 0;
  if (typeof rows === 'number') return rows;
  if (rows.length === 0) return 0;
  return rows[variant % rows.length];
}

/** How far a lamp's body hangs above its floor contact, in frame pixels. */
export function lampHangY(lamp: StoreProp): number {
  return lamp.hangY ?? 0;
}
