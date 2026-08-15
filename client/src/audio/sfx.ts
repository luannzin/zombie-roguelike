/**
 * Playing one-shots, and making them not sound like one-shots.
 *
 * Three things happen to every sound between the catalog and the speakers, and
 * all three exist to fight the same failure — a sample played twice in a row
 * announces that it is a sample:
 *
 *   VARIANT   the generator rendered several from different seeds; one is
 *             picked, and never the one that just played.
 *   DETUNE    playback rate is nudged a few percent. Free pitch and length
 *             variation on top of the variants, so four footsteps cover a walk
 *             of any length without a pattern surfacing.
 *   SPACE     a world position becomes pan and level against the listener, so
 *             a growl behind you to the left IS behind you to the left.
 *
 * SPACE IS THE ONE THAT MATTERS. The lantern makes this a game about not being
 * able to see, which makes every other channel the player has worth more. A
 * zombie you cannot see but can place is the difference between tension and
 * ambush, and it costs one pan node.
 *
 * Distance falloff is authored in TILES, like everything spatial in this
 * codebase, and converted with the tile size the server sent.
 */

import { busNode, unlockAudio } from './engine';
import { requestBuffer, soundEntry } from './library';

/** Full volume inside this radius, in tiles. Roughly "in the room with you". */
const NEAR_TILES = 3;
/** Silent past this, in tiles. A little beyond what a lantern ever shows. */
const FAR_TILES = 22;
/**
 * How hard a sound is pushed to one side, 0..1. Never 1: a sound panned fully
 * to one ear reads as broken headphones rather than as a direction, and a
 * player on speakers loses it completely.
 */
const MAX_PAN = 0.7;
/** Pan is full-scale at this lateral distance, in tiles. */
const PAN_TILES = 9;

export interface PlayOptions {
  /** Extra gain on top of the manifest's. 1 = as authored. */
  gain?: number;
  /** Extra playback rate on top of the jitter. 1 = as authored. */
  rate?: number;
  /** -1..1. Overridden by `playSfxAt`. */
  pan?: number;
  /** Seconds to wait before it starts. For deliberate beats, not for latency. */
  delay?: number;
  /** Force a variant instead of picking one. For rarity tiers and soil types. */
  variant?: number;
  /** Peak-to-peak detune, as a fraction. 0 disables it. */
  jitter?: number;
}

/** Default detune spread. Wide enough to hide repetition, narrow enough to stay in tune. */
const DEFAULT_JITTER = 0.09;

/** Last variant played per sound, so the picker never repeats immediately. */
const lastVariant = new Map<string, number>();

/**
 * Where the listener is, in world pixels, and how big a tile is.
 *
 * Set once a frame by the game. Kept here rather than passed per call because
 * every spatial sound in a frame shares it, and because a call site that has
 * to look up the camera to play a footstep will eventually get it wrong.
 */
let listenerX = 0;
let listenerY = 0;
let tileSize = 16;

export function setAudioListener(x: number, y: number, tile: number): void {
  listenerX = x;
  listenerY = y;
  tileSize = tile;
}

function pickVariant(name: string, count: number, forced?: number): number {
  if (forced !== undefined) return Math.max(0, Math.min(count - 1, forced));
  if (count <= 1) return 0;
  const previous = lastVariant.get(name);
  let index = (Math.random() * count) | 0;
  if (index === previous) index = (index + 1) % count;
  lastVariant.set(name, index);
  return index;
}

/**
 * Play `name`. Returns false if it could not — locked audio, unknown name, or
 * a buffer that is still decoding.
 *
 * Never throws and never waits. A sound that is not ready is a sound that does
 * not play; the frame loop keeps its budget and the next one will have it.
 */
export function playSfx(name: string, options: PlayOptions = {}): boolean {
  const entry = soundEntry(name);
  if (!entry) return false;

  const bus = busNode(entry.bus);
  if (!bus) return false;

  const variant = pickVariant(name, entry.files.length, options.variant);
  const buffer = requestBuffer(entry.files[variant]);
  if (!buffer) return false;

  const ctx = bus.context;
  const source = ctx.createBufferSource();
  source.buffer = buffer;

  const jitter = options.jitter ?? DEFAULT_JITTER;
  source.playbackRate.value = (options.rate ?? 1) * (1 + (Math.random() - 0.5) * jitter);

  const gain = ctx.createGain();
  gain.gain.value = entry.gain * (options.gain ?? 1);

  const pan = options.pan ?? 0;
  if (pan !== 0 && typeof ctx.createStereoPanner === 'function') {
    const panner = ctx.createStereoPanner();
    panner.pan.value = Math.max(-1, Math.min(1, pan));
    source.connect(gain).connect(panner).connect(bus);
  } else {
    source.connect(gain).connect(bus);
  }

  source.start(ctx.currentTime + (options.delay ?? 0));
  // Buffer sources are single-use; dropping the graph on `ended` is what keeps
  // a two-hour session from accumulating thousands of dead nodes.
  source.onended = () => {
    source.disconnect();
    gain.disconnect();
  };
  return true;
}

/** Level and pan for a world point against the current listener. */
export function spatial(x: number, y: number): { gain: number; pan: number } {
  const dx = x - listenerX;
  const dy = y - listenerY;
  const distance = Math.hypot(dx, dy) / tileSize;

  let gain: number;
  if (distance <= NEAR_TILES) {
    gain = 1;
  } else if (distance >= FAR_TILES) {
    gain = 0;
  } else {
    // Squared falloff: linear stays too loud too far out and the forest ends up
    // sounding like a small room with everything in it.
    const t = 1 - (distance - NEAR_TILES) / (FAR_TILES - NEAR_TILES);
    gain = t * t;
  }

  const pan = Math.max(-1, Math.min(1, dx / (PAN_TILES * tileSize))) * MAX_PAN;
  return { gain, pan };
}

/**
 * Play `name` as coming from a world point.
 *
 * Silently drops anything out of range, which is most of what a busy map would
 * otherwise ask for — this is the budget guard as much as it is the effect.
 */
export function playSfxAt(
  name: string,
  x: number,
  y: number,
  options: PlayOptions = {},
): boolean {
  const { gain, pan } = spatial(x, y);
  if (gain <= 0.02) return false;
  return playSfx(name, { ...options, gain: (options.gain ?? 1) * gain, pan });
}

/**
 * A cheap way to stop a swarm from stacking into a wall of noise.
 *
 * Six zombies in a pack all growling on the same frame is not six times as
 * scary, it is a drone. Callers pass a key and a minimum spacing; anything
 * that comes too soon after the last one on that key is dropped.
 */
const lastAt = new Map<string, number>();

export function throttled(key: string, minSeconds: number, now: number): boolean {
  const previous = lastAt.get(key);
  if (previous !== undefined && now - previous < minSeconds) return false;
  lastAt.set(key, now);
  return true;
}

/** Drop throttle and variant history. Called when a Game is disposed. */
export function resetSfxState(): void {
  lastAt.clear();
  lastVariant.clear();
}

/** Re-exported so call sites do not need the engine directly. */
export { unlockAudio };
