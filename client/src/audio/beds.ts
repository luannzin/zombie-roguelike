/**
 * Ambience: the layers that are always playing, and the crossfades between
 * them.
 *
 * The API is DECLARATIVE and that is the whole design. Callers do not start
 * and stop beds, they state what the world sounds like right now —
 * `setBeds({ fire: 0.8 })` in the camp, `setBeds({ wind: 1, night: 0.7 })` in
 * the forest — and this fades toward it. Two reasons:
 *
 *   The camp-to-forest hand-off is one call at one place instead of a stop
 *   here and a start there that have to be kept in sync across two screens and
 *   a march. Getting that wrong is silence in the middle of the transition, or
 *   a bonfire still crackling in the woods.
 *
 *   It is idempotent. The game can restate the same mix every frame and
 *   nothing retriggers, which means the caller does not have to track what is
 *   already playing.
 *
 * Every bed is started ONCE and never stopped while it is in the mix — it is
 * faded to zero and left running. Restarting a loop from sample zero on every
 * change would make the crossfade audible as a jump in the noise, and the
 * generator went to some trouble to make these seamless.
 */

import { busNode } from './engine';
import { loadBuffer, requestBuffer, soundEntry } from './library';

/** Seconds a bed takes to reach a new level. Long: weather does not switch. */
const FADE = 1.6;
/** Faster path for a hard cut, e.g. tearing everything down on dispose. */
const FADE_FAST = 0.25;

interface Voice {
  source: AudioBufferSourceNode;
  gain: GainNode;
  level: number;
}

const voices = new Map<string, Voice>();

/**
 * The mix that was last asked for, whether or not it could be honoured yet.
 *
 * This is what makes `setBeds` safe to call before the buffers have decoded —
 * and it always is, because the zone's ambience is stated on the `welcome`
 * that builds the world, which is long before a 300 KB wav has been fetched
 * and decoded. Without this the first call would find no buffer, start
 * nothing, and never be asked again: the forest would be silent for the whole
 * run. The retry below is scheduled by the decode itself, so it costs no
 * polling.
 */
let desired: Record<string, number> = {};
const retrying = new Set<string>();

function ensure(name: string): Voice | null {
  const existing = voices.get(name);
  if (existing) return existing;

  const entry = soundEntry(name);
  if (!entry?.loop) return null;

  const bus = busNode(entry.bus);
  if (!bus) return null;

  const buffer = requestBuffer(entry.files[0]);
  if (!buffer) {
    if (!retrying.has(name)) {
      retrying.add(name);
      void loadBuffer(entry.files[0])
        .then(() => {
          retrying.delete(name);
          // Re-apply rather than start this one bed: the mix may have moved on
          // twice while we were decoding, and `desired` is the only thing that
          // knows where it landed.
          apply(FADE);
        })
        .catch(() => retrying.delete(name));
    }
    return null;
  }

  const ctx = bus.context;
  const gain = ctx.createGain();
  gain.gain.value = 0;
  gain.connect(bus);

  const source = ctx.createBufferSource();
  source.buffer = buffer;
  source.loop = true;
  source.connect(gain);
  // Start somewhere random in the loop. Two clients that entered a room at
  // different times should not be listening to the same gust at the same
  // moment, and a bed that always starts at its first sample is a bed whose
  // period the player eventually learns.
  source.start(0, Math.random() * buffer.duration);

  const voice: Voice = { source, gain, level: 0 };
  voices.set(name, voice);
  return voice;
}

function rampTo(voice: Voice, entryGain: number, level: number, seconds: number): void {
  const param = voice.gain.gain;
  const now = voice.gain.context.currentTime;
  param.cancelScheduledValues(now);
  param.setValueAtTime(param.value, now);
  param.linearRampToValueAtTime(entryGain * level, now + seconds);
  voice.level = level;
}

function apply(seconds: number): void {
  for (const [name, level] of Object.entries(desired)) {
    if (level <= 0) continue;
    const voice = ensure(name);
    const entry = soundEntry(name);
    if (!voice || !entry) continue;
    if (Math.abs(voice.level - level) < 0.005) continue;
    rampTo(voice, entry.gain, level, seconds);
  }

  for (const [name, voice] of voices) {
    const level = desired[name] ?? 0;
    if (level > 0) continue;
    if (voice.level === 0) continue;
    const entry = soundEntry(name);
    if (entry) rampTo(voice, entry.gain, 0, seconds);
  }
}

/**
 * State the ambience. Anything not named is faded out; anything named is faded
 * in or adjusted. Levels are 0..1 on top of the manifest's own gain.
 *
 * Safe to call at any time, including before a single buffer has decoded —
 * see `desired`.
 */
export function setBeds(mix: Record<string, number>, seconds = FADE): void {
  desired = mix;
  apply(seconds);
}

/**
 * Set one bed's playback rate. The heartbeat is the caller: the same loop runs
 * faster as HP falls, which is one buffer doing the work of six.
 */
export function setBedRate(name: string, rate: number): void {
  const voice = voices.get(name);
  if (!voice) return;
  const param = voice.source.playbackRate;
  const now = voice.source.context.currentTime;
  param.cancelScheduledValues(now);
  param.setValueAtTime(param.value, now);
  param.linearRampToValueAtTime(rate, now + 0.4);
}

/** Fade everything out and release the nodes. Called from `Game.dispose()`. */
export function stopBeds(): void {
  desired = {};
  retrying.clear();
  for (const [, voice] of voices) {
    rampTo(voice, 1, 0, FADE_FAST);
    const source = voice.source;
    const gain = voice.gain;
    window.setTimeout(() => {
      try {
        source.stop();
      } catch {
        // Already stopped; nothing to do.
      }
      source.disconnect();
      gain.disconnect();
    }, FADE_FAST * 1000 + 60);
  }
  voices.clear();
}
