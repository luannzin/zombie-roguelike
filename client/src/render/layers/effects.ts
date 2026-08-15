/**
 * Transient combat visuals: footstep dust, tracers, muzzle flashes, impact
 * debris, melee slashes, floating text, and the empty-crate wind puff.
 *
 * Dust draws under entities; the rest draws over them. Floating text is
 * screen-space so it stays legible at any zoom. Wind is world-space after
 * darkness, additive, greyscale — a gust of air, not a player-tinted beam.
 */

import type { Effects, WindPuff, DeathBurst } from '../../game/effects';
import { fadeOf } from '../../lib/math';
import { hudFont } from '../../theme/fonts';
import { palette } from '../../theme/palette';
import type { Projection } from '../projection';
import { effectFrame, effectImage, type VfxSheet } from '../vfx';

/** World space, under entities. */
export function drawDust(ctx: CanvasRenderingContext2D, effects: Effects): void {
  for (const p of effects.dust) {
    const fade = fadeOf(p);
    const t = 1 - fade;
    // Bloom early, shrink late — reads as a puff, not a spark.
    const grow = t < 0.25 ? 0.6 + t * 2.2 : 1.15 - (t - 0.25) * 0.7;
    ctx.globalAlpha = 0.55 * fade * fade;
    ctx.fillStyle = p.color;
    const s = p.size * Math.max(0.35, grow);
    ctx.fillRect(p.x - s / 2, p.y - s / 2, s, s);
  }
  ctx.globalAlpha = 1;
}

/** World space, over entities. */
export function drawCombatEffects(
  ctx: CanvasRenderingContext2D,
  effects: Effects,
  tileSize: number,
): void {
  const fx = palette().effects;

  for (const tracer of effects.tracers) {
    const fade = fadeOf(tracer);
    const ex = tracer.x + tracer.dx * tracer.dist;
    const ey = tracer.y + tracer.dy * tracer.dist;

    // Wide coloured body, then a thin hot core on top.
    strokeLine(
      ctx,
      tracer.x,
      tracer.y,
      ex,
      ey,
      tracer.color,
      tileSize * 0.125 * tracer.width,
      0.35 * fade,
    );
    strokeLine(
      ctx,
      tracer.x,
      tracer.y,
      ex,
      ey,
      fx.tracerCore,
      tileSize * 0.0375 * tracer.width,
      fade,
    );
  }

  for (const flash of effects.flashes) {
    const fade = fadeOf(flash);
    const size = flash.size ?? 1;
    ctx.globalAlpha = fade;
    ctx.fillStyle = fx.muzzleFlash;
    ctx.beginPath();
    ctx.arc(
      flash.x + flash.dx * tileSize * 0.125,
      flash.y + flash.dy * tileSize * 0.125,
      tileSize * (0.14 * fade + 0.05) * size,
      0,
      Math.PI * 2,
    );
    ctx.fill();
  }

  drawSlashes(ctx, effects, tileSize, fx);

  for (const p of effects.particles) {
    const fade = fadeOf(p);
    ctx.globalAlpha = fade;
    ctx.fillStyle = p.color;
    const s = p.size * (0.55 + 0.45 * fade);
    ctx.fillRect(p.x - s / 2, p.y - s / 2, s, s);
  }

  ctx.globalAlpha = 1;
}

/**
 * Claw arcs, drawn perpendicular to the swing so they read as something raking
 * ACROSS the victim rather than a line pointing at them. A landed hit sweeps a
 * thick bright arc; a blocked one is a thin ring — same event, different
 * weight, so a swarm of absorbed swings never looks like a swarm of damage.
 */
function drawSlashes(
  ctx: CanvasRenderingContext2D,
  effects: Effects,
  tileSize: number,
  fx: ReturnType<typeof palette>['effects'],
): void {
  for (const slash of effects.slashes) {
    const fade = fadeOf(slash);
    const t = 1 - fade;
    // Sweep outward from the victim as it fades.
    const radius = tileSize * (slash.blocked ? 0.34 + t * 0.14 : 0.28 + t * 0.4);
    const facing = Math.atan2(slash.dy, slash.dx);
    const half = slash.blocked ? 0.75 : 1.15;
    // Pull the arc's centre back towards the attacker so the sweep passes
    // through the victim instead of hanging in the air behind them.
    const cx = slash.x - slash.dx * radius * 0.6;
    const cy = slash.y - slash.dy * radius * 0.6;

    ctx.globalAlpha = fade * (slash.blocked ? 0.45 : 0.95);
    ctx.strokeStyle = slash.blocked ? fx.slashBlocked : fx.slash;
    ctx.lineWidth = tileSize * (slash.blocked ? 0.05 : 0.11) * (0.5 + fade);
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.arc(cx, cy, radius, facing - half, facing + half);
    ctx.stroke();
  }
  ctx.lineCap = 'butt';
  ctx.globalAlpha = 1;
}

/** Screen space, over everything except the vignette. */
export function drawTextFloats(
  ctx: CanvasRenderingContext2D,
  effects: Effects,
  view: Projection,
): void {
  const fx = palette().effects;
  // hudFont snaps to the 11px grid, so this picks 11 / 22 / 33 — never a size
  // that would land the glyph grid between pixels. No bold: only Regular (400)
  // is loaded, so a bold request would be synthesized and smear the stems.
  ctx.font = hudFont(10 * view.zoom * 0.45);
  ctx.textBaseline = 'middle';

  for (const d of effects.textFloats) {
    ctx.globalAlpha = fadeOf(d);
    const color =
      d.tone === 'gold' ? fx.goldText : d.tone === 'reward' ? fx.rewardText : fx.damageText;
    drawCenteredText(ctx, d.text, view.x(d.x), view.y(d.y), color, fx.textShadow);
  }
  ctx.globalAlpha = 1;
}

function strokeLine(
  ctx: CanvasRenderingContext2D,
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  color: string,
  width: number,
  alpha: number,
): void {
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x1, y1);
  ctx.stroke();
}

/**
 * Centred pixel text with a 1px dark offset behind it, snapped to whole pixels.
 *
 * `textAlign: 'center'` cannot be used here. Departure Mono advances 7px per
 * glyph at 11px, so any odd-length string has an odd total width and the
 * browser would place the glyph origin on a half pixel — which antialiases the
 * stems and reads as a shimmer. Measuring and rounding the LEFT origin keeps
 * every string on the pixel grid regardless of its length.
 *
 * Callers must not set `ctx.textAlign`; this owns it.
 */
export function drawCenteredText(
  ctx: CanvasRenderingContext2D,
  text: string,
  centerX: number,
  y: number,
  color: string,
  shadow: string,
): void {
  ctx.textAlign = 'left';
  const left = Math.round(centerX - ctx.measureText(text).width / 2);
  const top = Math.round(y);

  ctx.fillStyle = shadow;
  ctx.fillText(text, left + 1, top + 1);
  ctx.fillStyle = color;
  ctx.fillText(text, left, top);
}

/**
 * One-shot gust when a crate broke empty. World pixels, after darkness,
 * additive, no player tint — the sheet is already the colour of air.
 */
export function drawWindPuffs(
  ctx: CanvasRenderingContext2D,
  sheet: VfxSheet | null,
  winds: WindPuff[],
): void {
  if (!sheet || winds.length === 0) return;
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  for (const puff of winds) {
    const fade = fadeOf(puff);
    const frame = effectFrame(sheet, puff.age);
    ctx.globalAlpha = 0.85 * fade;
    ctx.drawImage(
      sheet.image,
      frame * sheet.frameWidth,
      0,
      sheet.frameWidth,
      sheet.frameHeight,
      Math.round(puff.x - sheet.frameWidth / 2),
      Math.round(puff.y - sheet.anchorY),
      sheet.frameWidth,
      sheet.frameHeight,
    );
  }
  ctx.restore();
}

/**
 * A body hitting the floor. World pixels, after darkness, additive, tinted
 * with blood — the sheet is greyscale the way kindle is, and the hue is the
 * same blood the spray already uses.
 */
export function drawDeathBursts(
  ctx: CanvasRenderingContext2D,
  sheet: VfxSheet | null,
  deaths: DeathBurst[],
): void {
  if (!sheet || deaths.length === 0) return;
  const tint = palette().effects.blood[3] ?? palette().effects.hitCore;
  const image = effectImage(sheet, tint);
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  for (const burst of deaths) {
    const fade = fadeOf(burst);
    const frame = effectFrame(sheet, burst.age);
    ctx.globalAlpha = 0.95 * fade;
    ctx.drawImage(
      image,
      frame * sheet.frameWidth,
      0,
      sheet.frameWidth,
      sheet.frameHeight,
      Math.round(burst.x - sheet.frameWidth / 2),
      Math.round(burst.y - sheet.anchorY),
      sheet.frameWidth,
      sheet.frameHeight,
    );
  }
  ctx.restore();
}
