/**
 * Enemy hunt tell: a small diamond over the head that fills as the creature
 * notices you, and the mark inside it.
 *
 * There is no floor cone. The diamond IS the feedback:
 *
 *   idle          nothing at all
 *   noticing      empty diamond, a sliver of fill at the bottom
 *   working you   fill climbs
 *   hunting       full, and it stays that way
 *
 * Hidden while idle. Drawn OVER the darkness and not scaled by visibility:
 * a hunter in the dark still wears the tell, so killing the lamp does not
 * hide that it has you. The body itself still vanishes; only this mark
 * remains. Painted as world-pixel rectangles, not as type — it lives in
 * the forest, not on the HUD.
 */

import { clamp01 } from '../../lib/math';
import { palette, type Channels } from '../../theme/palette';
import type { EntityContext } from './entities';
import type { DrawableEntity } from '../types';

/**
 * Awareness at which the diamond appears. Below this the creature is
 * wandering and the woods stay quiet.
 */
const NOTICE_AT = 0.05;
/** Awareness at or above which an enemy is hunting, and the diamond is full. */
const ALERT_AT = 0.999;

/**
 * The diamond, in WORLD pixels of the art's own grid (1 unit = tileSize/16).
 * Half-widths per row from the top: a 5-wide, 7-tall lozenge.
 */
const DIA_ROWS = [0, 1, 2, 2, 2, 1, 0] as const;
/** How far above the top of the sprite it floats, same units. */
const DIA_LIFT = 3;

/** The bang inside: a two-tall bar, a one-tall gap, a one-tall dot. */
const BANG_W = 1;
const BANG_BAR = 2;
const BANG_GAP = 1;

/** Committed diamonds breathe. Depth and rate of that pulse. */
const PULSE_DEPTH = 0.14;
const PULSE_RATE = 7;

/**
 * The hunt diamond over every enemy that has started to notice the party.
 *
 * WORLD space, drawn AFTER the darkness pass on purpose: this is the one
 * tell that must survive the lamp going out. A mark swallowed by the night
 * would hide the very fact the player needs — that the thing has them.
 */
export function drawAlertMarks(
  entity: EntityContext,
  entities: readonly DrawableEntity[],
  time: number,
): void {
  const { ctx, config, book } = entity;
  const tone = palette().enemyView;
  const shadow = palette().entity.labelShadow;
  const unit = config.tileSize / 16;
  const rows = DIA_ROWS.length;
  const mid = (rows - 1) / 2;

  for (const target of entities) {
    if (target.kind !== 'enemy' || !target.alive) continue;
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
