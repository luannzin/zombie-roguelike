/**
 * Small numeric helpers shared by simulation, rendering and UI.
 *
 * These were previously re-implemented in camera / interpolation / prediction /
 * effects / renderer. Keep them dependency-free: this module is imported by
 * both the game core and React components.
 */

export function clamp(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value));
}

/** clamp(value, 0, 1) — the common case, spelled once. */
export function clamp01(value: number): number {
  return clamp(value, 0, 1);
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

/**
 * Frame-rate independent exponential decay factor for `dt` seconds.
 *
 * Multiply a value by this to decay it, or use `1 - expDamp(...)` as the lerp
 * factor when easing toward a target. Higher `rate` = faster settle.
 */
export function expDamp(rate: number, dt: number): number {
  return Math.exp(-rate * dt);
}

export interface Vec2 {
  x: number;
  y: number;
}

/**
 * Unit vector of (x, y). Returns `fallback` when the input is degenerate, so
 * callers never have to special-case a zero-length aim or velocity.
 */
export function normalize(x: number, y: number, fallback: Vec2 = { x: 0, y: 1 }): Vec2 {
  const length = Math.hypot(x, y);
  if (length <= 1e-4) return { x: fallback.x, y: fallback.y };
  return { x: x / length, y: y / length };
}

/** Progress of an aging effect, 1 at spawn to 0 at end of life. */
export function fadeOf(item: { age: number; life: number }): number {
  return item.life > 0 ? clamp01(1 - item.age / item.life) : 0;
}
