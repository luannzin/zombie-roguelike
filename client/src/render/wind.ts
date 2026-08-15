/**
 * Wind: one field, read by everything that bends.
 *
 * Every plant already has its own sway phase, which is what stops a forest
 * looking like a screen filter. What per-plant noise cannot produce is the
 * thing that actually reads as WEATHER: a gust arriving somewhere and moving
 * across the clearing. A field of independently wobbling tufts is busy; a
 * field where a wave of them leans together and then lets go is windy.
 *
 * So this module owns the shared half, and it is deliberately the only shared
 * half. `gust()` is a travelling wave along `angle()` — a front that crosses
 * the map at a walking pace, sharpened so there is calm between pulses and
 * enveloped so there are calm MINUTES between runs of pulses. Plants add it on
 * top of their own breeze.
 *
 * THE POINT IS THE COUPLING. Grass, bushes, ferns and the scenery that sways
 * (a sign on its post, canvas on a tent) all read this same function, so when
 * a gust crosses a homestead the sign swings on the same beat as the weeds
 * around it. Two systems bending on unrelated clocks is what makes a 2D scene
 * feel assembled; one clock under all of it is most of what makes it feel like
 * a place with air in it.
 *
 * The field is a pure function of position and time, plus one climate
 * multiplier stated on zone arrival (`setClimate`). Rain pushes harder; fog
 * sits still. Lobby and arena still agree because they share the zone's coat.
 */

const TAU = Math.PI * 2;

/** Prevailing direction, in radians. Drifts, so the map has no fixed grain. */
const BASE_ANGLE = -0.7;
const ANGLE_SWING = 0.55;
const ANGLE_RATE = 0.031;

/** Distance between gust fronts, in world px. About a screen apart. */
const GUST_LENGTH = 300;
/**
 * Fronts per second. With `GUST_LENGTH` this puts the front at ~150 px/s —
 * comfortably faster than a player at `MOVE_SPEED`, so a gust overtakes you
 * rather than travelling with you, which is the difference between weather and
 * an aura stuck to the camera.
 */
const GUST_RATE = 0.5;
/**
 * Shapes the wave into pulses. At 1 the map breathes in and out constantly and
 * the whole forest looks like it is underwater; higher values spend most of
 * the cycle at rest, so an arriving gust is an EVENT.
 */
const GUST_SHARPNESS = 2.6;

/** Slow envelope, so calm stretches and blustery stretches alternate. */
const LULL_RATE = 0.043;
const LULL_FLOOR = 0.3;

/**
 * Climate multiplier. 1 is a dry night. Rain pushes harder; fog sits still.
 * Stated once on zone arrival — the lobby and the arena both get the same
 * coat, so they still agree without passing a clock between them.
 */
let climate = 1;

export function setClimate(kind: string): void {
  climate = kind === 'rain' ? 1.55 : kind === 'fog' ? 0.55 : 1;
}

/** Prevailing direction at this moment, in radians. */
export function angle(time: number): number {
  return BASE_ANGLE + Math.sin(time * ANGLE_RATE) * ANGLE_SWING;
}

/**
 * Gust strength at a world point, 0..1.
 *
 * Sampled at the plant's own position, which is what makes it a front rather
 * than a global multiplier: two tufts twenty tiles apart are at different
 * phases of the same wave, so the lean sweeps across the ground.
 */
export function gust(x: number, y: number, time: number): number {
  const a = angle(time);
  // Distance along the wind axis. The wave is a function of this alone, so its
  // crests are lines perpendicular to the wind — which is what a gust front is.
  const axis = x * Math.cos(a) + y * Math.sin(a);
  const wave = Math.sin((axis / GUST_LENGTH - time * GUST_RATE) * TAU);
  if (wave <= 0) return 0;
  const lull = LULL_FLOOR + (1 - LULL_FLOOR) * (0.5 + 0.5 * Math.sin(time * LULL_RATE * TAU));
  return wave ** GUST_SHARPNESS * lull * climate;
}

/**
 * Lean of one bending thing, in world px.
 *
 * Two terms, and they do different jobs. The BREEZE is per-plant — its own
 * phase and rate — and it is what keeps a still frame from looking frozen. The
 * GUST is shared, one-directional and additive, and it is what makes a moving
 * frame look like there is air in it. Only the gust can push everything the
 * same way at the same moment, and only the breeze can stop that from looking
 * like the screen tilting.
 */
export function lean(
  x: number,
  y: number,
  time: number,
  amount: number,
  phase: number,
  rate: number,
): number {
  const breeze = Math.sin(time * rate + phase);
  const push = gust(x, y, time);
  // The gust both ADDS a downwind push and amplifies the plant's own motion:
  // wind does not only bend a stem, it shakes it.
  return (breeze * (1 + push * 0.9) + push * Math.cos(angle(time)) * 1.35) * amount;
}
