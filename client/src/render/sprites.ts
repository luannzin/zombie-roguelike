/**
 * Sprite sheet loading + per-colour tinting.
 *
 * There is ONE character asset. Player colours are applied as a multiply tint
 * over the base sheet and cached per colour, so adding a colour costs nothing
 * and no per-colour art is ever generated.
 *
 * Sheet layout (produced by server/tools/process_sprites.py):
 *   rows = down, left, right, up   cols = 3 animation frames
 */

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

/** Matches the canonical processed frame: 1 x 1.5 tiles at TILE_SIZE 16. */
const FALLBACK_W = 16;
const FALLBACK_H = 24;

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

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`failed to load ${src}`));
    img.src = src;
  });
}

/** Minimal procedural stand-in so the game still runs without processed assets. */
function fallbackSheet(): SpriteSheet {
  const w = FALLBACK_W;
  const h = FALLBACK_H;
  const canvas = document.createElement('canvas');
  canvas.width = w * 3;
  canvas.height = h * 4;
  const ctx = canvas.getContext('2d')!;
  const rows: Facing[] = ['down', 'left', 'right', 'up'];
  rows.forEach((facing, row) => {
    for (let col = 0; col < 3; col++) {
      const ox = col * w;
      const oy = row * h;
      const bob = col === 1 ? 0 : 1;
      ctx.fillStyle = '#e8e8f0';
      ctx.fillRect(ox + 4, oy + 9 + bob, 8, 8); // torso
      ctx.fillStyle = '#eecaac';
      ctx.fillRect(ox + 4, oy + 2 + bob, 8, 7); // head
      ctx.fillStyle = '#606476';
      ctx.fillRect(ox + 5, oy + 17 + bob, 2, 6); // legs
      ctx.fillRect(ox + 9, oy + 17 + bob, 2, 6);
      ctx.fillStyle = '#24222e';
      if (facing === 'down') {
        ctx.fillRect(ox + 6, oy + 5 + bob, 1, 2);
        ctx.fillRect(ox + 9, oy + 5 + bob, 1, 2);
      } else if (facing === 'left') {
        ctx.fillRect(ox + 5, oy + 5 + bob, 1, 2);
      } else if (facing === 'right') {
        ctx.fillRect(ox + 10, oy + 5 + bob, 1, 2);
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

export class TintCache {
  private cache = new Map<string, HTMLCanvasElement>();

  constructor(private readonly sheet: SpriteSheet) {}

  get(color: string): HTMLCanvasElement {
    const cached = this.cache.get(color);
    if (cached) return cached;

    const { image } = this.sheet;
    const width = image instanceof HTMLImageElement ? image.naturalWidth : image.width;
    const height = image instanceof HTMLImageElement ? image.naturalHeight : image.height;

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d')!;
    ctx.imageSmoothingEnabled = false;

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
