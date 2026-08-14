/**
 * Asset fetching, memoized by URL.
 *
 * The cache is not a micro-optimisation, it is a correctness fix for the seam
 * between two scenes. The lobby and the arena are different objects with
 * different loaders, and both need the same terrain atlas and the same player
 * sheet — so without this, starting a run re-fetches and re-decodes everything
 * the player is already looking at. The HTTP cache makes that fast but not
 * instant, and for the frames it takes, the renderer has no atlas and paints
 * flat colours instead of textured ground. That is a visible flash of a
 * different-looking world in the middle of a transition built to be seamless.
 *
 * Sharing one `HTMLImageElement` between consumers is safe: `drawImage` does
 * not mutate its source, and every per-colour tint is built into a cache the
 * consumer owns (see `render/sprites.ts`).
 *
 * Failures are not cached. A network blip on the first attempt should not
 * poison every later one.
 */

const images = new Map<string, Promise<HTMLImageElement>>();
const documents = new Map<string, Promise<unknown>>();

/** Promise wrapper around `Image.onload`. Shared by every asset loader. */
export function loadImage(src: string): Promise<HTMLImageElement> {
  const cached = images.get(src);
  if (cached) return cached;

  const pending = new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`failed to load ${src}`));
    img.src = src;
  }).catch((err: unknown) => {
    images.delete(src);
    throw err;
  });

  images.set(src, pending);
  return pending;
}

/** Fetch JSON, failing loudly on a non-2xx instead of parsing an error page. */
export function loadJson<T>(src: string): Promise<T> {
  const cached = documents.get(src) as Promise<T> | undefined;
  if (cached) return cached;

  const pending = (async () => {
    const response = await fetch(src);
    if (!response.ok) throw new Error(`${src}: ${response.status}`);
    return (await response.json()) as T;
  })().catch((err: unknown) => {
    documents.delete(src);
    throw err;
  });

  documents.set(src, pending);
  return pending;
}

/** Drop every cached asset. Regenerating art in `assets/` is the only reason. */
export function clearAssetCache(): void {
  images.clear();
  documents.clear();
}

// The asset pipeline writes into Vite's publicDir, so a regenerated sheet
// arrives as a full reload — but a manifest edited during a dev session would
// otherwise be served from this cache until then.
if (import.meta.hot) {
  import.meta.hot.on('vite:afterUpdate', clearAssetCache);
}
