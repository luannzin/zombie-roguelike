/**
 * Transient combat visuals: footstep dust, tracers, muzzle flashes, impact
 * debris and floating damage numbers.
 *
 * Dust draws under entities; the rest draws over them. Damage numbers are
 * screen-space so they stay legible at any zoom.
 */

import type { Effects } from '../../game/effects';
import { fadeOf } from '../../lib/math';
import { hudFont } from '../../theme/fonts';
import { palette } from '../../theme/palette';
import type { Projection } from '../projection';

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
    strokeLine(ctx, tracer.x, tracer.y, ex, ey, tracer.color, tileSize * 0.125, 0.35 * fade);
    strokeLine(ctx, tracer.x, tracer.y, ex, ey, fx.tracerCore, tileSize * 0.0375, fade);
  }

  for (const flash of effects.flashes) {
    const fade = fadeOf(flash);
    ctx.globalAlpha = fade;
    ctx.fillStyle = fx.muzzleFlash;
    ctx.beginPath();
    ctx.arc(
      flash.x + flash.dx * tileSize * 0.125,
      flash.y + flash.dy * tileSize * 0.125,
      tileSize * (0.14 * fade + 0.05),
      0,
      Math.PI * 2,
    );
    ctx.fill();
  }

  for (const p of effects.particles) {
    const fade = fadeOf(p);
    ctx.globalAlpha = fade;
    ctx.fillStyle = p.color;
    const s = p.size * (0.55 + 0.45 * fade);
    ctx.fillRect(p.x - s / 2, p.y - s / 2, s, s);
  }

  ctx.globalAlpha = 1;
}

/** Screen space, over everything except the vignette. */
export function drawDamageFloats(
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

  for (const d of effects.damageFloats) {
    ctx.globalAlpha = fadeOf(d);
    drawCenteredText(ctx, String(d.value), view.x(d.x), view.y(d.y), fx.damageText, fx.textShadow);
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
