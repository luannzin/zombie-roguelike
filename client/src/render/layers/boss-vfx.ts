/**
 * What his attacks LOOK like before, during and after they land.
 *
 * Three separate jobs, and they are separate because they answer three
 * different questions the player is asking at three different moments:
 *
 *   THE TELEGRAPH   "where is this going to hit?" — a mark on the ground,
 *                   during the windup, in the exact shape the server will
 *                   test. Drawn UNDER the bodies.
 *   THE TRAIL       "what just moved?" — a white-hot ribbon through the path
 *                   the bar took. Drawn OVER the bodies.
 *   THE RING        "he is spinning" — wind circling him for the length of
 *                   the sweep, which is the one attack whose danger is a
 *                   circle rather than a direction.
 *
 * THE TELEGRAPH IS THE HITBOX. Its radius and its arc come off
 * `welcome.config.bossMoves`, which `boss.Move.client_payload` builds from
 * the same numbers `_in_arc` tests against, and it fills over exactly the
 * windup the art authored. Nothing here is a shape somebody matched by eye —
 * a marker that promises a smaller wedge than the swing delivers teaches the
 * player a rule the simulation does not keep, and they learn it by standing
 * at the edge of the mark and dying there.
 *
 * GROUND MARKS ARE SQUASHED BY THE CAMERA, not by taste. `GROUND_SQUASH` is
 * the cosine of S1's pitch: a circle painted on the floor of a world seen
 * from 57 degrees above the horizon is an ellipse a little over half as tall
 * as it is wide. Drawing it round would read as a disc standing upright in
 * front of him.
 *
 * THE TRAIL IS PRESENTATION AND LIVES ENTIRELY ON THIS SIDE. The bar's tip is
 * not on the wire and should not be: it is sixty samples a second of
 * something nothing is decided by. `tipAt` re-derives it from the row's own
 * playhead against the arcs below, which MIRROR the ones `make_sawyer.py`
 * poses the sprite on — see `SWING`. They agree because both are driven by
 * the same `t`; re-time a clip's arc in the generator and this table is the
 * other half that has to move.
 */

import type { Projection } from '../projection';
import type { BossRow, GameConfig } from '../../net/protocol';

/** Cosine of the camera's pitch (S1: 55-60 degrees above the horizon). */
const GROUND_SQUASH = 0.55;

/**
 * Per move: where the bar starts and ends, in degrees RELATIVE TO HIS AIM,
 * and how far out the nose rides as a fraction of the move's own reach.
 *
 * These mirror `make_sawyer.py`'s `CHOP_ARC` / `RIP_ARC` projected onto the
 * ground plane. They are not the sprite's angles — the sprite swings in a
 * vertical plane and this is the shadow that swing casts on the floor — but
 * they start and end where the sprite's do, which is what makes the ribbon
 * leave the bar rather than float beside it.
 */
const SWING: Record<string, { from: number; to: number; radius: number }> = {
  // Overhead and across: cocked back over the far shoulder, down through the
  // aim, finishing past it. The widest arc he throws.
  chop: { from: -155, to: 35, radius: 1.0 },
  // The throw: a flat sweep across the body, right to left.
  rip: { from: -105, to: 95, radius: 0.72 },
  // The rev does not swing. It shakes, and `tipAt` gives it a jitter instead.
  rev: { from: -60, to: -48, radius: 0.55 },
};

/** How many turns the sweep makes. Mirrors `make_sawyer.TURNS`. */
const SWEEP_TURNS = 2;
/** Trail samples kept. At 60fps this is a fifth of a second of bar. */
export const TRAIL_LENGTH = 12;

export interface TrailPoint {
  x: number;
  y: number;
  /** Seconds old. Drives the taper and the fade. */
  age: number;
}

/**
 * Where the nose of the bar is right now, or null when it is not swinging.
 *
 * Returns null outside the three attack states so the caller stops feeding
 * the trail — a ribbon that keeps being extended while he stands still is a
 * ribbon that collapses to a dot on his hands and then smears when he moves.
 */
export function tipAt(row: BossRow, config: GameConfig): { x: number; y: number } | null {
  if (row.s !== 'windup' && row.s !== 'strike' && row.s !== 'recover') return null;
  const name = row.m;
  const move = name ? config.bossMoves?.[name] : undefined;
  if (!move || !name) return null;

  const aim = Math.atan2(row.ay, row.ax);
  const swingStart = move.windup * 0.55;
  const swingEnd = move.windup + move.active;

  if (name === 'sweep') {
    // A circle, not an arc: he turns on the spot for the whole active window
    // and the bar goes all the way round with him, twice.
    const spin = clamp01((row.t - move.windup) / Math.max(0.001, move.active));
    const angle = aim + spin * Math.PI * 2 * SWEEP_TURNS;
    return {
      x: row.x + Math.cos(angle) * move.reach,
      y: row.y + Math.sin(angle) * move.reach * GROUND_SQUASH,
    };
  }

  const arc = SWING[name];
  if (!arc) return null;
  const reach = move.reach > 0 ? move.reach : (config.bossCrescent?.radius ?? 16) * 2.6;
  // EASED, and eased HARD. A swing is not a constant angular rate — it is
  // slow through the cock, violent through the contact, and slow again out of
  // it. A linear sweep produces an even ribbon, which reads as a fan being
  // waved rather than as something heavy being thrown.
  const raw = clamp01((row.t - swingStart) / Math.max(0.001, swingEnd - swingStart));
  const eased = raw * raw * (3 - 2 * raw);
  const deg = arc.from + (arc.to - arc.from) * eased;
  const angle = aim + (deg * Math.PI) / 180;
  const shake = name === 'rev' ? Math.sin(row.t * 70) * 3 : 0;
  const r = reach * arc.radius + shake;
  return {
    x: row.x + Math.cos(angle) * r,
    y: row.y + Math.sin(angle) * r * GROUND_SQUASH,
  };
}

function clamp01(value: number): number {
  return value < 0 ? 0 : value > 1 ? 1 : value;
}

/**
 * The mark on the floor. Drawn BEFORE the bodies, so a player standing in it
 * is standing in it rather than behind it.
 *
 * It exists during the windup and for the frames the hitbox is open, and it
 * does two things over that time: it FILLS (the wedge sweeps out from his
 * facing) and it HEATS (his gold runs to red as the blow gets closer). Two
 * channels rather than one, because a mark that only fills is a mark you have
 * to be looking at to read, and a mark that only heats does not tell you how
 * long you have.
 */
export function drawBossTelegraph(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  row: BossRow,
  config: GameConfig,
): void {
  if (row.s !== 'windup' && row.s !== 'strike') return;
  const name = row.m;
  const move = name ? config.bossMoves?.[name] : undefined;
  if (!move) return;

  const striking = row.s === 'strike';
  // 0 at the start of the windup, 1 on the frame it lands.
  const charge = striking ? 1 : clamp01(row.t / Math.max(0.001, move.windup));
  const aim = Math.atan2(row.ay, row.ax);
  const zoom = view.zoom;
  const cx = view.x(row.x);
  const cy = view.y(row.y);

  ctx.save();
  ctx.globalCompositeOperation = 'lighter';

  if (name === 'rip') {
    drawLane(ctx, cx, cy, aim, zoom, charge, striking, config);
  } else if (move.arcDegrees >= 179) {
    drawRing(ctx, cx, cy, move.reach * zoom, charge, striking);
  } else if (move.reach > 0) {
    drawWedge(ctx, cx, cy, aim, move.reach * zoom, move.arcDegrees, charge, striking);
  }

  ctx.restore();
}

/** Colour of the mark at a given charge: his gold, running to red. */
function heat(charge: number, alpha: number): string {
  const r = Math.round(242 + (230 - 242) * charge);
  const g = Math.round(165 + (72 - 165) * charge);
  const b = Math.round(65 + (79 - 65) * charge);
  return `rgba(${r},${g},${b},${alpha})`;
}

/** The chop: a pie slice out of his facing, sweeping open as it charges. */
function drawWedge(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  aim: number,
  reach: number,
  arcDegrees: number,
  charge: number,
  striking: boolean,
): void {
  const half = ((arcDegrees / 2) * Math.PI) / 180;
  const grown = half * (0.3 + 0.7 * charge);
  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(1, GROUND_SQUASH);

  // The FILL is faint and the EDGE is not. A solid wedge under a boss is a
  // wedge you cannot see anything else through, and what the player is
  // reading in that half second is where their own feet are.
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.arc(0, 0, reach, aim - grown, aim + grown);
  ctx.closePath();
  ctx.fillStyle = heat(charge, striking ? 0.30 : 0.10 + 0.14 * charge);
  ctx.fill();

  ctx.lineWidth = (striking ? 2.4 : 1.4) / GROUND_SQUASH * 0.6;
  ctx.strokeStyle = heat(charge, striking ? 0.85 : 0.35 + 0.45 * charge);
  ctx.stroke();
  ctx.restore();
}

/** The sweep: a ring, because the danger is every direction at once. */
function drawRing(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  reach: number,
  charge: number,
  striking: boolean,
): void {
  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(1, GROUND_SQUASH);

  // An ANNULUS that closes inward, not a disc that fills. The ring shrinking
  // onto him is the thing that reads as "this is about to go off", and it is
  // the same language a fuse has.
  const inner = reach * (1 - charge) * 0.92;
  ctx.beginPath();
  ctx.arc(0, 0, reach, 0, Math.PI * 2);
  ctx.arc(0, 0, inner, 0, Math.PI * 2, true);
  ctx.fillStyle = heat(charge, striking ? 0.26 : 0.08 + 0.16 * charge);
  ctx.fill('evenodd');

  ctx.beginPath();
  ctx.arc(0, 0, reach, 0, Math.PI * 2);
  ctx.lineWidth = striking ? 2.6 : 1.6;
  ctx.strokeStyle = heat(charge, striking ? 0.9 : 0.4 + 0.45 * charge);
  ctx.stroke();
  ctx.restore();
}

/** The throw: a lane the length the crescent will actually travel. */
function drawLane(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  aim: number,
  zoom: number,
  charge: number,
  striking: boolean,
  config: GameConfig,
): void {
  const spec = config.bossCrescent;
  if (!spec) return;
  const length = spec.reach * zoom * (0.35 + 0.65 * charge);
  const half = spec.radius * zoom;
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(aim);
  ctx.scale(1, GROUND_SQUASH);

  ctx.beginPath();
  ctx.rect(0, -half, length, half * 2);
  ctx.fillStyle = heat(charge, striking ? 0.26 : 0.08 + 0.14 * charge);
  ctx.fill();
  ctx.lineWidth = striking ? 2.4 : 1.4;
  ctx.strokeStyle = heat(charge, striking ? 0.85 : 0.32 + 0.45 * charge);
  ctx.stroke();
  ctx.restore();
}

/**
 * WIND. Circling him for the length of the spin, and only the spin.
 *
 * Streaks on two radii turning at two rates, which is the whole trick: one
 * ring of anything turning at one rate reads as a wheel, and two rings at
 * different rates read as air being dragged round. They are drawn additively
 * and kept faint — this is the frame with the most going on in the whole
 * game, and the wind is the last thing that should be competing for it.
 */
export function drawSweepWind(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  row: BossRow,
  config: GameConfig,
  time: number,
): void {
  if (row.s !== 'strike' || row.m !== 'sweep') return;
  const move = config.bossMoves?.sweep;
  if (!move) return;
  const life = clamp01((row.t - 0) / Math.max(0.001, move.active));
  // Up fast, down slow: the air is moving before the second turn and is still
  // settling when he stops.
  const strength = Math.min(1, life * 6) * (1 - life * 0.35);
  if (strength <= 0.02) return;

  const cx = view.x(row.x);
  const cy = view.y(row.y);
  const zoom = view.zoom;

  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  ctx.translate(cx, cy);
  ctx.scale(1, GROUND_SQUASH);
  ctx.lineCap = 'round';

  for (const band of [0, 1]) {
    const radius = move.reach * zoom * (band ? 1.16 : 0.82);
    const rate = band ? -5.2 : 7.4;
    const streaks = band ? 5 : 7;
    ctx.lineWidth = (band ? 1.6 : 2.4) * zoom * 0.5;
    for (let i = 0; i < streaks; i++) {
      const at = time * rate + (i / streaks) * Math.PI * 2;
      const span = 0.42 + 0.2 * Math.sin(time * 9 + i);
      ctx.beginPath();
      ctx.arc(0, 0, radius, at, at + span);
      ctx.strokeStyle = `rgba(226,220,208,${(band ? 0.10 : 0.16) * strength})`;
      ctx.stroke();
    }
  }
  ctx.restore();
}

/**
 * The bar's own path, as a white-hot ribbon.
 *
 * Two passes over the same points: a wide warm one and a narrow white one on
 * top. That is what a hot edge looks like and it is the same construction the
 * muzzle flashes use — one pass alone is either a fat glow with no edge in it
 * or a hard line with no heat.
 *
 * It TAPERS from the head, so the ribbon has a direction. A trail of constant
 * width is a rope somebody laid on the floor.
 */
export function drawBossTrail(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  trail: readonly TrailPoint[],
  rage: boolean,
): void {
  if (trail.length < 2) return;
  const zoom = view.zoom;
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  for (const pass of [0, 1]) {
    for (let i = 1; i < trail.length; i++) {
      const a = trail[i - 1];
      const b = trail[i];
      // Age is measured from the HEAD of the list, which is the newest point.
      const t = 1 - i / trail.length;
      const fade = t * t;
      if (fade < 0.02) continue;
      ctx.beginPath();
      ctx.moveTo(view.x(a.x), view.y(a.y));
      ctx.lineTo(view.x(b.x), view.y(b.y));
      if (pass === 0) {
        ctx.lineWidth = 5.5 * zoom * 0.5 * t;
        ctx.strokeStyle = rage
          ? `rgba(230,72,79,${0.30 * fade})`
          : `rgba(242,165,65,${0.28 * fade})`;
      } else {
        ctx.lineWidth = 2.0 * zoom * 0.5 * t;
        ctx.strokeStyle = `rgba(255,241,214,${0.62 * fade})`;
      }
      ctx.stroke();
    }
  }
  ctx.restore();
}

/**
 * The hit itself: a bright crescent thrown across the contact point.
 *
 * Short — a tenth of a second — and shaped like the swing rather than round.
 * A circular flash on a chainsaw landing reads as an explosion, and nothing
 * about this weapon explodes.
 */
export function drawBossImpact(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  hit: { x: number; y: number; dx: number; dy: number; age: number; life: number; power: number },
): void {
  const t = clamp01(hit.age / hit.life);
  if (t >= 1) return;
  const fade = (1 - t) * (1 - t);
  const zoom = view.zoom;
  const aim = Math.atan2(hit.dy, hit.dx);
  const radius = (10 + 26 * t) * hit.power * zoom * 0.5;

  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  ctx.translate(view.x(hit.x), view.y(hit.y));
  ctx.rotate(aim);
  ctx.scale(1, GROUND_SQUASH);
  ctx.lineCap = 'round';

  for (const pass of [0, 1]) {
    ctx.beginPath();
    ctx.arc(0, 0, radius, -1.05, 1.05);
    ctx.lineWidth = (pass === 0 ? 7 : 2.6) * zoom * 0.5 * (1 - t * 0.6);
    ctx.strokeStyle = pass === 0
      ? `rgba(242,165,65,${0.34 * fade})`
      : `rgba(255,247,232,${0.8 * fade})`;
    ctx.stroke();
  }
  ctx.restore();
}
