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
 *   residue  hundreds more of the same, thrown outward by the blast and never
 *            cleaned up — `render/residue.ts` decides where they land
 *   pillar   a bottom-anchored PROP with three STATES, in the depth sort
 *   console  the same, and the only thing on the map you press
 *   charge / crown / emerge / rift / collapse / aura
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

/**
 * A ground decal, in TWO images with two blend modes.
 *
 * `image` is what the mark takes OUT of the ground and is drawn `multiply`:
 * drained soil, fissures, grit. Multiplying keeps the terrain's own texture
 * underneath and only removes light from it, which is what damage does to
 * ground — drawn `source-over` the dark pixels replace the soil instead, and
 * the field reads as stickers laid on dirt.
 *
 * `lit` is what it ADDS and is drawn `lighter`: crystal, the caught lip of a
 * crack, a hot speck. Additive is also the only way a two-pixel glint survives
 * compositing over a dark forest floor.
 *
 * See `GroundDecal` in make_rift.py, which decides the split by ramp value.
 */
export interface RiftDecalSheet {
  image: HTMLImageElement;
  lit: HTMLImageElement | null;
  frameWidth: number;
  frameHeight: number;
  frames: number;
}

/**
 * A decal sheet whose frame is chosen by DIRECTION rather than rolled.
 *
 * `frame = (direction * levels + level) * rolls + roll`. Mirrors
 * `corrupt_frame` in make_rift.py; the heading convention is `tracks.png`'s.
 */
export interface RiftAimedSheet extends RiftDecalSheet {
  directions: number;
  levels: number;
  rolls: number;
}

export interface RiftEffectSheet {
  image: HTMLImageElement;
  /**
   * One bitmap per OVERFEED TIER, `image` first.
   *
   * Only the anomaly's own sheets have these. A tier is a whole different
   * colour scheme for the same lattice (see `LEVEL_HUES` in make_rift.py), and
   * a colour scheme is not something a draw-time multiply can produce — so
   * they are baked, and they are separate files because four tiers of a
   * 64-frame loop in one strip is 16384px wide, right on the maximum texture
   * dimension a lot of hardware accepts. Empty for every other sheet.
   */
  levelImages: HTMLImageElement[];
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
  /** What the blast left on the ground. Six cuts; the scatter picks by distance. */
  residue: RiftDecalSheet | null;
  /** The ground it went through. Aimed: the frame comes from the tile's angle. */
  corrupt: RiftAimedSheet | null;
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
  /**
   * One-shot: the anomaly going out. Starts on `rift` frame 0 of the same
   * tier and ends on an empty frame — it hands off to NOTHING, which is why
   * the caller must not also fade it out. The sheet is the vanish.
   */
  collapse: RiftEffectSheet | null;
  /** Loop: the rainbow band a PAID console throws until somebody shuts it. */
  aura: RiftEffectSheet | null;
  /** The exit's torches: an unlit post in the depth sort, one cut, one state. */
  torch: RiftPropSheet | null;
  /** Loop: a torch burning the anomaly's fire. Anchored on the post's base. */
  torchfire: RiftEffectSheet | null;
  /** Paving for the threshold. Scattered client-side around the exit mouth. */
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

interface AimedManifest extends PropManifest {
  directions: number;
  levels: number;
  rolls: number;
}

interface EffectManifest extends PropManifest {
  fps: number;
  anchorY: number;
  loop?: boolean;
  tinted?: boolean;
  crownAt?: number;
  burstAt?: number;
  /** Overfeed tiers, and the file for each. `levelFiles[0]` repeats `file`. */
  levels?: number;
  levelFiles?: string[];
}

interface RiftManifest {
  tile: number;
  props: { pillar?: PropManifest; console?: PropManifest; torch?: PropManifest };
  decals: {
    scar?: PropManifest;
    residue?: PropManifest;
    corrupt?: AimedManifest;
    egress?: PropManifest;
  };
  effects: {
    charge?: EffectManifest;
    crown?: EffectManifest;
    emerge?: EffectManifest;
    rift?: EffectManifest;
    collapse?: EffectManifest;
    aura?: EffectManifest;
    torchfire?: EffectManifest;
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
    const [
      scar, residue, corrupt, egress, pillar, consoleSheet, torch,
      charge, crown, emerge, rift, collapse, aura, torchfire,
    ] = await Promise.all([
      manifest.decals.scar ? loadDecal(manifest.decals.scar) : null,
      manifest.decals.residue ? loadDecal(manifest.decals.residue) : null,
      manifest.decals.corrupt ? loadAimed(manifest.decals.corrupt) : null,
      manifest.decals.egress ? loadDecal(manifest.decals.egress) : null,
      manifest.props.pillar ? loadProp(manifest.props.pillar) : null,
      manifest.props.console ? loadProp(manifest.props.console) : null,
      manifest.props.torch ? loadProp(manifest.props.torch) : null,
      manifest.effects.charge ? loadEffect(manifest.effects.charge) : null,
      manifest.effects.crown ? loadEffect(manifest.effects.crown) : null,
      manifest.effects.emerge ? loadEffect(manifest.effects.emerge) : null,
      manifest.effects.rift ? loadEffect(manifest.effects.rift) : null,
      manifest.effects.collapse ? loadEffect(manifest.effects.collapse) : null,
      manifest.effects.aura ? loadEffect(manifest.effects.aura) : null,
      manifest.effects.torchfire ? loadEffect(manifest.effects.torchfire) : null,
    ]);
    return {
      tile: manifest.tile, scar, residue, corrupt, egress,
      pillar, console: consoleSheet, torch,
      charge, crown, emerge, rift, collapse, aura, torchfire,
    };
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

async function loadAimed(manifest: AimedManifest): Promise<RiftAimedSheet> {
  return {
    ...(await loadDecal(manifest)),
    directions: manifest.directions,
    levels: manifest.levels,
    rolls: manifest.rolls,
  };
}

async function loadEffect(manifest: EffectManifest): Promise<RiftEffectSheet> {
  const files = manifest.levelFiles?.length ? manifest.levelFiles : [manifest.file];
  const levelImages = await Promise.all(
    files.map((file) => loadImage(`${ROOT}/${file}`)),
  );
  const image = levelImages[0];
  return {
    image,
    levelImages,
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

/**
 * The bitmap for one overfeed tier of a sheet that has them.
 *
 * Clamped rather than checked: the server owns the tier count and the art owns
 * how many were baked, and a mismatch between the two must degrade to the
 * hottest sheet that exists rather than draw nothing on a pad the party is
 * standing at.
 */
export function riftLevelImage(sheet: RiftEffectSheet, level: number): CanvasImageSource {
  const banks = sheet.levelImages;
  if (banks.length <= 1) return sheet.image;
  const index = Math.max(0, Math.min(banks.length - 1, Math.floor(level)));
  return banks[index];
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
