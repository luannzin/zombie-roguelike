/**
 * The merchant: one character, four clips, and a clock that picks between them.
 *
 * Produced by server/tools/make_merchant.py and served from /merchant/.
 *
 * HE IS NOT AN ENTITY, and that is the whole reason this file exists rather
 * than a sheet in `sprites.ts`. Every other character in the game is a body the
 * server is simulating — it has a position that changes, a facing driven by
 * aim, and a walk cycle indexed off velocity. He has none of that: he stands on
 * one tile of one map and the only thing that varies is what he happens to be
 * doing while you look at him. So he gets a CLIP PLAYER instead of a walk
 * frame, and the clip player is the character.
 *
 * ONE LOOPING CLIP AND THREE INTERRUPTIONS. `idle` runs forever; every few
 * seconds one of `randomClips` plays through once and hands back to it. The
 * gap is rolled per cycle out of `randomGap`, so two clients watching the same
 * merchant do not see the same performance — which is fine and is the point.
 * Nothing about him is on the wire: he is scenery that moves, the server has
 * never had an opinion about which frame he is on, and a party standing in
 * front of him are all looking at the same person doing slightly different
 * things. Synchronising that would cost a message per animation to buy an
 * agreement nobody can perceive.
 *
 * The manifest drives all of it — clip names, frame counts, fps, which clips
 * are the random ones, and how long the gaps are — so adding a fourth flourish
 * is a recipe in `make_merchant.py` and no change here.
 */

import { loadImage, loadJson } from '../lib/image';

export interface MerchantClip {
  image: HTMLImageElement;
  frames: number;
  fps: number;
  loop: boolean;
}

export interface MerchantAtlas {
  frameWidth: number;
  frameHeight: number;
  /** Where the frame registers: 0.5/1.0 is bottom-centre, like every prop. */
  anchorX: number;
  anchorY: number;
  clips: Record<string, MerchantClip>;
  /** Which clips may interrupt the idle. Names into `clips`. */
  randomClips: string[];
  /** Seconds between interruptions, as `[min, max]`. */
  randomGap: [number, number];
}

interface ClipManifest {
  file: string;
  frames: number;
  fps: number;
  loop?: boolean;
}

interface MerchantManifest {
  name: string;
  frameWidth: number;
  frameHeight: number;
  anchor?: { x: number; y: number };
  clips: Record<string, ClipManifest>;
  randomClips?: string[];
  randomGap?: [number, number];
}

const ROOT = '/merchant';
const IDLE = 'idle';

let atlasPromise: Promise<MerchantAtlas | null> | null = null;

export function loadMerchant(): Promise<MerchantAtlas | null> {
  atlasPromise ??= fetchMerchant();
  return atlasPromise;
}

async function fetchMerchant(): Promise<MerchantAtlas | null> {
  try {
    const manifest = await loadJson<MerchantManifest>(`${ROOT}/manifest.json`);
    const names = Object.keys(manifest.clips);
    const images = await Promise.all(
      names.map((name) => loadImage(`${ROOT}/${manifest.clips[name].file}`)),
    );
    const clips: Record<string, MerchantClip> = {};
    names.forEach((name, index) => {
      const row = manifest.clips[name];
      clips[name] = {
        image: images[index],
        frames: row.frames,
        fps: row.fps,
        loop: row.loop === true,
      };
    });
    return {
      frameWidth: manifest.frameWidth,
      frameHeight: manifest.frameHeight,
      anchorX: manifest.anchor?.x ?? 0.5,
      anchorY: manifest.anchor?.y ?? 1,
      clips,
      // Only clips that actually loaded — a manifest naming one whose file is
      // missing would otherwise wedge the player on a clip with no image.
      randomClips: (manifest.randomClips ?? []).filter((name) => name in clips),
      randomGap: manifest.randomGap ?? [4, 11],
    };
  } catch (err) {
    console.warn('[merchant] no merchant atlas:', err);
    atlasPromise = null;
    return null;
  }
}

/**
 * Which clip he is playing and how far into it, advanced by `dt`.
 *
 * Owned by the caller and stepped once a frame. Deliberately a plain mutable
 * struct rather than a class: there is exactly one merchant on exactly one
 * map, and `Game` already owns the lifetime of everything else on it.
 */
export interface MerchantPose {
  clip: string;
  /** Seconds into the current clip. */
  t: number;
  /** Seconds of idle left before the next interruption. */
  wait: number;
}

export function newMerchantPose(atlas: MerchantAtlas | null): MerchantPose {
  return { clip: IDLE, t: 0, wait: rollGap(atlas) };
}

function rollGap(atlas: MerchantAtlas | null): number {
  const [lo, hi] = atlas?.randomGap ?? [4, 11];
  return lo + Math.random() * Math.max(0, hi - lo);
}

/**
 * Advance the performance.
 *
 * A one-shot that runs off its last frame hands back to the idle and rolls a
 * fresh gap; the idle counts that gap down and then picks the next flourish.
 * The gap is only spent while he is IDLING, so a long clip does not eat the
 * pause that was supposed to follow it.
 */
export function stepMerchant(
  pose: MerchantPose,
  atlas: MerchantAtlas | null,
  dt: number,
): void {
  if (!atlas) return;
  pose.t += dt;
  const clip = atlas.clips[pose.clip];
  if (!clip) {
    pose.clip = IDLE;
    pose.t = 0;
    return;
  }
  if (pose.clip === IDLE) {
    pose.wait -= dt;
    if (pose.wait <= 0 && atlas.randomClips.length > 0) {
      const pick = atlas.randomClips[
        Math.floor(Math.random() * atlas.randomClips.length)
      ];
      pose.clip = pick;
      pose.t = 0;
    }
    return;
  }
  if (pose.t >= clip.frames / clip.fps) {
    pose.clip = IDLE;
    pose.t = 0;
    pose.wait = rollGap(atlas);
  }
}

/** The frame to blit for a pose: clip, source x, and the sheet holding it. */
export function merchantFrame(
  pose: MerchantPose,
  atlas: MerchantAtlas,
): { image: HTMLImageElement; sx: number } | null {
  const clip = atlas.clips[pose.clip] ?? atlas.clips[IDLE];
  if (!clip) return null;
  const step = Math.floor(pose.t * clip.fps);
  const index = clip.loop
    ? ((step % clip.frames) + clip.frames) % clip.frames
    : Math.min(clip.frames - 1, Math.max(0, step));
  return { image: clip.image, sx: index * atlas.frameWidth };
}
