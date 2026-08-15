/**
 * The sound catalog: the manifest `make_audio.py` wrote, and the decoded
 * buffers behind it.
 *
 * Same caching discipline as `lib/image.ts`, and for the same reason — the
 * lobby and the arena are different objects that want the same footsteps, and
 * decoding a wav twice at the seam is dead time in the one transition built to
 * have none. Failures are not cached: a network blip on the first fetch must
 * not permanently mute a sound.
 *
 * NOTHING HERE KNOWS WHAT A SOUND MEANS. Names, per-sound gain and bus routing
 * all come off the manifest, which is generated. Adding a sound to the game is
 * a recipe in `server/tools/make_audio.py` and a call site — never an edit
 * here.
 */

import type { Bus } from './engine';
import { audioGraph } from './engine';

/** One catalog entry. Mirrors the manifest written by `make_audio.py`. */
export interface SoundEntry {
  /** Variants of the same sound. One is picked per play. */
  files: string[];
  /** Mix level authored in the generator. */
  gain: number;
  bus: Bus;
  /** Beds only. A looping buffer whose ends were crossfaded to meet. */
  loop?: boolean;
}

interface AudioManifest {
  sounds: Record<string, SoundEntry>;
}

const ROOT = '/audio';

let manifest: AudioManifest | null = null;
let manifestPending: Promise<AudioManifest> | null = null;
const buffers = new Map<string, Promise<AudioBuffer>>();

export function loadAudioManifest(): Promise<AudioManifest> {
  if (manifest) return Promise.resolve(manifest);
  if (manifestPending) return manifestPending;

  manifestPending = (async () => {
    const response = await fetch(`${ROOT}/manifest.json`);
    if (!response.ok) throw new Error(`${ROOT}/manifest.json: ${response.status}`);
    const parsed = (await response.json()) as AudioManifest;
    manifest = parsed;
    return parsed;
  })().catch((err: unknown) => {
    manifestPending = null;
    throw err;
  });

  return manifestPending;
}

/** The catalog entry for `name`, or null if the manifest has not landed yet. */
export function soundEntry(name: string): SoundEntry | null {
  return manifest?.sounds[name] ?? null;
}

/**
 * Fetch and decode one file.
 *
 * `decodeAudioData` needs the context, so this can only work once something
 * has unlocked audio. Before that it rejects, and every caller treats a
 * missing buffer as silence — which is correct: sounds that would have played
 * before the player's first click are sounds nobody was going to hear.
 */
export function loadBuffer(file: string): Promise<AudioBuffer> {
  const cached = buffers.get(file);
  if (cached) return cached;

  const pending = (async () => {
    const graph = audioGraph();
    if (!graph) throw new Error('audio locked');
    const response = await fetch(`${ROOT}/${file}`);
    if (!response.ok) throw new Error(`${ROOT}/${file}: ${response.status}`);
    return await graph.ctx.decodeAudioData(await response.arrayBuffer());
  })().catch((err: unknown) => {
    buffers.delete(file);
    throw err;
  });

  buffers.set(file, pending);
  return pending;
}

/**
 * The synchronous side of the cache.
 *
 * The frame loop cannot await. `playSfx` asks for a buffer, and if it is not
 * decoded yet it starts the decode and drops that one play — which is the
 * right trade for a footstep and is why `prime` exists for everything that
 * matters.
 */
const decoded = new Map<string, AudioBuffer>();

export function requestBuffer(file: string): AudioBuffer | null {
  const ready = decoded.get(file);
  if (ready) return ready;
  void loadBuffer(file)
    .then((buffer) => decoded.set(file, buffer))
    .catch(() => {
      // Already logged by the fetch; a missing sound is silence, not a crash.
    });
  return null;
}

/**
 * Decode a set of sounds up front. Await this before a moment that must not be
 * silent — the first gunshot, the arrival sting, the bonfire bed.
 */
export async function primeAudio(names: string[]): Promise<void> {
  const catalog = await loadAudioManifest();
  const files: string[] = [];
  for (const name of names) {
    const entry = catalog.sounds[name];
    if (entry) files.push(...entry.files);
  }
  await Promise.all(
    files.map((file) =>
      loadBuffer(file)
        .then((buffer) => decoded.set(file, buffer))
        .catch(() => undefined),
    ),
  );
}

/** Drop every decoded buffer. Regenerating audio in `assets/` is the only reason. */
export function clearAudioCache(): void {
  buffers.clear();
  decoded.clear();
  manifest = null;
  manifestPending = null;
}

if (import.meta.hot) {
  import.meta.hot.on('vite:afterUpdate', clearAudioCache);
}
