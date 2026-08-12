/**
 * Canvas access to the HUD type stack.
 *
 * Same contract as `palette.ts`: `styles/index.css` owns the value, this reads
 * it lazily off `:root` and caches it. Canvas `ctx.font` needs a plain CSS
 * shorthand string, not a `var()`.
 *
 * The font may still be loading on the first frames — `ctx.font` silently keeps
 * its previous value if the family is unavailable. That self-heals because the
 * canvas repaints every frame, and `whenFontsReady()` lets callers avoid the
 * flash entirely.
 */

let cached: string | null = null;

const FALLBACK = 'ui-monospace, Menlo, Consolas, monospace';

/**
 * Departure Mono's design grid.
 *
 * The font has `unitsPerEm: 550` and draws every feature on a 50-unit grid
 * (cap height 400, x-height 300, ascender 550, descender -150). 550 / 50 = 11,
 * so one design pixel is exactly `fontSize / 11` screen pixels.
 *
 * At 11px (or 22px, 33px…) that lands on whole pixels and the glyphs are
 * crisp. At 10px or 12px it lands on 0.91 / 1.09 pixels, the rasterizer
 * antialiases stems unevenly, and the text visibly shimmers. Every HUD size —
 * DOM and canvas — must therefore be a multiple of this number.
 */
export const HUD_GRID = 11;

/** Nearest usable size on the font's pixel grid, never below one grid step. */
export function snapHudSize(px: number): number {
  return Math.max(HUD_GRID, Math.round(px / HUD_GRID) * HUD_GRID);
}

/** The resolved `--font-hud` family list. */
export function hudFamily(): string {
  if (cached === null) {
    cached = getComputedStyle(document.documentElement).getPropertyValue('--font-hud').trim();
    if (!cached) cached = FALLBACK;
  }
  return cached;
}

/**
 * A canvas `ctx.font` shorthand, snapped to the font's pixel grid so callers
 * cannot accidentally request a blurry size.
 *
 * Deliberately offers no weight argument: only Departure Mono Regular (400) is
 * loaded, so any bolder request would be synthesized by the rasterizer and
 * thicken stems unevenly. Emphasis comes from colour and size instead.
 */
export function hudFont(sizePx: number): string {
  return `${snapHudSize(sizePx)}px ${hudFamily()}`;
}

/**
 * Resolves once the webfont is usable. Awaited during startup so the first
 * rendered frame already has the real face.
 */
export function whenFontsReady(): Promise<unknown> {
  return document.fonts?.ready ?? Promise.resolve();
}

if (import.meta.hot) {
  import.meta.hot.on('vite:afterUpdate', () => {
    cached = null;
  });
}
