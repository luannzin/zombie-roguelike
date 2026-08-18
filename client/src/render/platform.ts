/**
 * Platform atlas: the extraction rig's art.
 *
 * Produced by server/tools/make_platform.py and served from /platform/
 * (assets/processed is Vite's publicDir).
 *
 * THIS ATLAS SPANS ALL THREE SHAPES, which is why it is its own module rather
 * than more entries in `scenery.ts` or `vfx.ts`:
 *
 *   platform  a bottom-anchored PROP with two STATES, in the depth sort
 *   drone     the same, four of them, parked or turning
 *   imprint   a flat DECAL, uncovered the frame the skid breaks ground
 *   rotor / strobe / downwash / burst
 *             effect TIMELINES anchored on `anchorY`, drawn additively after
 *             the darkness pass
 *
 * The prop frames are STATES, not variants. Nothing here may be rolled: the
 * frame index says what the machine IS, and picking one by hash would make the
 * rig flicker between running and dead.
 *
 * EVERY SHEET HERE BAKES ITS OWN COLOUR (`tinted: false`). A rotor disc is
 * white-hot dust and a nav light is red; a draw-time multiply is a single hue
 * and could produce neither. The tint machinery in `vfx.ts` is not reached
 * from this module at all.
 *
 * THE LAYOUT BLOCK IS PART OF THE ART. `eyes` is where on the platform sprite
 * each rope is tied and `rope.length` is how much line each drone was rigged
 * with — the client draws the rigging from those two numbers, because a rope
 * between a fixed eye and a drone that climbs, strains and then flies off
 * cannot be a sprite. `server/app/rift.py` ships the world positions; this
 * ships the pixels inside them.
 *
 * Loading is best-effort: a missing atlas resolves to `null` and callers skip
 * the structure, so the game still runs with no assets built.
 */

import { loadImage, loadJson } from '../lib/image';

export interface PlatformPropSheet {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  /** How many states each piece has. Frame index IS the state. */
  states: number;
}

/**
 * A ground decal, in TWO images with two blend modes.
 *
 * `image` is what the mark takes OUT of the ground and is drawn `multiply`:
 * pressed soil, oil, the dents. Multiplying keeps the terrain's own texture
 * underneath and only removes light from it, which is what weight does to
 * ground — drawn `source-over` the dark pixels replace the soil instead and
 * the mark reads as a sticker laid on dirt.
 *
 * `lit` is what it ADDS and is drawn `lighter`: grit and loose bolts. Additive
 * is also the only way a two-pixel glint survives a dark forest floor.
 */
export interface PlatformDecalSheet {
  image: HTMLImageElement;
  lit: HTMLImageElement | null;
  frameWidth: number;
  frameHeight: number;
}

export interface PlatformEffectSheet {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  fps: number;
  /** Distance from the top of the frame to the point the effect sits on. */
  anchorY: number;
  loop: boolean;
}

/** A point on the platform sprite, in pixels from its contact point. */
export interface PlatformPoint {
  dx: number;
  dy: number;
}

export interface PlatformLayout {
  /** The four lift eyes, in the same corner order the server places drones. */
  eyes: PlatformPoint[];
  /** How much line each drone was rigged with, in pixels. Sets hover height. */
  ropeLength: number;
  /** Where the rotor plane sits above a drone's own contact point. */
  rotorY: number;
}

export interface PlatformAtlas {
  tile: number;
  platform: PlatformPropSheet | null;
  drone: PlatformPropSheet | null;
  imprint: PlatformDecalSheet | null;
  /** Loop: four discs turning. Drawn over every drone that is running. */
  rotor: PlatformEffectSheet | null;
  /** Loop: a live drone's nav lights, blinking. */
  strobe: PlatformEffectSheet | null;
  /** Loop: rotor wash under a rig that is straining against the ground. */
  downwash: PlatformEffectSheet | null;
  /** One-shot: the ground letting go. Ends on an empty frame. */
  burst: PlatformEffectSheet | null;
  layout: PlatformLayout;
}

interface PropManifest {
  file: string;
  litFile?: string;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  states?: number;
  rotorY?: number;
}

interface EffectManifest extends PropManifest {
  fps: number;
  anchorY: number;
  loop?: boolean;
}

interface LayoutManifest {
  eyes?: PlatformPoint[];
  rope?: { length: number };
}

interface PlatformManifest {
  tile: number;
  props: { platform?: PropManifest; drone?: PropManifest };
  decals: { imprint?: PropManifest };
  effects: {
    rotor?: EffectManifest;
    strobe?: EffectManifest;
    downwash?: EffectManifest;
    burst?: EffectManifest;
  };
  layout: LayoutManifest;
}

const ROOT = '/platform';

/**
 * What the rig looks like if the manifest is missing its layout block.
 *
 * Authored against the 80x64 skid `make_platform.py` writes at tile 16. It
 * exists so a client talking to a half-built asset tree draws ropes to
 * plausible places instead of to `undefined` — the manifest's numbers win
 * whenever they arrive, and they always do in practice.
 */
const LAYOUT_FALLBACK: PlatformLayout = {
  eyes: [
    { dx: -33, dy: -37 },
    { dx: 27, dy: -59 },
    { dx: 33, dy: -37 },
    { dx: -27, dy: -59 },
  ],
  ropeLength: 67,
  rotorY: 9,
};

let atlasPromise: Promise<PlatformAtlas | null> | null = null;

export function loadPlatform(): Promise<PlatformAtlas | null> {
  atlasPromise ??= fetchPlatform();
  return atlasPromise;
}

async function fetchPlatform(): Promise<PlatformAtlas | null> {
  try {
    const manifest = await loadJson<PlatformManifest>(`${ROOT}/manifest.json`);
    const [platform, drone, imprint, rotor, strobe, downwash, burst] = await Promise.all([
      manifest.props.platform ? loadProp(manifest.props.platform) : null,
      manifest.props.drone ? loadProp(manifest.props.drone) : null,
      manifest.decals.imprint ? loadDecal(manifest.decals.imprint) : null,
      manifest.effects.rotor ? loadEffect(manifest.effects.rotor) : null,
      manifest.effects.strobe ? loadEffect(manifest.effects.strobe) : null,
      manifest.effects.downwash ? loadEffect(manifest.effects.downwash) : null,
      manifest.effects.burst ? loadEffect(manifest.effects.burst) : null,
    ]);
    const eyes = manifest.layout?.eyes;
    return {
      tile: manifest.tile,
      platform,
      drone,
      imprint,
      rotor,
      strobe,
      downwash,
      burst,
      layout: {
        eyes: eyes?.length ? eyes : LAYOUT_FALLBACK.eyes,
        ropeLength: manifest.layout?.rope?.length ?? LAYOUT_FALLBACK.ropeLength,
        rotorY: manifest.props.drone?.rotorY ?? LAYOUT_FALLBACK.rotorY,
      },
    };
  } catch (err) {
    console.warn('[platform] no atlas, extraction point not drawn:', err);
    return null;
  }
}

async function loadProp(manifest: PropManifest): Promise<PlatformPropSheet> {
  return {
    image: await loadImage(`${ROOT}/${manifest.file}`),
    frameWidth: manifest.frameWidth,
    frameHeight: manifest.frameHeight,
    frames: manifest.frames,
    states: manifest.states ?? manifest.frames,
  };
}

async function loadDecal(manifest: PropManifest): Promise<PlatformDecalSheet> {
  const [image, lit] = await Promise.all([
    loadImage(`${ROOT}/${manifest.file}`),
    manifest.litFile ? loadImage(`${ROOT}/${manifest.litFile}`) : null,
  ]);
  return {
    image,
    lit,
    frameWidth: manifest.frameWidth,
    frameHeight: manifest.frameHeight,
  };
}

async function loadEffect(manifest: EffectManifest): Promise<PlatformEffectSheet> {
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

/** Frame index for a sheet, held on the last frame once a one-shot is over. */
export function platformFrame(sheet: PlatformEffectSheet, elapsed: number): number {
  const index = Math.floor(Math.max(0, elapsed) * sheet.fps);
  if (sheet.loop) return ((index % sheet.frames) + sheet.frames) % sheet.frames;
  return Math.max(0, Math.min(sheet.frames - 1, index));
}

/** Frame index for a prop. `state` is authoritative — never hash one. */
export function platformPropFrame(sheet: PlatformPropSheet, state: number): number {
  return Math.max(0, Math.min(sheet.frames - 1, Math.floor(state)));
}
