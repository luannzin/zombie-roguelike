/**
 * The audio context, its buses, and the two problems every browser game has
 * with sound.
 *
 * PROBLEM ONE: A page may not make noise until the user has touched it. An
 * `AudioContext` built on load starts `suspended`, and every sound played into
 * it is silently dropped. So the context is built LAZILY, on the first real
 * gesture, by a listener this module installs itself. Nothing else in the app
 * has to know that rule exists — `playSfx` before the first click is a no-op
 * rather than an error, and the first click that unlocks it is also the click
 * that plays the menu button. There is no "click to enable audio" gate, which
 * is a thing players should never be shown.
 *
 * PROBLEM TWO: Sound needs a volume control, and one master fader is not it.
 * Three buses hang off master — SFX, AMBIENT and UI — because the three fail
 * differently. Ambience that is slightly too loud is fatiguing over twenty
 * minutes in a way a gunshot is not; UI clicks that are fine in a menu are
 * intrusive over gameplay. Which bus a sound rides is decided in
 * `server/tools/make_audio.py` and travels on the manifest, so the mix is one
 * file rather than a number at every call site.
 *
 * Everything is ramped, never assigned. `gain.value = x` on a live graph is a
 * step discontinuity in the samples, which is a click — the same failure the
 * generator's `fade` exists to prevent, arriving from the other end.
 */

const STORAGE_KEY = 'zr:audio';

/**
 * Which fader a sound rides. Mirrors `bus` in the audio manifest, and each one
 * is a row in the options panel — so the split is a PLAYER-FACING taxonomy,
 * not an engineering one:
 *
 *   ui       the interface answering you: a refusal, the bag
 *   ambient  the loops that are always there: fire, wind, night, the heart
 *   sfx      guns and zombies — the loud, violent half
 *   misc     everything else that happens: footsteps, loot, crates, the lamp,
 *            the transitions
 *
 * `sfx` is deliberately narrow. A player who wants to turn combat down without
 * losing their own footsteps has to be able to, and that is only possible if
 * the violent sounds are their own group.
 */
export const BUSES = ['ui', 'ambient', 'sfx', 'misc'] as const;
export type Bus = (typeof BUSES)[number];

export interface AudioSettings {
  /** 0..1 per bus. The options panel shows these as 0..100. */
  volumes: Record<Bus, number>;
  muted: boolean;
}

/** Where a fresh install starts. */
const DEFAULT_VOLUMES: Record<Bus, number> = {
  ui: 0.5,
  ambient: 0.5,
  sfx: 0,
  misc: 0.5,
};

/**
 * Shortest ramp that is still a ramp. Below about 5 ms the step is audible
 * again; above about 20 ms a mute stops feeling like a button.
 */
const RAMP = 0.012;

/** Ramp used when the page is hidden or shown. Slower, because it is not a UI action. */
const BLUR_RAMP = 0.25;

interface Graph {
  ctx: AudioContext;
  master: GainNode;
  buses: Record<Bus, GainNode>;
}

let graph: Graph | null = null;
let settings: AudioSettings = loadSettings();
let hidden = false;
let listeners: (() => void)[] = [];

function loadSettings(): AudioSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as { volumes?: Partial<Record<Bus, number>>; muted?: boolean };
      const volumes = { ...DEFAULT_VOLUMES };
      for (const bus of BUSES) {
        const value = parsed.volumes?.[bus];
        // Per bus, not wholesale: a stored blob written before this bus
        // existed should keep the settings it does have and default the rest.
        if (typeof value === 'number') volumes[bus] = clamp01(value);
      }
      return { volumes, muted: Boolean(parsed.muted) };
    }
  } catch {
    // Private mode, blocked storage, or a value from an older shape. Defaults
    // are a fine answer; audio is not worth a failed boot.
  }
  return { volumes: { ...DEFAULT_VOLUMES }, muted: false };
}

function saveSettings(): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // Nothing to do. The setting simply will not survive a reload.
  }
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

/**
 * The standing balance BETWEEN the buses, under the player's faders.
 *
 * Not user-facing and not redundant with the sliders: this is what makes "50"
 * mean the same loudness on every row. UI sits low because it is the only
 * category that plays while nothing else is happening, which makes it feel far
 * louder than its numbers suggest.
 */
const BUS_TRIM: Record<Bus, number> = {
  sfx: 1.0,
  ambient: 0.85,
  misc: 0.9,
  ui: 0.65,
};

/** The live context, or null if nothing has unlocked it yet. */
export function audioGraph(): Graph | null {
  return graph;
}

/** Destination for a sound on `bus`. Null until the context exists. */
export function busNode(bus: Bus): GainNode | null {
  return graph?.buses[bus] ?? null;
}

export function audioTime(): number {
  return graph?.ctx.currentTime ?? 0;
}

function build(): Graph {
  const Ctor: typeof AudioContext =
    window.AudioContext ??
    (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const ctx = new Ctor();

  const master = ctx.createGain();
  master.gain.value = masterTarget();
  master.connect(ctx.destination);

  const buses = {} as Record<Bus, GainNode>;
  for (const bus of BUSES) {
    const node = ctx.createGain();
    node.gain.value = busTarget(bus);
    node.connect(master);
    buses[bus] = node;
  }

  return { ctx, master, buses };
}

/** Master carries mute and the hidden-tab duck only. Levels live on the buses. */
function masterTarget(): number {
  return settings.muted || hidden ? 0 : 1;
}

function busTarget(bus: Bus): number {
  const volume = settings.volumes[bus];
  // Perceptual, not linear: a fader at 0.5 that is half the SAMPLES is nearly
  // as loud as full. Squaring puts the useful range under the player's hand,
  // and — the reason it matters here — makes a slider at 0 actually silent
  // rather than merely quiet.
  return BUS_TRIM[bus] * volume * volume;
}

function ramp(param: AudioParam, target: number, seconds: number): void {
  const now = graph?.ctx.currentTime ?? 0;
  param.cancelScheduledValues(now);
  param.setValueAtTime(param.value, now);
  param.linearRampToValueAtTime(target, now + seconds);
}

function applyMaster(seconds: number): void {
  if (!graph) return;
  ramp(graph.master.gain, masterTarget(), seconds);
}

function applyBus(bus: Bus, seconds: number): void {
  if (!graph) return;
  ramp(graph.buses[bus].gain, busTarget(bus), seconds);
}

let unlockedOnce: (() => void)[] = [];

/**
 * Build the context if it does not exist and resume it if the browser parked
 * it. Safe to call from anywhere and on every gesture — it is idempotent.
 */
export function unlockAudio(): void {
  if (!graph) {
    try {
      graph = build();
    } catch {
      // No Web Audio: the game is playable, just silent.
      return;
    }
    // Decoding cannot start before this moment — `decodeAudioData` needs the
    // context — so this is the earliest anything can be preloaded, and the
    // menu click that unlocks us is minutes before the first gunshot.
    const waiting = unlockedOnce;
    unlockedOnce = [];
    for (const fn of waiting) fn();
  }
  if (graph.ctx.state === 'suspended') void graph.ctx.resume();
}

/**
 * Install the gesture listeners that unlock audio, plus the visibility handler
 * that shuts it up when the tab goes away. Call once, from the app root.
 *
 * `onUnlock` runs on the frame the context first exists, which is the only
 * moment preloading can begin. Returns a teardown, because everything created
 * in this codebase has one.
 */
export function installAudioUnlock(onUnlock?: () => void): () => void {
  if (onUnlock) {
    if (graph) onUnlock();
    else unlockedOnce.push(onUnlock);
  }
  const unlock = () => unlockAudio();
  const events: (keyof WindowEventMap)[] = ['pointerdown', 'keydown', 'touchstart'];
  for (const event of events) {
    window.addEventListener(event, unlock, { passive: true });
  }

  const onVisibility = () => {
    hidden = document.visibilityState === 'hidden';
    applyMaster(BLUR_RAMP);
  };
  document.addEventListener('visibilitychange', onVisibility);

  return () => {
    for (const event of events) window.removeEventListener(event, unlock);
    document.removeEventListener('visibilitychange', onVisibility);
  };
}

export function getAudioSettings(): AudioSettings {
  return settings;
}

/** Set one bus, 0..1. The options panel divides its 0..100 by a hundred. */
export function setBusVolume(bus: Bus, value: number): void {
  settings = { ...settings, volumes: { ...settings.volumes, [bus]: clamp01(value) } };
  saveSettings();
  applyBus(bus, RAMP);
  notify();
}

export function setMuted(muted: boolean): void {
  settings = { ...settings, muted };
  saveSettings();
  applyMaster(RAMP);
  notify();
}

export function toggleMuted(): boolean {
  setMuted(!settings.muted);
  return settings.muted;
}

/** Subscribe to settings changes — for a HUD readout. Returns an unsubscribe. */
export function onAudioSettingsChange(fn: () => void): () => void {
  listeners.push(fn);
  return () => {
    listeners = listeners.filter((entry) => entry !== fn);
  };
}

function notify(): void {
  for (const fn of listeners) fn();
}
