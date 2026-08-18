/**
 * Rift atlas: the dressing every THRESHOLD in this game shares.
 *
 * Produced by server/tools/make_rift.py and served from /rift/
 * (assets/processed is Vite's publicDir).
 *
 * WHAT IS LEFT OF IT, AND WHY THE REST IS STILL ON DISK. This atlas was the
 * whole extraction point once — a sigil, standing stones and a tear in the
 * world hanging over them. The extraction point is a cargo platform now
 * (`render/platform.ts`), and four of these sheets survived the change because
 * they were never about the anomaly:
 *
 *   console   the one thing on the map you press. Unchanged, including its
 *             four states, because the VERBS did not change: wake it, load it,
 *             launch it, and a dead button afterwards
 *   torch     an unlit post in the depth sort, and the light that says
 *             "somebody dressed this place". The exit corridor wears four of
 *             them and every extraction pad wears one
 *   torchfire the flame those posts burn, anchored on the post's BASE
 *   aura      the rainbow band a PAID console throws until somebody deals
 *             with it
 *   egress    cut paving for the exit's threshold
 *
 * The anomaly's own sheets — `scar`, `pillar`, `charge`, `crown`, `emerge`,
 * `rift`, `collapse`, `residue`, `corrupt` — are still generated and still in
 * `assets/processed/rift/`. Nothing loads them today. They are kept because
 * the art is worth keeping, not because anything is half-migrated.
 *
 * EVERY EFFECT SHEET HERE BAKES ITS OWN COLOUR, and `tinted` is the flag that
 * says so. A flame is a ramp from a dull red root to a white core and a draw-
 * time multiply is a single hue, so `riftImage` refuses the tint rather than
 * trusting each call site to remember. The tint machinery is kept only because
 * `tinted` is a manifest flag a future sheet could set.
 *
 * Loading is best-effort: a missing atlas resolves to `null` and callers skip
 * the piece, so the game still runs with no assets built.
 */

import { loadImage, loadJson } from '../lib/image';
import { EffectTintCache } from './vfx';

export interface RiftPropSheet {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  /** How many distinct cuts the sheet holds. */
  shapes: number;
  /** How many states each cut has. Frame index is `shape * states + state`. */
  states: number;
}

/**
 * A ground decal, in TWO images with two blend modes.
 *
 * `image` is what the mark takes OUT of the ground and is drawn `multiply`:
 * drained soil, fissures, grit. Multiplying keeps the terrain's own texture
 * underneath and only removes light from it, which is what wear does to
 * ground — drawn `source-over` the dark pixels replace the soil instead, and
 * the field reads as stickers laid on dirt.
 *
 * `lit` is what it ADDS and is drawn `lighter`: the caught lip of a slab, a
 * hot speck. Additive is also the only way a two-pixel glint survives being
 * composited over a dark forest floor.
 */
export interface RiftDecalSheet {
  image: HTMLImageElement;
  lit: HTMLImageElement | null;
  frameWidth: number;
  frameHeight: number;
  frames: number;
}

export interface RiftEffectSheet {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  fps: number;
  /** Distance from the top of the frame to the point the effect sits on. */
  anchorY: number;
  loop: boolean;
  /** False when the art bakes its own colour — never tint those. */
  tinted: boolean;
  /** Per-colour copies. Only ever populated for a `tinted` sheet. */
  tints: EffectTintCache;
}

export interface RiftAtlas {
  tile: number;
  /** The button. Four states: idle, armed, READY, spent. */
  console: RiftPropSheet | null;
  /** A threshold's torch: an unlit post in the depth sort, one cut, one state. */
  torch: RiftPropSheet | null;
  /** Loop: a torch burning. Anchored on the post's base. */
  torchfire: RiftEffectSheet | null;
  /** Loop: the rainbow band a PAID console throws until somebody deals with it. */
  aura: RiftEffectSheet | null;
  /** Paving for the exit's threshold. Scattered client-side around the mouth. */
  egress: RiftDecalSheet | null;
}

interface PropManifest {
  file: string;
  /** The additive half, for ground decals. */
  litFile?: string;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  shapes?: number;
  states?: number;
}

interface EffectManifest extends PropManifest {
  fps: number;
  anchorY: number;
  loop?: boolean;
  tinted?: boolean;
}

interface RiftManifest {
  tile: number;
  props: { console?: PropManifest; torch?: PropManifest };
  decals: { egress?: PropManifest };
  effects: { aura?: EffectManifest; torchfire?: EffectManifest };
}

const ROOT = '/rift';

let atlasPromise: Promise<RiftAtlas | null> | null = null;

export function loadRift(): Promise<RiftAtlas | null> {
  atlasPromise ??= fetchRift();
  return atlasPromise;
}

async function fetchRift(): Promise<RiftAtlas | null> {
  try {
    const manifest = await loadJson<RiftManifest>(`${ROOT}/manifest.json`);
    const [egress, consoleSheet, torch, aura, torchfire] = await Promise.all([
      manifest.decals.egress ? loadDecal(manifest.decals.egress) : null,
      manifest.props.console ? loadProp(manifest.props.console) : null,
      manifest.props.torch ? loadProp(manifest.props.torch) : null,
      manifest.effects.aura ? loadEffect(manifest.effects.aura) : null,
      manifest.effects.torchfire ? loadEffect(manifest.effects.torchfire) : null,
    ]);
    return { tile: manifest.tile, console: consoleSheet, torch, torchfire, aura, egress };
  } catch (err) {
    console.warn('[rift] no atlas, console and torches not drawn:', err);
    return null;
  }
}

async function loadProp(manifest: PropManifest): Promise<RiftPropSheet> {
  return {
    image: await loadImage(`${ROOT}/${manifest.file}`),
    frameWidth: manifest.frameWidth,
    frameHeight: manifest.frameHeight,
    frames: manifest.frames,
    shapes: manifest.shapes ?? 1,
    states: manifest.states ?? 1,
  };
}

async function loadDecal(manifest: PropManifest): Promise<RiftDecalSheet> {
  const [image, lit] = await Promise.all([
    loadImage(`${ROOT}/${manifest.file}`),
    manifest.litFile ? loadImage(`${ROOT}/${manifest.litFile}`) : null,
  ]);
  return {
    image,
    lit,
    frameWidth: manifest.frameWidth,
    frameHeight: manifest.frameHeight,
    frames: manifest.frames,
  };
}

async function loadEffect(manifest: EffectManifest): Promise<RiftEffectSheet> {
  const image = await loadImage(`${ROOT}/${manifest.file}`);
  return {
    image,
    frameWidth: manifest.frameWidth,
    frameHeight: manifest.frameHeight,
    frames: manifest.frames,
    fps: manifest.fps,
    anchorY: manifest.anchorY,
    loop: manifest.loop ?? false,
    tinted: manifest.tinted ?? true,
    tints: new EffectTintCache(image),
  };
}

/**
 * The bitmap to draw for this sheet, tinted or not.
 *
 * A sheet that bakes its own colour ignores `color` entirely rather than
 * trusting every call site to remember — getting this wrong on a flame costs
 * the whole ramp and would be easy to miss in a dark forest.
 */
export function riftImage(sheet: RiftEffectSheet, color: string | null): CanvasImageSource {
  return sheet.tinted && color ? sheet.tints.get(color) : sheet.image;
}

/** Frame index for a sheet, held on the last frame once a one-shot is over. */
export function riftFrame(sheet: RiftEffectSheet, elapsed: number): number {
  const index = Math.floor(Math.max(0, elapsed) * sheet.fps);
  if (sheet.loop) return ((index % sheet.frames) + sheet.frames) % sheet.frames;
  return Math.max(0, Math.min(sheet.frames - 1, index));
}

/** Frame index for a prop. `state` is authoritative — never hash one. */
export function riftPropFrame(sheet: RiftPropSheet, shape: number, state: number): number {
  const cut = ((shape % sheet.shapes) + sheet.shapes) % sheet.shapes;
  const step = Math.max(0, Math.min(sheet.states - 1, state));
  return Math.min(sheet.frames - 1, cut * sheet.states + step);
}
