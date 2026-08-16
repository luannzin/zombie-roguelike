/**
 * Screen-space pose for the extraction-exit caret.
 *
 * The game writes this every frame from the same camera the canvas used.
 * `ExitGuide` reads it in its own rAF and sets a transform — no React state,
 * so the HUD contract (no per-frame renders) stays intact. Show/hide still
 * comes from `hud-store` at 5 Hz.
 */

export interface ExitGuidePose {
  x: number;
  y: number;
  angle: number;
}

/** Keep the caret off the glass edge so it stays readable. */
const EDGE_INSET = 28;

let pose: ExitGuidePose | null = null;

export function writeExitGuide(x: number, y: number, angle: number): void {
  if (pose) {
    pose.x = x;
    pose.y = y;
    pose.angle = angle;
    return;
  }
  pose = { x, y, angle };
}

export function readExitGuide(): ExitGuidePose | null {
  return pose;
}

export function dropExitGuide(): void {
  pose = null;
}

/**
 * Hit the inset screen rectangle from `(ox, oy)` along unit `(dx, dy)`.
 *
 * Origin is clamped inside first, so a player near the bezel still produces
 * a point on the far edge in the exit's direction.
 */
export function rayToScreenEdge(
  ox: number,
  oy: number,
  dx: number,
  dy: number,
  width: number,
  height: number,
  inset = EDGE_INSET,
): { x: number; y: number } {
  const minX = inset;
  const minY = inset;
  const maxX = Math.max(minX, width - inset);
  const maxY = Math.max(minY, height - inset);
  const x = Math.min(maxX, Math.max(minX, ox));
  const y = Math.min(maxY, Math.max(minY, oy));
  let t = Infinity;
  if (dx > 1e-6) t = Math.min(t, (maxX - x) / dx);
  else if (dx < -1e-6) t = Math.min(t, (minX - x) / dx);
  if (dy > 1e-6) t = Math.min(t, (maxY - y) / dy);
  else if (dy < -1e-6) t = Math.min(t, (minY - y) / dy);
  if (!Number.isFinite(t) || t < 0) return { x, y };
  return { x: x + dx * t, y: y + dy * t };
}
