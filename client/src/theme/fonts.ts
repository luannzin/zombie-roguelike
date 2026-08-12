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

const FALLBACK = "ui-monospace, Menlo, Consolas, monospace";

/** The resolved `--font-hud` family list. */
export function hudFamily(): string {
  if (cached === null) {
    cached = getComputedStyle(document.documentElement).getPropertyValue('--font-hud').trim();
    if (!cached) cached = FALLBACK;
  }
  return cached;
}

/** A canvas `ctx.font` shorthand at `sizePx`, e.g. `bold 12px "Departure Mono", …`. */
export function hudFont(sizePx: number, weight?: 'bold'): string {
  const prefix = weight ? `${weight} ` : '';
  return `${prefix}${Math.round(sizePx)}px ${hudFamily()}`;
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
