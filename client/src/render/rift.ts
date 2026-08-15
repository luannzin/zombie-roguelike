/**
 * Rift atlas: the extraction structure's art.
 *
 * Produced by server/tools/make_rift.py and served from /rift/
 * (assets/processed is Vite's publicDir).
 *
 * THIS ATLAS SPANS ALL THREE SHAPES, which is why it is its own module rather
 * than more entries in `scenery.ts` or `vfx.ts`:
 *
 *   scar     a flat DECAL, drawn on the floor with the boot prints
 *   pillar   a bottom-anchored PROP with two STATES, in the depth sort
 *   console  the same, and the only thing on the map you press
 *   charge / crown / emerge / rift
 *            effect TIMELINES anchored on `anchorY`, drawn additively after
 *            the darkness pass
 *
 * The prop frames are STATES, not variants. Nothing here may be rolled: the
 * frame index says what the structure IS, and picking one by hash would make
 * the extraction point flicker between on and off.
 *
 * EVERY EFFECT SHEET HERE BAKES ITS OWN COLOUR, and `tinted` is the flag that
 * says so. The structure is painted from one iridescent prism — the anomaly's
 * openings, and the pillars' conduit running violet at the foot through cyan to
 * a white crown — and the one thing a draw-time tint can never produce is six
 * pastels in a frame, because a multiply is a single hue. So `riftImage`
 * refuses the tint rather than trusting each call site to remember, and the
 * tint machinery is kept only because `tinted` is a manifest flag that a future
 * sheet could set. `--scene-beacon` survives as the beacon GLOW's tone, on the
 * scene-light list, and nothing else.
 *
 * Loading is best-effort: a missing atlas resolves to `null` and callers skip
 * the structure, so the game still runs with no assets built.
 */

import { loadImage, loadJson } from '../lib/image';
import { EffectTintCache } from './vfx';

export interface RiftPropSheet {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  /** How many distinct cuts the sheet holds (pillar: 4, console: 1). */
  shapes: number;
  /** How many states each cut has. Frame index is `shape * states + state`. */
  states: number;
}

export interface RiftDecalSheet {
  image: HTMLImageElement;
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
  /**
   * For a one-shot, the fraction of the timeline at which the sheet flashes —
   * `crownAt` / `burstAt` in the manifest. That frame is where the PROP
   * underneath swaps state, because the flash is what hides the swap.
   */
  handoffAt: number;
  /** Per-colour copies. Only ever populated for a `tinted` sheet. */
  tints: EffectTintCache;
}

export interface RiftAtlas {
  tile: number;
  scar: RiftDecalSheet | null;
  pillar: RiftPropSheet | null;
  console: RiftPropSheet | null;
  /** One-shot: a stone waking. Hands off to `crown` on its last frame. */
  charge: RiftEffectSheet | null;
  /** Loop: a woken stone holding. */
  crown: RiftEffectSheet | null;
  /** One-shot: the anomaly tearing open. Hands off to `rift`. */
  emerge: RiftEffectSheet | null;
  /** Loop: the anomaly at rest, and it never looks restful. */
  rift: RiftEffectSheet | null;
}

interface PropManifest {
  file: string;
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
  crownAt?: number;
  burstAt?: number;
}

interface RiftManifest {
  tile: number;
  props: { pillar?: PropManifest; console?: PropManifest };
  decals: { scar?: PropManifest };
  effects: {
    charge?: EffectManifest;
    crown?: EffectManifest;
    emerge?: EffectManifest;
    rift?: EffectManifest;
  };
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
    const [scar, pillar, consoleSheet, charge, crown, emerge, rift] = await Promise.all([
      manifest.decals.scar ? loadDecal(manifest.decals.scar) : null,
      manifest.props.pillar ? loadProp(manifest.props.pillar) : null,
      manifest.props.console ? loadProp(manifest.props.console) : null,
      manifest.effects.charge ? loadEffect(manifest.effects.charge) : null,
      manifest.effects.crown ? loadEffect(manifest.effects.crown) : null,
      manifest.effects.emerge ? loadEffect(manifest.effects.emerge) : null,
      manifest.effects.rift ? loadEffect(manifest.effects.rift) : null,
    ]);
    return { tile: manifest.tile, scar, pillar, console: consoleSheet, charge, crown, emerge, rift };
  } catch (err) {
    console.warn('[rift] no atlas, extraction point not drawn:', err);
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
  return {
    image: await loadImage(`${ROOT}/${manifest.file}`),
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
    handoffAt: manifest.crownAt ?? manifest.burstAt ?? 0.5,
    tints: new EffectTintCache(image),
  };
}

/**
 * The bitmap to draw for this sheet, tinted or not.
 *
 * A sheet that bakes its own colour ignores `color` entirely rather than
 * trusting every call site to remember — getting this wrong on the anomaly
 * costs the whole prism and would be easy to miss in a dark forest.
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
