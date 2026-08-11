/**
 * Canvas access to the design tokens.
 *
 * `src/styles/index.css` is the single source of truth. This module reads those
 * custom properties off `:root` once, caches the result, and hands plain colour
 * strings to the canvas — which cannot consume `var()` itself.
 *
 * Resolution is LAZY on purpose. In dev, Vite injects the stylesheet as a
 * module side effect, so reading at import time can race the CSS and yield
 * empty strings. First read happens during the first frame instead, long after
 * the styles are in.
 */

/**
 * Used only if a variable is missing (a token was renamed and a call site
 * wasn't). Prevents `fillStyle = ''` silently painting the previous colour.
 */
const FALLBACK = '#ff00ff';

let cache: Palette | null = null;

export interface Palette {
  surface: string;
  panelBorder: string;
  ink: string;
  inkMuted: string;
  inkAccent: string;

  tiles: {
    floor: string[];
    floorSpeck: string;
    wallBody: string;
    wallTop: string;
    wallEdge: string;
  };

  effects: {
    hitParticles: string[];
    missParticles: string[];
    dust: string[];
    dustSmear: string;
    hitCore: string;
    missCore: string;
    tracerCore: string;
    muzzleFlash: string;
    damageText: string;
    textShadow: string;
    fallbackShot: string;
  };

  entity: {
    shadow: string;
    barBackdrop: string;
    aimLocal: string;
    aimRemote: string;
    labelShadow: string;
  };

  hp: { high: string; mid: string; low: string };
  progress: { xp: string; neutral: string };
  minimap: { localRing: string };

  /** Bare `R G B` channels — the vignette computes alpha per stop. */
  danger: {
    inner: string;
    mid: string;
    outer: string;
    wash: string;
    edge: string;
  };
}

function resolve(): Palette {
  const style = getComputedStyle(document.documentElement);
  const v = (name: string): string => style.getPropertyValue(name).trim() || FALLBACK;

  return {
    surface: v('--surface'),
    panelBorder: v('--panel-border'),
    ink: v('--ink'),
    inkMuted: v('--ink-muted'),
    inkAccent: v('--ink-accent'),

    tiles: {
      floor: [v('--tile-floor-a'), v('--tile-floor-b'), v('--tile-floor-c')],
      floorSpeck: v('--tile-floor-speck'),
      wallBody: v('--tile-wall-body'),
      wallTop: v('--tile-wall-top'),
      wallEdge: v('--tile-wall-edge'),
    },

    effects: {
      hitParticles: [v('--fx-hit-a'), v('--fx-hit-b'), v('--fx-hit-c'), v('--fx-hit-d')],
      missParticles: [v('--fx-miss-a'), v('--fx-miss-b'), v('--fx-miss-c')],
      dust: [
        v('--fx-dust-a'),
        v('--fx-dust-b'),
        v('--fx-dust-c'),
        v('--fx-dust-d'),
        v('--fx-dust-e'),
      ],
      dustSmear: v('--fx-dust-smear'),
      hitCore: v('--fx-hit-core'),
      missCore: v('--fx-miss-core'),
      tracerCore: v('--fx-tracer-core'),
      muzzleFlash: v('--fx-muzzle'),
      damageText: v('--fx-damage-text'),
      textShadow: v('--fx-text-shadow'),
      fallbackShot: v('--fx-shot-fallback'),
    },

    entity: {
      shadow: v('--entity-shadow'),
      barBackdrop: v('--entity-bar-backdrop'),
      aimLocal: v('--entity-aim-local'),
      aimRemote: v('--entity-aim-remote'),
      labelShadow: v('--entity-label-shadow'),
    },

    hp: { high: v('--hp-high'), mid: v('--hp-mid'), low: v('--hp-low') },
    progress: { xp: v('--xp'), neutral: v('--neutral') },
    minimap: { localRing: v('--minimap-local-ring') },

    danger: {
      inner: v('--danger-inner'),
      mid: v('--danger-mid'),
      outer: v('--danger-outer'),
      wash: v('--danger-wash'),
      edge: v('--danger-edge'),
    },
  };
}

/** Cached token values. Hoist out of per-tile / per-particle loops. */
export function palette(): Palette {
  if (!cache) cache = resolve();
  return cache;
}

// Editing index.css hot-replaces the stylesheet but not this cache, which
// would leave the canvas on the old colours until a reload.
if (import.meta.hot) {
  import.meta.hot.on('vite:afterUpdate', () => {
    cache = null;
  });
}

// --- derived helpers --------------------------------------------------------

export type HpLevel = 'high' | 'mid' | 'low';

/** Ratio thresholds for HP colour. Shared by the canvas bars and the DOM HUD. */
export const HP_THRESHOLDS = { high: 0.5, mid: 0.25 } as const;

export function hpLevel(ratio: number): HpLevel {
  if (ratio > HP_THRESHOLDS.high) return 'high';
  if (ratio > HP_THRESHOLDS.mid) return 'mid';
  return 'low';
}

export function hpColor(ratio: number): string {
  return palette().hp[hpLevel(ratio)];
}

/**
 * Deterministic floor variation. Shared so the minimap's dithering lines up
 * with the main view instead of being a second, subtly different pattern.
 */
export function floorColor(tx: number, ty: number): string {
  const floor = palette().tiles.floor;
  return floor[(tx * 7 + ty * 13) % floor.length];
}

/** Sparse floor detail marks — same cadence in both views. */
export function hasFloorSpeck(tx: number, ty: number): boolean {
  return (tx + ty) % 9 === 0;
}
