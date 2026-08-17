/**
 * Screen-space pose for the extraction-exit arrow.
 *
 * The game writes a TARGET every frame from the same camera the canvas used.
 * `ExitGuide` calls `stepExitGuide` in its own rAF and gets back the pose to
 * draw — no React state, so the HUD contract (no per-frame renders) stays
 * intact. Show/hide still comes from `hud-store` at 5 Hz.
 *
 * WHY THERE ARE TWO POSES AND A CLOCK IN HERE
 * The target is not smooth and cannot be made smooth upstream. `projectionFor`
 * ROUNDS the camera offset to a whole screen pixel, so the player's projected
 * position twitches half a pixel every frame; a ray cast from that point to the
 * screen edge multiplies the twitch by however far away the edge is, and near a
 * corner the intersection can jump the width of the screen between two frames
 * while the direction barely moved. Parked on the bezel and rounded to integers
 * on top of that, the arrow shook. So the smoothing lives here, next to the
 * explanation, rather than being sprinkled over the component.
 */

export interface ExitGuidePose {
  x: number;
  y: number;
  angle: number;
}

/**
 * How far along the ray the arrow sits, from the player toward the screen edge.
 *
 * HALFWAY, not on the bezel. An arrow pinned to the glass edge is furthest from
 * the thing it is about — you read the arrow, then look back at your character
 * to work out which way that is — and it is where the jitter is worst, because
 * the ray is longest there. Halfway out it sits in the same glance as the
 * player, it never fights the hotbar or the minimap for the corner, and the
 * same angular wobble moves it half as far.
 */
const REACH = 0.5;

/** Keep the ray's far point inside the glass, so `REACH` measures something. */
const EDGE_INSET = 22;

/**
 * Seconds for the smoothing to cover most of the gap, position and angle.
 *
 * Short enough that the arrow is never lying about where the exit is while you
 * turn, long enough to eat the per-frame rounding. The angle is quicker than
 * the position because a stale ANGLE is misinformation and a stale position is
 * only a lag.
 */
const POS_TAU = 0.085;
const ANGLE_TAU = 0.055;

let target: ExitGuidePose | null = null;
let shown: ExitGuidePose | null = null;

export function writeExitGuide(x: number, y: number, angle: number): void {
  if (target) {
    target.x = x;
    target.y = y;
    target.angle = angle;
    return;
  }
  target = { x, y, angle };
}

export function dropExitGuide(): void {
  target = null;
  shown = null;
}

/**
 * Advance the drawn pose toward the target and hand it back.
 *
 * Frame-rate independent: the fraction covered comes out of `exp(-dt / tau)`,
 * so a 144 Hz client and a 30 Hz one settle over the same wall time instead of
 * the fast one arriving in a third of it.
 */
export function stepExitGuide(dt: number): ExitGuidePose | null {
  if (!target) {
    shown = null;
    return null;
  }
  // First frame after it appears is a SNAP. Easing in from wherever the arrow
  // was last time would sweep it across the screen on every re-show.
  if (!shown) {
    shown = { x: target.x, y: target.y, angle: target.angle };
    return shown;
  }
  const step = Math.max(0, Math.min(0.1, dt));
  const kp = 1 - Math.exp(-step / POS_TAU);
  const ka = 1 - Math.exp(-step / ANGLE_TAU);
  shown.x += (target.x - shown.x) * kp;
  shown.y += (target.y - shown.y) * kp;
  shown.angle += shortestArc(shown.angle, target.angle) * ka;
  return shown;
}

/**
 * Signed shortest turn from `from` to `to`.
 *
 * Without it the arrow takes the long way round the moment the angle crosses
 * the -pi/+pi seam — a full backwards spin, on the one frame the player walked
 * past due west of the exit.
 */
function shortestArc(from: number, to: number): number {
  const tau = Math.PI * 2;
  return ((to - from + Math.PI) % tau + tau) % tau - Math.PI;
}

/**
 * Where the arrow belongs on screen, given the player's projected position and
 * a unit direction toward the exit.
 */
export function guidePoint(
  ox: number,
  oy: number,
  dx: number,
  dy: number,
  width: number,
  height: number,
): { x: number; y: number } {
  const edge = rayToScreenEdge(ox, oy, dx, dy, width, height);
  const from = clampToScreen(ox, oy, width, height, EDGE_INSET);
  return {
    x: from.x + (edge.x - from.x) * REACH,
    y: from.y + (edge.y - from.y) * REACH,
  };
}

function clampToScreen(
  x: number,
  y: number,
  width: number,
  height: number,
  inset: number,
): { x: number; y: number } {
  const maxX = Math.max(inset, width - inset);
  const maxY = Math.max(inset, height - inset);
  return {
    x: Math.min(maxX, Math.max(inset, x)),
    y: Math.min(maxY, Math.max(inset, y)),
  };
}

/**
 * Hit the inset screen rectangle from `(ox, oy)` along unit `(dx, dy)`.
 *
 * Origin is clamped inside first, so a player near the bezel still produces
 * a point on the far edge in the exit's direction.
 */
function rayToScreenEdge(
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
  const { x, y } = clampToScreen(ox, oy, width, height, inset);
  let t = Infinity;
  if (dx > 1e-6) t = Math.min(t, (maxX - x) / dx);
  else if (dx < -1e-6) t = Math.min(t, (minX - x) / dx);
  if (dy > 1e-6) t = Math.min(t, (maxY - y) / dy);
  else if (dy < -1e-6) t = Math.min(t, (minY - y) / dy);
  if (!Number.isFinite(t) || t < 0) return { x, y };
  return { x: x + dx * t, y: y + dy * t };
}
