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

/** A colour as raw `[r, g, b]` bytes. */
export type Channels = [number, number, number];

export interface Palette {
  surface: string;
  panelBorder: string;
  panelInset: string;
  ink: string;
  inkMuted: string;
  inkAccent: string;

  tiles: {
    floor: string[];
    floorSpeck: string;
    wallBody: string;
    wallTop: string;
    wallEdge: string;
    tree: string;
    treeTop: string;
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
    rewardText: string;
    goldText: string;
    goldParticles: string[];
    goldCore: string;
    slash: string;
    slashBlocked: string;
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
  minimap: { localRing: string; enemy: string; fog: string; unseen: string };

  /**
   * The hunt diamond's three fill stops, as `[r, g, b]`: the layer mixes
   * between them on the awareness meter and picks its own alpha, so a colour
   * string would be the wrong shape. `mark` is the bang inside the lozenge.
   */
  enemyView: { notice: Channels; alert: Channels; hunt: Channels; mark: string };

  /**
   * Lighting tones as `[r, g, b]`. The darkness layer writes raw ImageData
   * bytes, so it needs channels, not a CSS colour string.
   */
  night: { shadow: Channels; lantern: Channels };

  /**
   * Lights the MAP owns out in the forest. Bare channels: the layer computes
   * alpha from its own flicker. `beacon` is reserved for the extraction point.
   */
  scene: { lamp: Channels; ember: Channels; beacon: Channels };

  /** The lobby campfire — the only light in that scene. */
  fire: {
    stone: string;
    log: string;
    logLit: string;
    outer: string;
    mid: string;
    core: string;
    embers: string[];
    /** Bare channels: the glow's alpha comes from the flicker, not the token. */
    glow: Channels;
  };

  /** The motes falling around a player materialising into a lobby seat. The
   * column itself is a greyscale sheet tinted with the player's own colour. */
  summon: { spark: string; core: string };

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
  /** Read a bare `R G B` token as bytes. Magenta if the token is missing. */
  const rgb = (name: string): Channels => {
    const parts = v(name).split(/[\s,]+/).map(Number);
    if (parts.length < 3 || parts.some(Number.isNaN)) return [255, 0, 255];
    return [parts[0], parts[1], parts[2]];
  };

  return {
    surface: v('--surface'),
    panelBorder: v('--panel-border'),
    panelInset: v('--panel-inset'),
    ink: v('--ink'),
    inkMuted: v('--ink-muted'),
    inkAccent: v('--ink-accent'),

    tiles: {
      floor: [v('--tile-floor-a'), v('--tile-floor-b'), v('--tile-floor-c')],
      floorSpeck: v('--tile-floor-speck'),
      wallBody: v('--tile-wall-body'),
      wallTop: v('--tile-wall-top'),
      wallEdge: v('--tile-wall-edge'),
      tree: v('--tile-tree'),
      treeTop: v('--tile-tree-top'),
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
      rewardText: v('--fx-reward-text'),
      goldText: v('--fx-gold-text'),
      goldParticles: [v('--fx-gold-a'), v('--fx-gold-b'), v('--fx-gold-c'), v('--fx-gold-d')],
      goldCore: v('--fx-gold-core'),
      slash: v('--fx-slash'),
      slashBlocked: v('--fx-slash-blocked'),
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
    minimap: {
      localRing: v('--minimap-local-ring'),
      enemy: v('--minimap-enemy'),
      fog: v('--minimap-fog'),
      unseen: v('--minimap-unseen'),
    },

    enemyView: {
      notice: rgb('--enemy-view-notice'),
      alert: rgb('--enemy-view-alert'),
      hunt: rgb('--enemy-view-hunt'),
      mark: v('--enemy-alert-mark'),
    },

    night: { shadow: rgb('--night-shadow'), lantern: rgb('--night-lantern') },

    scene: {
      lamp: rgb('--scene-lamp'),
      ember: rgb('--scene-ember'),
      beacon: rgb('--scene-beacon'),
    },

    fire: {
      stone: v('--fire-stone'),
      log: v('--fire-log'),
      logLit: v('--fire-log-lit'),
      outer: v('--fire-outer'),
      mid: v('--fire-mid'),
      core: v('--fire-core'),
      embers: [v('--fire-ember-a'), v('--fire-ember-b'), v('--fire-ember-c')],
      glow: rgb('--fire-glow'),
    },

    summon: {
      spark: v('--summon-spark'),
      core: v('--summon-core'),
    },

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
