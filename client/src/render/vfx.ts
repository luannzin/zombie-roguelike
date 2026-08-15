/**
 * VFX atlas: pre-rendered effect animations.
 *
 * Produced by server/tools/make_vfx.py and served from /vfx/
 * (assets/processed is Vite's publicDir).
 *
 * These are not props. A prop sheet's frames are variants of one object and it
 * is bottom-anchored on a tile; an effect sheet's frames are a TIMELINE played
 * once, anchored on the point the effect happens at. That point is `anchorY`
 * pixels down from the top of the frame rather than the bottom edge, because
 * an impact needs rows below the contact line to throw a shockwave into.
 *
 * Every effect here is drawn ADDITIVELY, after the darkness pass — the same
 * rule the arena's renderer follows for muzzle flashes. A beam of light is a
 * light source, not a thing being lit.
 *
 * The art is GREYSCALE. An effect that belongs to a player is tinted here with
 * that player's colour (`effectImage`), so the column delivering somebody to
 * the fire is the same colour as their row in the roster and the swatch on
 * their character. An effect that belongs to the fire — the kindle roar —
 * is tinted with `fire.core` the same way. See server/tools/make_vfx.py.
 *
 * Loading is best-effort: a missing atlas resolves to `null` and callers skip
 * the effect, so the game still runs with no assets built.
 */

import { createSurface, sourceSize } from '../lib/canvas';
import { loadImage, loadJson } from '../lib/image';

export interface VfxSheet {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  /** Playback rate. The sheet's duration is `frames / fps` seconds. */
  fps: number;
  /** Distance from the top of the frame to the point the effect is anchored on. */
  anchorY: number;
  /** False for one-shot timelines, which is everything here so far. */
  loop: boolean;
  /** Per-colour copies of `image`. Read through `effectImage`, not directly. */
  tints: EffectTintCache;
}

export interface VfxAtlas {
  /**
   * Tile size the sheets were generated at. Callers drawing into a world on a
   * different scale would need to rescale, which for pixel art means a matching
   * integer factor — in practice both come from the same `--tile`.
   */
  tile: number;
  /** A player materialising: charge, strike, impact, collapse. */
  summon: VfxSheet | null;
  /** The bonfire roaring when the match starts: charge, rise, impact, collapse. */
  kindle: VfxSheet | null;
}

interface EffectManifest {
  file: string;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  fps: number;
  anchorY: number;
  loop?: boolean;
}

interface VfxManifest {
  tile: number;
  effects: { summon?: EffectManifest; kindle?: EffectManifest };
}

const ROOT = '/vfx';

export async function loadVfx(): Promise<VfxAtlas | null> {
  try {
    const manifest = await loadJson<VfxManifest>(`${ROOT}/manifest.json`);
    const [summon, kindle] = await Promise.all([
      manifest.effects.summon ? loadEffect(manifest.effects.summon) : null,
      manifest.effects.kindle ? loadEffect(manifest.effects.kindle) : null,
    ]);
    return { tile: manifest.tile, summon, kindle };
  } catch (err) {
    console.warn('[vfx] no effect atlas, effects disabled:', err);
    return null;
  }
}

async function loadEffect(manifest: EffectManifest): Promise<VfxSheet> {
  const image = await loadImage(`${ROOT}/${manifest.file}`);
  return {
    image,
    frameWidth: manifest.frameWidth,
    frameHeight: manifest.frameHeight,
    frames: manifest.frames,
    fps: manifest.fps,
    anchorY: manifest.anchorY,
    loop: manifest.loop ?? false,
    tints: new EffectTintCache(image),
  };
}

/**
 * The sheet's bitmap in `color`, or the greyscale original when none is given.
 *
 * Cached per colour, so an effect fired every frame for a whole party costs one
 * canvas per player and nothing after that.
 */
export function effectImage(
  sheet: VfxSheet,
  color: string | null,
): CanvasImageSource {
  return color ? sheet.tints.get(color) : sheet.image;
}

/**
 * Per-colour copies of an effect sheet.
 *
 * Deliberately NOT `sprites.TintCache`, which is a straight multiply: that is
 * right for a material — a shirt in a player's colour — and wrong for a light.
 * Multiplied alone, the white-hot core of a beam comes out as flat mid-tone
 * paint. So the neutral art is added back on top afterwards, which pulls only
 * the brightest pixels toward white and leaves the dim sheath fully coloured:
 * a hot core inside a tinted glow, which is what light actually looks like.
 */
export class EffectTintCache {
  private readonly cache = new Map<string, HTMLCanvasElement>();

  constructor(private readonly image: HTMLImageElement) {}

  get(color: string): HTMLCanvasElement {
    const cached = this.cache.get(color);
    if (cached) return cached;

    const image = this.image;
    const { width, height } = sourceSize(image);
    const { canvas, ctx } = createSurface(width, height, 'vfx/tint');

    ctx.drawImage(image, 0, 0);
    ctx.globalCompositeOperation = 'multiply';
    ctx.fillStyle = color;
    ctx.fillRect(0, 0, width, height);
    // The core, put back. Additive, so it lands in proportion to how bright the
    // pixel already was and the outer steps keep their hue.
    ctx.globalCompositeOperation = 'lighter';
    ctx.globalAlpha = CORE_HEAT;
    ctx.drawImage(image, 0, 0);
    // Both passes above painted over transparent pixels; this restores the
    // sheet's own alpha, including its quantized edge steps, exactly.
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = 'destination-in';
    ctx.drawImage(image, 0, 0);
    ctx.globalCompositeOperation = 'source-over';

    this.cache.set(color, canvas);
    return canvas;
  }

  clear(): void {
    this.cache.clear();
  }
}

/**
 * How much of the neutral art is added back over the tint. Higher washes the
 * colour out of the beam entirely; at 0 the strike is flat paint with no heat
 * in it.
 */
const CORE_HEAT = 0.22;

/** Frame index for a one-shot sheet, held on the last frame once it is over. */
export function effectFrame(sheet: VfxSheet, elapsed: number): number {
  const index = Math.floor(elapsed * sheet.fps);
  if (sheet.loop) return ((index % sheet.frames) + sheet.frames) % sheet.frames;
  return Math.max(0, Math.min(sheet.frames - 1, index));
}
