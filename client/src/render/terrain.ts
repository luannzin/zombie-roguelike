/**
 * Terrain atlas: the forest's ground texture and its props.
 *
 * Produced by server/tools/make_textures.py and served from
 * /terrain/ (assets/processed is Vite's publicDir).
 *
 * Three kinds of asset, because the world contains three kinds of thing:
 *
 *   GROUNDS are square and tile. Each is a single seamless image cut into a
 *   `cols x rows` grid; a tile picks its cell with `(tx % cols, ty % rows)`.
 *   That is not a random variant lookup — the cells are neighbouring windows
 *   into one continuous texture, so they are guaranteed to line up and the
 *   floor has no grid seams. There are FOUR of them and a map mixes them off
 *   its own material field; `blend` is the set of alpha stencils that dissolve
 *   one into the next instead of butting them together on a grid line.
 *
 *   PROPS (rock, tree, deadtree, stump, grass, bush, fern) are not square.
 *   They are alpha silhouettes that sit ON TOP of the ground, bottom-anchored
 *   and centred on their tile, the same way process_sprites.py anchors a
 *   character. A tree is taller than a tile and overhangs the tile above it by
 *   `canopyHeight` px, and a fern is drawn in FRONT of characters rather than
 *   behind them.
 *
 *   DECALS (patch, branch, leaves) lie FLAT. They have no silhouette; the
 *   terrain layer bakes them into the ground canvas, so they cost nothing per
 *   frame and can never occlude a body.
 *
 * Loading is best-effort: a missing atlas resolves to `null` and the terrain
 * layer falls back to flat colours, so the game still runs with no assets
 * built.
 */

import { loadImage, loadJson } from '../lib/image';

export interface PropSheet {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  /**
   * Pixels of this prop that stick out above its own tile. Only trees have it;
   * that strip is redrawn after entities so a player north of a tree walks
   * under the foliage instead of on top of it.
   */
  canopyHeight: number;
  /**
   * Frames per second when the frames are an ANIMATION rather than variants.
   * Zero for every prop except the campfire — a rock's five frames are five
   * rocks, and playing them would make the boulders twitch.
   */
  fps: number;
}

/** One soil: a seamless atlas cut into a `cols x rows` grid of tiles. */
export interface GroundSheet {
  name: string;
  image: HTMLImageElement;
  tile: number;
  cols: number;
  rows: number;
}

/** A flat sheet baked into the ground canvas. No anchor, no depth. */
export interface DecalSheet {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
}

export interface TerrainAtlas {
  /**
   * The soils, in manifest order — that order IS the material index the
   * client's field produces, so it must not be sorted or filtered.
   */
  grounds: GroundSheet[];
  /**
   * Alpha stencils with ASCENDING coverage. Index by how far a tile has
   * crossed a material boundary and draw the neighbouring soil through it;
   * see `layers/terrain.ts`.
   */
  blend: DecalSheet;
  rock: PropSheet;
  tree: PropSheet;
  /** Bare trunks for a blighted TREE tile. Same frame and anchor as `tree`. */
  deadtree: PropSheet;
  stump: PropSheet;
  grass: PropSheet;
  /** Taller than grass and drawn with it, so a body passes IN FRONT of it. */
  bush: PropSheet;
  fern: PropSheet;
  /** Flat scatter baked into the ground: stains, twigs, leaf litter. */
  patch: DecalSheet;
  branch: DecalSheet;
  leaves: DecalSheet;
  /**
   * The lobby's campfire. Optional because it arrived after the first atlas
   * shipped: a client running against older `assets/processed/` still gets a
   * forest, just no fire in it.
   */
  campfire: PropSheet | null;
}

interface PropManifest {
  file: string;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  canopyHeight?: number;
  fps?: number;
}

type PropName = 'rock' | 'tree' | 'deadtree' | 'stump' | 'grass' | 'bush' | 'fern';
type DecalName = 'patch' | 'branch' | 'leaves';

interface TerrainManifest {
  tile: number;
  grounds: { name: string; file: string; tile: number; cols: number; rows: number }[];
  blend: PropManifest;
  props: Record<PropName, PropManifest> & { campfire?: PropManifest };
  decals: Record<DecalName, PropManifest>;
}

const ROOT = '/terrain';

/**
 * One atlas per session, shared by every `TerrainLayer`.
 *
 * The lobby and the arena each own a layer and both draw the same forest. Two
 * separate loads would mean the arena spends its first frames with no atlas,
 * painting flat colours over ground the player is already looking at — a flash
 * of a different-looking world at the exact moment the two scenes hand over.
 * The per-map bake caches stay per-layer; only the images are shared.
 */
let atlasPromise: Promise<TerrainAtlas | null> | null = null;

export function loadTerrain(): Promise<TerrainAtlas | null> {
  atlasPromise ??= fetchTerrain();
  return atlasPromise;
}

async function fetchTerrain(): Promise<TerrainAtlas | null> {
  try {
    const manifest = await loadJson<TerrainManifest>(`${ROOT}/manifest.json`);
    const prop = (name: PropName) => loadProp(manifest.props[name]);
    const decal = (name: DecalName) => loadDecal(manifest.decals[name]);
    const [
      grounds, blend, rock, tree, deadtree, stump, grass, bush, fern,
      patch, branch, leaves, campfire,
    ] = await Promise.all([
      Promise.all(manifest.grounds.map(loadGround)),
      loadDecal(manifest.blend),
      prop('rock'),
      prop('tree'),
      prop('deadtree'),
      prop('stump'),
      prop('grass'),
      prop('bush'),
      prop('fern'),
      decal('patch'),
      decal('branch'),
      decal('leaves'),
      manifest.props.campfire ? loadProp(manifest.props.campfire) : Promise.resolve(null),
    ]);
    return {
      grounds, blend, rock, tree, deadtree, stump, grass, bush, fern,
      patch, branch, leaves, campfire,
    };
  } catch (err) {
    console.warn('[terrain] falling back to flat tiles:', err);
    // Not memoized as a permanent failure: a later scene should get another go.
    atlasPromise = null;
    return null;
  }
}

async function loadGround(
  manifest: TerrainManifest['grounds'][number],
): Promise<GroundSheet> {
  return {
    name: manifest.name,
    image: await loadImage(`${ROOT}/${manifest.file}`),
    tile: manifest.tile,
    cols: manifest.cols,
    rows: manifest.rows,
  };
}

async function loadDecal(manifest: PropManifest): Promise<DecalSheet> {
  return {
    image: await loadImage(`${ROOT}/${manifest.file}`),
    frameWidth: manifest.frameWidth,
    frameHeight: manifest.frameHeight,
    frames: manifest.frames,
  };
}

async function loadProp(manifest: PropManifest): Promise<PropSheet> {
  return {
    image: await loadImage(`${ROOT}/${manifest.file}`),
    frameWidth: manifest.frameWidth,
    frameHeight: manifest.frameHeight,
    frames: manifest.frames,
    canopyHeight: manifest.canopyHeight ?? 0,
    fps: manifest.fps ?? 0,
  };
}

/**
 * Deterministic 0..1 from a tile coordinate and the map seed.
 *
 * Every decoration decision — which rock variant, whether this tile has grass,
 * where the tuft sits inside the tile — comes from this. That is why the map
 * payload carries a seed and not a decoration layer: the server sends 4 bytes
 * and both sides agree on a whole forest's worth of detail.
 */
export function tileHash(tx: number, ty: number, seed: number, salt = 0): number {
  let h = (Math.imul(tx, 374761393) + Math.imul(ty, 668265263) + Math.imul(seed ^ salt, 2246822519)) | 0;
  h = (h ^ (h >>> 13)) | 0;
  h = Math.imul(h, 1274126177) | 0;
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}
