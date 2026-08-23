/**
 * THE SAWYER, drawn: an atlas of facing clips and a frame picked off the wire.
 *
 * Produced by server/tools/make_sawyer.py and served from /sawyer/.
 *
 * HE IS THE THIRD KIND OF ANIMATED THING IN THIS GAME and he had to be,
 * because neither of the other two fits:
 *
 *   a BODY (`sprites.ts`)   four facing rows by three walk frames, indexed off
 *                           velocity. It has no vocabulary for "the eleventh
 *                           frame of a chop".
 *   the MERCHANT            clips, but on a LOCAL clock — he stands on one
 *                           tile and nobody can perceive two clients
 *                           disagreeing about which frame he is on.
 *
 * The boss is clips like the merchant and authoritative like a body. The row
 * carries `s` (his state) and `t` (seconds into it), and this file turns that
 * pair into a frame. Nothing here runs a clock of its own.
 *
 * WHY THE SERVER OWNS THE PLAYHEAD. His windup IS the mechanic — the player
 * learns the fight by watching the bar go up — so the frame on screen and the
 * frame the hitbox opens on have to be the same frame. Given a local clock
 * they drift by exactly the amount of jitter on the link, and the symptom is
 * the worst one a boss can have: you dodged it, on your screen, and died.
 * `server/app/boss.py` reads its timings out of this same manifest for the
 * other half of that promise.
 *
 * FACINGS ARE PICKED THE WAY EVERY OTHER BODY'S ARE — off the aim vector,
 * with the same bias toward the side rows that `sprites.ts` uses, because a
 * body facing 44 degrees reads as facing sideways and not as facing away.
 * `sweep` is the exception and it has no facing at all: the rig turns inside
 * the clip, which is why the sheet ships once (see `make_sawyer.py`).
 */

import { loadImage, loadJson } from '../lib/image';
import type { BossRow, GameConfig } from '../net/protocol';

export type BossFacing = 'down' | 'left' | 'right' | 'up';

export interface BossClip {
  /** One image per facing, or a single `null`-keyed sheet for `sweep`. */
  images: Partial<Record<BossFacing, HTMLImageElement>>;
  /** The facing-less sheet, for clips that turn inside themselves. */
  single: HTMLImageElement | null;
  frames: number;
  fps: number;
  loop: boolean;
  /** Frame indices the art marks: `hit`, `release`, `roar`, `impact`. */
  events: Record<string, number>;
}

export interface BossAtlas {
  frameWidth: number;
  frameHeight: number;
  /** Where the frame registers. NOT 1.0 — he keeps rows under his feet. */
  anchorX: number;
  anchorY: number;
  /** His footprint and height, in TILES. Never taken off the frame. */
  footprint: { w: number; h: number };
  heightTiles: number;
  clips: Record<string, BossClip>;
  crescent: {
    image: HTMLImageElement;
    frameWidth: number;
    frameHeight: number;
    headings: number;
    frames: number;
    fps: number;
  } | null;
  burst: {
    image: HTMLImageElement;
    frameWidth: number;
    frameHeight: number;
    frames: number;
    fps: number;
  } | null;
}

interface ClipManifest {
  file?: string;
  frames: number;
  fps: number;
  loop?: boolean;
  facings?: Record<string, string> | null;
  events?: Record<string, number>;
}

interface BossManifest {
  name: string;
  frameWidth: number;
  frameHeight: number;
  anchor?: { x: number; y: number };
  footprint?: { w: number; h: number };
  height?: number;
  clips: Record<string, ClipManifest>;
  projectile?: {
    file: string;
    frameWidth: number;
    frameHeight: number;
    headings: number;
    frames: number;
    fps: number;
    burst?: {
      file: string;
      frameWidth: number;
      frameHeight: number;
      frames: number;
      fps: number;
    };
  };
}

const ROOT = '/sawyer';

let atlasPromise: Promise<BossAtlas | null> | null = null;

export function loadBoss(): Promise<BossAtlas | null> {
  atlasPromise ??= fetchBoss();
  return atlasPromise;
}

async function fetchBoss(): Promise<BossAtlas | null> {
  try {
    const manifest = await loadJson<BossManifest>(`${ROOT}/manifest.json`);
    const clips: Record<string, BossClip> = {};
    const jobs: Array<Promise<void>> = [];

    for (const [name, row] of Object.entries(manifest.clips)) {
      const clip: BossClip = {
        images: {},
        single: null,
        frames: row.frames,
        fps: row.fps,
        loop: row.loop === true,
        events: row.events ?? {},
      };
      clips[name] = clip;
      if (row.facings) {
        for (const [facing, file] of Object.entries(row.facings)) {
          jobs.push(
            loadImage(`${ROOT}/${file}`).then((img) => {
              clip.images[facing as BossFacing] = img;
            }),
          );
        }
      } else if (row.file) {
        jobs.push(
          loadImage(`${ROOT}/${row.file}`).then((img) => {
            clip.single = img;
          }),
        );
      }
    }

    let crescent: BossAtlas['crescent'] = null;
    let burst: BossAtlas['burst'] = null;
    const proj = manifest.projectile;
    if (proj) {
      jobs.push(
        loadImage(`${ROOT}/${proj.file}`).then((img) => {
          crescent = {
            image: img,
            frameWidth: proj.frameWidth,
            frameHeight: proj.frameHeight,
            headings: proj.headings,
            frames: proj.frames,
            fps: proj.fps,
          };
        }),
      );
      if (proj.burst) {
        const spec = proj.burst;
        jobs.push(
          loadImage(`${ROOT}/${spec.file}`).then((img) => {
            burst = {
              image: img,
              frameWidth: spec.frameWidth,
              frameHeight: spec.frameHeight,
              frames: spec.frames,
              fps: spec.fps,
            };
          }),
        );
      }
    }

    await Promise.all(jobs);
    return {
      frameWidth: manifest.frameWidth,
      frameHeight: manifest.frameHeight,
      anchorX: manifest.anchor?.x ?? 0.5,
      anchorY: manifest.anchor?.y ?? 1,
      footprint: manifest.footprint ?? { w: 1.6, h: 0.75 },
      heightTiles: manifest.height ?? 3.4,
      clips,
      crescent,
      burst,
    };
  } catch (err) {
    console.warn('[boss] no sawyer atlas:', err);
    atlasPromise = null;
    return null;
  }
}

/**
 * Which clip a state plays.
 *
 * `windup`, `strike` and `recover` are three states of ONE clip FOR A SWING:
 * the server splits them because the hitbox opens between them, and the art
 * does not because a swing is a swing. So the three share `m` (the move's
 * name) and the playhead runs straight through them — which is why `clipTime`
 * below uses `t` raw rather than reconstructing it. Getting that wrong
 * restarts the animation on the frame the bar lands, which is the single most
 * visible bug this file could have. `tests/boss-clock.ts` is what found it.
 *
 * THE CHARGE IS THE EXCEPTION AND IT IS AN EXCEPTION ABOUT THE ART. It is one
 * move played on three sheets — `rev` for the cord and the roar, `walk` for
 * the run, `idle` for the pull-up — because it is the only attack that is not
 * a pose. So `m` names a MOVE and not necessarily a clip, and the mapping
 * comes off `welcome.config.bossMoves` rather than being assumed. The server
 * resets his playhead on each of those phases for exactly the same reason it
 * does NOT reset it inside a swing: the clip changed.
 *
 * `config` is optional so the frame picker still works before the welcome has
 * landed, and so the swings — whose move name IS their sheet name — resolve
 * with or without it.
 */
export function clipFor(row: BossRow, config: GameConfig | null = null): string {
  switch (row.s) {
    case 'arrive':
      return 'arrive';
    case 'dead':
      return 'death';
    case 'walk':
      return 'walk';
    // THE RUN DRAWS AS A WALK, and it is the one state whose clip is not the
    // move's at all: he is crossing the yard, and the sheet for crossing
    // ground is the one every other body uses to do it.
    case 'charge':
      return 'walk';
    case 'windup':
    case 'strike':
      return moveOf(row, config)?.clip ?? row.m ?? 'chop';
    case 'recover':
      return moveOf(row, config)?.after ?? row.m ?? 'chop';
    default:
      return 'idle';
  }
}

function moveOf(row: BossRow, config: GameConfig | null) {
  return row.m ? config?.bossMoves?.[row.m] : undefined;
}

/**
 * Seconds into the clip. The row already carries it; this exists to say why.
 *
 * `t` on the wire is the CLIP'S PLAYHEAD, not the state's clock, and that is
 * a deliberate contract (see `Boss.clip_t` in `server/app/boss.py`). A move is
 * three server states — windup, strike, recover — and one animation, because
 * the hitbox opens between them and a swing does not. Reconstructing the
 * playhead here would mean holding a copy of this module's phase lengths, and
 * the version that tried restarted the clip on the exact frame the bar landed:
 * the player watched the windup, the bar came down, the sprite jumped back to
 * frame zero, and they took thirty-four damage from a boss who appeared to be
 * winding up again.
 *
 * Kept as a function rather than inlined so `bossFrame` reads the same as it
 * would if the arithmetic ever came back, and so this note has somewhere to
 * live.
 */
export function clipTime(row: BossRow, atlas: BossAtlas,
                         config: GameConfig | null = null): number {
  const clip = atlas.clips[clipFor(row, config)];
  if (!clip) return row.t;
  // Clamped for a non-looping clip: a recovery that outlasts its own animation
  // holds the last frame rather than wrapping to the first.
  return clip.loop ? row.t : Math.min(clip.frames / clip.fps, row.t);
}


/**
 * The facing row, off the aim vector.
 *
 * Biased toward the SIDE rows the same way `sprites.ts` biases a player's:
 * the side view is the one that carries the weapon, and at this size a body
 * facing 40 degrees away from the camera drawn face-on has a 41px chainsaw
 * pointing at nothing.
 */
export function bossFacing(ax: number, ay: number): BossFacing {
  if (Math.abs(ax) >= Math.abs(ay) * 0.8) return ax >= 0 ? 'right' : 'left';
  return ay >= 0 ? 'down' : 'up';
}

/** The frame to blit: which sheet, and how far along it. */
export function bossFrame(
  row: BossRow,
  atlas: BossAtlas,
  config: GameConfig | null = null,
): { image: HTMLImageElement; sx: number } | null {
  const name = clipFor(row, config);
  const clip = atlas.clips[name] ?? atlas.clips.idle;
  if (!clip) return null;
  const image = clip.single ?? clip.images[bossFacing(row.ax, row.ay)]
    ?? clip.images.down ?? null;
  if (!image) return null;
  const t = clipTime(row, atlas, config);
  const step = Math.floor(t * clip.fps);
  const index = clip.loop
    ? ((step % clip.frames) + clip.frames) % clip.frames
    : Math.min(clip.frames - 1, Math.max(0, step));
  return { image, sx: index * atlas.frameWidth };
}

/**
 * The crescent's frame: one of eight baked headings, and how far into its own
 * short loop it is.
 *
 * Baked rather than rotated for the reason `tracks.png` documents in
 * `make_textures.py`: a 40px arc of chain through a canvas rotate is grey
 * mush, and which way the teeth face is the whole read.
 */
export function crescentFrame(
  crest: { dx: number; dy: number; t: number },
  atlas: BossAtlas,
  now: number,
): { image: HTMLImageElement; sx: number; size: number } | null {
  const spec = atlas.crescent;
  if (!spec) return null;
  const angle = Math.atan2(crest.dy, crest.dx);
  const turn = (angle + Math.PI * 2) % (Math.PI * 2);
  const heading = Math.round((turn / (Math.PI * 2)) * spec.headings) % spec.headings;
  const step = Math.floor(now * spec.fps) % spec.frames;
  return {
    image: spec.image,
    sx: (heading * spec.frames + step) * spec.frameWidth,
    size: spec.frameWidth,
  };
}
