/**
 * Sprite sheet loading + per-colour tinting.
 *
 * Sheets are keyed by asset name ("player", "zombie", …) in a `SpriteBook`.
 * Which enemy sheets to load is not hardcoded here: the server names them in
 * `welcome.config.enemyTypes[*].sprite`, so a new creature is a server-side
 * stat block plus a processed folder, with no client change.
 *
 * Player colours are a multiply tint over the base sheet, cached per colour, so
 * adding a colour costs nothing and no per-colour art is ever generated. It
 * lands on the DYEABLE part of the sheet only — the pixels the art left pure
 * grey — so a player is somebody in a coloured coat rather than somebody made
 * of one colour; see `TintCache`. Equipped gear is the same contract (the
 * backpack). Enemy overlays (hats, clothes) are drawn untinted — their art
 * carries its own palette.
 *
 * Sheet layout (produced by server/tools/process_sprites.py):
 *   rows = down, left, right, up
 *   walk sheets: 3 columns; death sheets (`*-death`): a one-shot timeline
 *   whose last column is the prone rest. Never rotate a walk frame to fake
 *   a corpse — 16px through a canvas transform is mush.
 */

import { createSurface, sourceSize } from '../lib/canvas';
import { loadImage } from '../lib/image';

export type Facing = 'down' | 'left' | 'right' | 'up';

export interface SpriteSheet {
  image: HTMLImageElement | HTMLCanvasElement;
  frameWidth: number;
  frameHeight: number;
  rows: Record<string, number>;
  frames: number;
  idleFrame: number;
  walkFrameOrder: number[];
  fps: number;
  /** False on one-shot timelines (death). Walk sheets loop. */
  loop: boolean;
}

interface Manifest {
  sheet: string;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  rows: Record<string, number>;
  idleFrame: number;
  walkFrameOrder: number[];
  fps: number;
  loop?: boolean;
}

/** Matches the canonical processed frame: 1 x 1 tile at TILE_SIZE 16. */
const FALLBACK_W = 16;
const FALLBACK_H = 16;

export async function loadCharacterSheet(name: string): Promise<SpriteSheet | null> {
  try {
    const manifest = (await fetch(`/${name}/manifest.json`).then((r) => {
      if (!r.ok) throw new Error(`manifest ${r.status}`);
      return r.json();
    })) as Manifest;

    const image = await loadImage(`/${name}/${manifest.sheet}`);
    return {
      image,
      frameWidth: manifest.frameWidth,
      frameHeight: manifest.frameHeight,
      rows: manifest.rows,
      frames: manifest.frames,
      idleFrame: manifest.idleFrame,
      walkFrameOrder: manifest.walkFrameOrder,
      fps: manifest.fps,
      loop: manifest.loop !== false,
    };
  } catch (err) {
    if (name.endsWith('-death')) {
      console.warn(`[sprites] no death sheet "${name}"`);
      return null;
    }
    console.warn(`[sprites] falling back to generated art for "${name}":`, err);
    return fallbackSheet();
  }
}

/** Minimal procedural stand-in so the game still runs without processed assets. */
function fallbackSheet(): SpriteSheet {
  const w = FALLBACK_W;
  const h = FALLBACK_H;
  const { canvas, ctx } = createSurface(w * 3, h * 4, 'sprites/fallback');
  const rows: Facing[] = ['down', 'left', 'right', 'up'];
  rows.forEach((facing, row) => {
    for (let col = 0; col < 3; col++) {
      const ox = col * w;
      const oy = row * h;
      const bob = col === 1 ? 0 : 1;
      ctx.fillStyle = '#e8e8f0';
      ctx.fillRect(ox + 5, oy + 6 + bob, 6, 6); // torso
      ctx.fillStyle = '#eecaac';
      ctx.fillRect(ox + 5, oy + 1 + bob, 6, 5); // head
      ctx.fillStyle = '#606476';
      ctx.fillRect(ox + 5, oy + 12 + bob, 2, 4); // legs
      ctx.fillRect(ox + 9, oy + 12 + bob, 2, 4);
      ctx.fillStyle = '#24222e';
      if (facing === 'down') {
        ctx.fillRect(ox + 6, oy + 3 + bob, 1, 1);
        ctx.fillRect(ox + 9, oy + 3 + bob, 1, 1);
      } else if (facing === 'left') {
        ctx.fillRect(ox + 5, oy + 3 + bob, 1, 1);
      } else if (facing === 'right') {
        ctx.fillRect(ox + 10, oy + 3 + bob, 1, 1);
      }
    }
  });
  return {
    image: canvas,
    frameWidth: w,
    frameHeight: h,
    rows: { down: 0, left: 1, right: 2, up: 3 },
    frames: 3,
    idleFrame: 1,
    walkFrameOrder: [0, 1, 2, 1],
    fps: 8,
    loop: true,
  };
}

/**
 * Every loaded sheet, plus its tint cache.
 *
 * Loading is idempotent and deduplicated: `load()` can be called again on every
 * `welcome` without refetching, and two entity types sharing a sprite share one
 * bitmap. A name that has not finished loading simply has no sheet yet and the
 * renderer skips it — enemies appear seconds after `welcome`, so nothing pops.
 */
export class SpriteBook {
  private readonly sheets = new Map<string, SpriteSheet>();
  private readonly tints = new Map<string, TintCache>();
  private readonly inFlight = new Map<string, Promise<void>>();

  /** Fetch any sheets not already loaded (or loading). Resolves when all are in. */
  async load(names: readonly string[]): Promise<void> {
    const pending = names.map((name) => {
      const existing = this.inFlight.get(name);
      if (existing) return existing;
      if (this.sheets.has(name)) return Promise.resolve();

      const task = loadCharacterSheet(name).then((sheet) => {
        if (!sheet) return;
        this.sheets.set(name, sheet);
        this.tints.set(name, new TintCache(sheet));
      });
      this.inFlight.set(name, task);
      return task;
    });
    await Promise.all(pending);
  }

  get(name: string): SpriteSheet | undefined {
    return this.sheets.get(name);
  }

  /** The sheet's bitmap, multiplied by `color` when one is given. */
  image(name: string, color: string | null): CanvasImageSource | undefined {
    const sheet = this.sheets.get(name);
    if (!sheet) return undefined;
    if (!color) return sheet.image;
    return this.tints.get(name)?.get(color) ?? sheet.image;
  }

  /** Drop cached tints. Sheets themselves are kept — the art does not change. */
  clearTints(): void {
    for (const cache of this.tints.values()) cache.clear();
  }
}

export class TintCache {
  private cache = new Map<string, HTMLCanvasElement>();
  private base: ImageData | null = null;

  constructor(private readonly sheet: SpriteSheet) {}

  /**
   * The sheet in `color`, and ONLY the parts of it that are supposed to be.
   *
   * IT USED TO MULTIPLY THE WHOLE BITMAP, which is the cheapest possible
   * per-player colour and also the reason every player was a monochrome
   * silhouette: the multiply hit the skin, the hair, the hat and the boots as
   * hard as it hit the coat, so "the red player" was a person made of red
   * rather than a person in a red coat. Fifteen hues of that is fifteen
   * palette swaps of one blob, and the character underneath — whose face,
   * whose hat, whose gear — was gone in all fifteen.
   *
   * WHAT MARKS THE TINTABLE PART IS THE ART ITSELF: a pixel is dyed if it is
   * EXACTLY GREY (r == g == b). Nothing else about the sheet changes and no
   * second file has to be shipped, kept in step, or fetched. That is a real
   * contract, not a coincidence — `server/tools/make_player.py` authors the
   * coat and the boots on a pure grey ramp, gives every other material a hue
   * (the outline is blue-black, the skin is warm, the leather is brown), and
   * ASSERTS both halves of it before it writes a file. A sheet that never
   * gets tinted never gets here, so the rule binds exactly the three sheets
   * that are authored under it.
   *
   * Done as one pass over the pixels rather than as canvas composites: a
   * sheet is a few thousand pixels, it happens once per colour per sheet, and
   * the alternative is three composite ops plus a mask bitmap to express one
   * `if`.
   */
  get(color: string): HTMLCanvasElement {
    const cached = this.cache.get(color);
    if (cached) return cached;

    const { image } = this.sheet;
    const { width, height } = sourceSize(image);
    const { canvas, ctx } = createSurface(width, height, 'sprites/tint');
    if (!this.base) {
      ctx.drawImage(image, 0, 0);
      this.base = ctx.getImageData(0, 0, width, height);
    }

    const [dr, dg, db] = parseColor(color);
    const src = this.base.data;
    const out = ctx.createImageData(width, height);
    const dst = out.data;
    for (let i = 0; i < src.length; i += 4) {
      const r = src[i];
      const g = src[i + 1];
      const b = src[i + 2];
      const dye = r === g && g === b;
      dst[i] = dye ? (r * dr) / 255 : r;
      dst[i + 1] = dye ? (g * dg) / 255 : g;
      dst[i + 2] = dye ? (b * db) / 255 : b;
      dst[i + 3] = src[i + 3];
    }
    ctx.putImageData(out, 0, 0);

    this.cache.set(color, canvas);
    return canvas;
  }

  /** Drop cached tints — colours are per-room, so this runs on teardown. */
  clear(): void {
    this.cache.clear();
  }
}

/** `#rgb` / `#rrggbb` to three bytes. The palette only ever hands us hex. */
export function parseColor(color: string): [number, number, number] {
  const hex = color.trim().replace('#', '');
  const full = hex.length === 3 ? hex.split('').map((c) => c + c).join('') : hex;
  const value = Number.parseInt(full, 16);
  if (full.length !== 6 || Number.isNaN(value)) return [255, 255, 255];
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

/**
 * The row to draw: the HOLDING pose when the sheet has one and the body is
 * carrying something, the plain walk row otherwise.
 *
 * A sheet without the block — every creature, and the player's own gear
 * overlays — simply has no `hold-*` key and keeps the row it always had,
 * which is what lets the second pose be appended to one sheet without a flag
 * anywhere else (`server/tools/process_sprites.py`).
 */
export function poseRow(sheet: SpriteSheet, facing: Facing, holding: boolean): number {
  if (holding) {
    const held = sheet.rows[`hold-${facing}`];
    if (held !== undefined) return held;
  }
  return sheet.rows[facing] ?? 0;
}

export function facingFromAim(ax: number, ay: number): Facing {
  if (Math.abs(ax) >= Math.abs(ay)) return ax >= 0 ? 'right' : 'left';
  return ay >= 0 ? 'down' : 'up';
}

/** Walk cycle column. Death sheets use `timelineFrame`. */
export function frameIndex(sheet: SpriteSheet, animTime: number, moving: boolean): number {
  if (!moving) return sheet.idleFrame;
  const order = sheet.walkFrameOrder;
  return order[Math.floor(animTime * sheet.fps) % order.length];
}

/** One-shot timeline column. Holds the last frame. */
export function timelineFrame(sheet: SpriteSheet, age: number): number {
  if (sheet.frames <= 1) return 0;
  return Math.min(sheet.frames - 1, Math.max(0, Math.floor(age * sheet.fps)));
}
