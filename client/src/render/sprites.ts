/**
 * Sprite sheet loading + per-colour tinting.
 *
 * Sheets are keyed by asset name ("player", "zombie", …) in a `SpriteBook`.
 * Which enemy sheets to load is not hardcoded here: the server names them in
 * `welcome.config.enemyTypes[*].sprite`, so a new creature is a server-side
 * stat block plus a processed folder, with no client change.
 *
 * Player colours are a multiply tint over the base sheet, cached per colour, so
 * adding a colour costs nothing and no per-colour art is ever generated.
 * Equipped gear (the backpack) is the same contract: a greyscale overlay
 * multiplied by the wearer's colour. Enemies are drawn untinted — their art
 * carries its own palette.
 *
 * Sheet layout (produced by server/tools/process_sprites.py):
 *   rows = down, left, right, up   cols = 3 animation frames
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
}

/** Matches the canonical processed frame: 1 x 1 tile at TILE_SIZE 16. */
const FALLBACK_W = 16;
const FALLBACK_H = 16;

export async function loadCharacterSheet(name: string): Promise<SpriteSheet> {
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
    };
  } catch (err) {
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

  constructor(private readonly sheet: SpriteSheet) {}

  get(color: string): HTMLCanvasElement {
    const cached = this.cache.get(color);
    if (cached) return cached;

    const { image } = this.sheet;
    const { width, height } = sourceSize(image);
    const { canvas, ctx } = createSurface(width, height, 'sprites/tint');

    ctx.drawImage(image, 0, 0);
    ctx.globalCompositeOperation = 'multiply';
    ctx.fillStyle = color;
    ctx.fillRect(0, 0, width, height);
    // Restore the original alpha mask (multiply also painted transparent pixels).
    ctx.globalCompositeOperation = 'destination-in';
    ctx.drawImage(image, 0, 0);
    ctx.globalCompositeOperation = 'source-over';

    this.cache.set(color, canvas);
    return canvas;
  }

  /** Drop cached tints — colours are per-room, so this runs on teardown. */
  clear(): void {
    this.cache.clear();
  }
}

export function facingFromAim(ax: number, ay: number): Facing {
  if (Math.abs(ax) >= Math.abs(ay)) return ax >= 0 ? 'right' : 'left';
  return ay >= 0 ? 'down' : 'up';
}

export function frameIndex(sheet: SpriteSheet, animTime: number, moving: boolean): number {
  if (!moving) return sheet.idleFrame;
  const order = sheet.walkFrameOrder;
  return order[Math.floor(animTime * sheet.fps) % order.length];
}
