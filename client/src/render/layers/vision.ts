/**
 * Enemy tells worn over the head: the hunt diamond, and the miniboss crown.
 *
 * There is no floor cone. The diamond IS the feedback:
 *
 *   idle          nothing at all
 *   noticing      empty diamond, a sliver of fill at the bottom
 *   working you   fill climbs
 *   hunting       full, and it stays that way
 *
 * Hidden while idle. Drawn OVER the darkness only when this client has
 * already seen the creature while it was alerting (`alertKnown`): killing
 * the lamp then does not hide that it has you. A hunter that committed in
 * the dark, never seen, wears nothing — that would be a free tracker.
 * The body itself still vanishes. Painted as world-pixel rectangles, not
 * as type — it lives in the forest, not on the HUD.
 *
 * THE CROWN IS THE OTHER HALF AND IT ANSWERS A DIFFERENT QUESTION. The
 * diamond says WHAT IT IS DOING; the crown says WHAT IT IS. It is worn by any
 * creature whose stat block carries a rank (`EnemyTypeConfig.rank`), it does
 * not fill, and it is drawn UNLIT while the thing is still asleep — which is
 * the whole miniboss encounter in one mark: there it is, it has not seen you,
 * and the next move is yours. It lights on the frame its eyes open.
 *
 * It sits above the diamond rather than replacing it, because a party that
 * has already woken one still needs to know whether it is coming.
 */

import { clamp01 } from '../../lib/math';
import { palette, type Channels } from '../../theme/palette';
import type { EntityContext } from './entities';
import { RANK_MINIBOSS, type DrawableEntity } from '../types';

/**
 * Awareness at which the diamond appears. Below this the creature is
 * wandering and the woods stay quiet.
 */
export const NOTICE_AT = 0.05;
/** Awareness at or above which an enemy is hunting, and the diamond is full. */
const ALERT_AT = 0.999;

/**
 * The diamond, in WORLD pixels of the art's own grid (1 unit = tileSize/16),
 * then scaled by MARK_SCALE. Half-widths per row from the top: a 5-wide,
 * 7-tall lozenge at scale 1.
 */
const MARK_SCALE = 0.5;
const DIA_ROWS = [0, 1, 2, 2, 2, 1, 0] as const;
/** How far above the top of the sprite it floats, same unscaled units. */
const DIA_LIFT = 3;

/** The bang inside: a two-tall bar, a one-tall gap, a one-tall dot. */
const BANG_W = 1;
const BANG_BAR = 2;
const BANG_GAP = 1;

/** Committed diamonds breathe. Depth and rate of that pulse. */
const PULSE_DEPTH = 0.14;
const PULSE_RATE = 7;

/**
 * The hunt diamond over every enemy this client has already seen alerting.
 *
 * WORLD space, drawn AFTER the darkness pass on purpose: once latched, this
 * is the one tell that must survive the lamp going out. A mark on a hunter
 * you never saw would be a free tracker.
 */
export function drawAlertMarks(
  entity: EntityContext,
  entities: readonly DrawableEntity[],
  time: number,
): void {
  const { ctx, config, book } = entity;
  const tone = palette().enemyView;
  const shadow = palette().entity.labelShadow;
  const unit = (config.tileSize / 16) * MARK_SCALE;
  const rows = DIA_ROWS.length;
  const mid = (rows - 1) / 2;

  for (const target of entities) {
    if (target.kind !== 'enemy' || !target.alive || !target.alertKnown) continue;
    const awareness = clamp01(target.awareness);
    if (awareness < NOTICE_AT) continue;

    const frameHeight = book.get(target.sheet)?.frameHeight ?? config.spriteHeight;
    const spriteTop = target.y + target.recoilY + target.halfHeight - frameHeight;
    const cx = Math.round(target.x + target.recoilX);
    const cy = Math.round(spriteTop - DIA_LIFT * unit - mid * unit);

    const ramp = (awareness - NOTICE_AT) / (1 - NOTICE_AT);
    const [r, g, b] = mix(tone, ramp);
    const pulse =
      awareness >= ALERT_AT ? 1 + Math.sin(time * PULSE_RATE) * PULSE_DEPTH : 1;
    const fillAlpha = Math.min(1, (0.55 + 0.45 * ramp) * pulse);
    const fill = `rgba(${r},${g},${b},${fillAlpha})`;
    const edge = `rgb(${r},${g},${b})`;

    // Bed first, one unit larger, so the lozenge reads on firelight and on
    // a black field alike.
    stampDiamond(ctx, cx, cy, unit, 1, shadow);
    stampDiamond(ctx, cx, cy, unit, 0, shadow);

    // Fill climbs from the bottom. A just-noticed sliver is one row; a
    // hunter is the whole stone.
    const filled = Math.max(1, Math.ceil(rows * ramp));
    const fillFrom = rows - filled;
    ctx.fillStyle = fill;
    for (let row = fillFrom; row < rows; row++) {
      const hw = DIA_ROWS[row];
      const inset = hw > 0 ? 1 : 0;
      const inner = hw - inset;
      if (inner < 0) continue;
      ctx.fillRect(
        cx - inner * unit,
        cy + row * unit,
        (inner * 2 + 1) * unit,
        unit,
      );
    }

    stampDiamondOutline(ctx, cx, cy, unit, edge);

    const bangX = cx - Math.floor(BANG_W / 2) * unit;
    const barTop = cy + 1 * unit;
    const dotTop = barTop + (BANG_BAR + BANG_GAP) * unit;
    stampBang(ctx, bangX, barTop, BANG_W * unit, BANG_BAR * unit, unit, shadow, tone.mark);
    stampBang(ctx, bangX, dotTop, BANG_W * unit, unit, unit, shadow, tone.mark);
  }
}

/**
 * The crown, in the same world-pixel units the diamond is stamped in: half
 * widths per row from the top, so it is drawn by the same loop.
 *
 * THREE PEAKS AND A BAND, and it is three because the thing under it has
 * three heads — but the shape is authored rather than derived from the head
 * count on purpose. A mark that counted heads would be a second, worse
 * drawing of the sprite; what this has to say is "this one is not like the
 * others", and it has to say it identically for whatever the next miniboss
 * turns out to be.
 */
const CROWN_ROWS: readonly (readonly [number, number])[][] = [
  // Row 0: three points, one pixel each.
  [
    [-2, -2],
    [0, 0],
    [2, 2],
  ],
  // Row 1: the points widen and the valleys are still open.
  [
    [-2, -1],
    [1, 2],
  ],
  // Row 2: the band, solid across.
  [[-2, 2]],
];
/** How far above the diamond (or the head, with no diamond) the crown sits. */
const CROWN_LIFT = 3;

/**
 * The rank mark over every creature whose stat block has one.
 *
 * Same pass and same rules as the diamond: after the darkness, so a miniboss
 * this client has seen hunting keeps its crown when the lamp goes out, and
 * faded with the body otherwise. A crown on something nobody has ever laid
 * eyes on would be a free tracker, which is the one thing the hunt tell has
 * always refused to be.
 */
export function drawRankMarks(
  entity: EntityContext,
  entities: readonly DrawableEntity[],
  time: number,
): void {
  const { ctx, config, book } = entity;
  const tone = palette().enemyView;
  const shadow = palette().entity.labelShadow;
  const unit = (config.tileSize / 16) * MARK_SCALE;

  for (const target of entities) {
    if (target.kind !== 'enemy' || !target.alive) continue;
    if (target.rank !== RANK_MINIBOSS) continue;
    const seen = Math.max(target.visibility, target.alertKnown ? 1 : 0);
    if (seen <= 0.01) continue;

    const frameHeight = book.get(target.sheet)?.frameHeight ?? config.spriteHeight;
    const spriteTop = target.y + target.recoilY + target.halfHeight - frameHeight;
    const cx = Math.round(target.x + target.recoilX);
    // Clear of the diamond when there is one, and of the head when there is
    // not. Two marks on one head must never overlap: the pair is read as a
    // pair, and a crown sitting in a lozenge is one illegible blob.
    const stack =
      target.alertKnown && clamp01(target.awareness) >= NOTICE_AT
        ? DIA_ROWS.length + DIA_LIFT
        : DIA_LIFT;
    const top = Math.round(spriteTop - (stack + CROWN_LIFT + CROWN_ROWS.length) * unit);

    // ASLEEP IS DARK. The crown is drawn in the shadow tone alone while the
    // thing has not woken, so what the player sees across the clearing is the
    // SHAPE of a rank with no light in it — the same sentence the sprite is
    // telling with its shut eyes, said again in the one channel that survives
    // the distance.
    const lit = !target.asleep;
    const [r, g, b] = tone.hunt;
    // It breathes once it is up, at the diamond's own rate, so the two marks
    // pulse together rather than beating against each other.
    const pulse = lit ? 1 + Math.sin(time * PULSE_RATE) * PULSE_DEPTH : 1;
    const fill = lit
      ? `rgba(${r},${g},${b},${Math.min(1, 0.9 * pulse) * seen})`
      : shadow;

    ctx.globalAlpha = lit ? 1 : seen;
    // Bed first, one unit out in every direction, so the mark reads on
    // firelight and on a black field alike — the diamond's own trick.
    stampCrown(ctx, cx, top, unit, 1, shadow);
    stampCrown(ctx, cx, top, unit, 0, fill);
    ctx.globalAlpha = 1;
  }
}

function stampCrown(
  ctx: CanvasRenderingContext2D,
  cx: number,
  top: number,
  unit: number,
  pad: number,
  color: string,
): void {
  ctx.fillStyle = color;
  const rows = CROWN_ROWS.length;
  for (let row = -pad; row < rows + pad; row++) {
    const spans = CROWN_ROWS[Math.min(rows - 1, Math.max(0, row))];
    for (const [from, to] of spans) {
      ctx.fillRect(
        cx + (from - pad) * unit,
        top + row * unit,
        (to - from + 1 + pad * 2) * unit,
        unit,
      );
    }
  }
}

/** Bang pixel with a one-unit dark bed, so it reads on any fill without
 * blotting out the lozenge. */
function stampBang(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  unit: number,
  bed: string,
  color: string,
): void {
  ctx.fillStyle = bed;
  ctx.fillRect(x - unit, y - unit, w + 2 * unit, h + 2 * unit);
  ctx.fillStyle = color;
  ctx.fillRect(x, y, w, h);
}

/** Solid lozenge, optionally grown by `pad` units for the dark bed. */
function stampDiamond(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  unit: number,
  pad: number,
  color: string,
): void {
  ctx.fillStyle = color;
  const last = DIA_ROWS.length - 1;
  for (let row = -pad; row <= last + pad; row++) {
    const src = Math.min(last, Math.max(0, row));
    const hw = DIA_ROWS[src] + pad;
    ctx.fillRect(cx - hw * unit, cy + row * unit, (hw * 2 + 1) * unit, unit);
  }
}

function stampDiamondOutline(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  unit: number,
  color: string,
): void {
  ctx.fillStyle = color;
  const last = DIA_ROWS.length - 1;
  for (let row = 0; row <= last; row++) {
    const hw = DIA_ROWS[row];
    ctx.fillRect(cx - hw * unit, cy + row * unit, unit, unit);
    if (hw > 0) ctx.fillRect(cx + hw * unit, cy + row * unit, unit, unit);
  }
}

/** The palette's three stops, sampled at `t` — noticing, deciding, hunting. */
function mix(
  tone: { notice: Channels; alert: Channels; hunt: Channels },
  t: number,
): Channels {
  const cold = t < 0.5;
  const from = cold ? tone.notice : tone.alert;
  const to = cold ? tone.alert : tone.hunt;
  const local = cold ? t * 2 : (t - 0.5) * 2;
  return [
    Math.round(from[0] + (to[0] - from[0]) * local),
    Math.round(from[1] + (to[1] - from[1]) * local),
    Math.round(from[2] + (to[2] - from[2]) * local),
  ];
}
