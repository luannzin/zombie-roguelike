/**
 * Weapon VFX atlas: the muzzle, the shotgun's cone, and a round arriving.
 *
 * Produced by server/tools/make_weapon_vfx.py and served from /weapon-vfx/
 * (assets/processed is Vite's publicDir).
 *
 * SEPARATE FROM `vfx.ts`, AND THE SPLIT IS ABOUT TINT RATHER THAN ABOUT
 * TIDINESS. Everything in that atlas is greyscale and coloured at draw time
 * with whoever it belongs to: an arrival column is the colour of the player
 * arriving, the kindle roar is the colour of the fire. Fire from a barrel
 * belongs to nobody. These sheets ship with the ramp baked in and are drawn
 * with no tint at all, so a muzzle flash is the same fire whoever pulled the
 * trigger — which is also why they need no `TintCache` and no per-colour
 * canvas.
 *
 * ORIENTED, WHICH THE OTHER ATLAS IS NOT. Every frame here points RIGHT, the
 * same convention the held-gun atlas uses, and the caller rotates it onto the
 * aim. That is what `anchorX` is for: a muzzle flash is pinned to the BARREL
 * TIP on the frame's left edge and grows forward out of it, where a summon
 * column is pinned to the ground under its middle. Rotation happens about
 * (anchorX, anchorY).
 *
 * Loading is best-effort: a missing atlas resolves to `null` and the effects
 * layer falls back to the primitives it used to draw, so the game still runs
 * with no assets built.
 */

import { loadImage, loadJson } from '../lib/image';

export interface WeaponVfxSheet {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  /** Playback rate. The sheet's duration is `frames / fps` seconds. */
  fps: number;
  /**
   * The point the effect is pinned to and rotates about, in frame pixels.
   * `anchorX` is measured from the LEFT edge — see the module note.
   */
  anchorX: number;
  anchorY: number;
}

export interface WeaponVfxAtlas {
  /** Tile size the sheets were generated at. */
  tile: number;
  /** The bloom at the barrel of any gun. Scaled by the weapon's `flash`. */
  muzzle: WeaponVfxSheet | null;
  /** The shotgun's cone, ring and smoke. One per shell, not per pellet. */
  blast: WeaponVfxSheet | null;
  /** A round arriving somewhere. Centre-anchored. */
  impact: WeaponVfxSheet | null;
}

interface SheetManifest {
  file: string;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  fps: number;
  anchorX: number;
  anchorY: number;
}

interface WeaponVfxManifest {
  tile: number;
  effects: {
    muzzle?: SheetManifest;
    blast?: SheetManifest;
    impact?: SheetManifest;
  };
}

const ROOT = '/weapon-vfx';

let atlasPromise: Promise<WeaponVfxAtlas | null> | null = null;

export function loadWeaponVfx(): Promise<WeaponVfxAtlas | null> {
  atlasPromise ??= fetchWeaponVfx();
  return atlasPromise;
}

async function fetchWeaponVfx(): Promise<WeaponVfxAtlas | null> {
  try {
    const manifest = await loadJson<WeaponVfxManifest>(`${ROOT}/manifest.json`);
    const [muzzle, blast, impact] = await Promise.all([
      manifest.effects.muzzle ? loadSheet(manifest.effects.muzzle) : null,
      manifest.effects.blast ? loadSheet(manifest.effects.blast) : null,
      manifest.effects.impact ? loadSheet(manifest.effects.impact) : null,
    ]);
    return { tile: manifest.tile, muzzle, blast, impact };
  } catch (err) {
    console.warn('[weapon-vfx] no atlas, shots draw as primitives:', err);
    return null;
  }
}

async function loadSheet(manifest: SheetManifest): Promise<WeaponVfxSheet> {
  const image = await loadImage(`${ROOT}/${manifest.file}`);
  return {
    image,
    frameWidth: manifest.frameWidth,
    frameHeight: manifest.frameHeight,
    frames: manifest.frames,
    fps: manifest.fps,
    anchorX: manifest.anchorX,
    anchorY: manifest.anchorY,
  };
}

/**
 * How long one play of `sheet` lasts, in seconds.
 *
 * Effects here are spawned with a life taken FROM the sheet rather than
 * chosen by the caller, so a flash is over exactly when its last frame is
 * and never holds on a frozen final frame or cuts off mid-bloom. Change the
 * frame count in the generator and the timing follows.
 */
export function sheetLife(sheet: WeaponVfxSheet): number {
  return sheet.frames / sheet.fps;
}

/** Frame index for a one-shot sheet, clamped to the last frame. */
export function weaponFrame(sheet: WeaponVfxSheet, elapsed: number): number {
  const index = Math.floor(elapsed * sheet.fps);
  return Math.max(0, Math.min(sheet.frames - 1, index));
}

/**
 * Draw one play of `sheet` at a world point, rotated onto `(dx, dy)`.
 *
 * ADDITIVE and un-tinted, and the caller is expected to already be in world
 * space after the darkness pass — a muzzle flash is a light source, not a
 * thing being lit, which is the same rule every other effect in this game
 * follows.
 *
 * `scale` is the weapon's own `flash` number, so a Glock and an AWP draw the
 * same art at the sizes their rounds deserve. It scales about the anchor, so
 * the fire stays welded to the barrel however big it gets.
 */
export function drawOriented(
  ctx: CanvasRenderingContext2D,
  sheet: WeaponVfxSheet,
  x: number,
  y: number,
  dx: number,
  dy: number,
  age: number,
  alpha: number,
  scale: number,
): void {
  const frame = weaponFrame(sheet, age);
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.translate(x, y);
  ctx.rotate(Math.atan2(dy, dx));
  ctx.scale(scale, scale);
  ctx.drawImage(
    sheet.image,
    frame * sheet.frameWidth,
    0,
    sheet.frameWidth,
    sheet.frameHeight,
    -sheet.anchorX,
    -sheet.anchorY,
    sheet.frameWidth,
    sheet.frameHeight,
  );
  ctx.restore();
}
