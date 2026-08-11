/**
 * Canvas 2D plumbing.
 *
 * Every surface in this game is pixel art, so smoothing is disabled everywhere
 * and a missing context is always fatal. Both rules live here instead of being
 * repeated at each `getContext` call site.
 */

export function get2d(
  canvas: HTMLCanvasElement,
  label: string,
  options?: CanvasRenderingContext2DSettings,
): CanvasRenderingContext2D {
  const ctx = canvas.getContext('2d', options);
  if (!ctx) throw new Error(`${label}: 2d context unavailable`);
  ctx.imageSmoothingEnabled = false;
  return ctx;
}

export interface OffscreenSurface {
  canvas: HTMLCanvasElement;
  ctx: CanvasRenderingContext2D;
}

/** Detached canvas + context, sized in device pixels. Used for every cache. */
export function createSurface(width: number, height: number, label: string): OffscreenSurface {
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.floor(width));
  canvas.height = Math.max(1, Math.floor(height));
  return { canvas, ctx: get2d(canvas, label) };
}

/** Intrinsic pixel size of anything drawable, image or canvas. */
export function sourceSize(source: CanvasImageSource & { width?: number; height?: number }): {
  width: number;
  height: number;
} {
  if (source instanceof HTMLImageElement) {
    return { width: source.naturalWidth, height: source.naturalHeight };
  }
  return { width: Number(source.width) || 0, height: Number(source.height) || 0 };
}
