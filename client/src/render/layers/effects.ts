/**
 * Transient combat visuals: footstep dust, tracers, muzzle flashes, impact
 * debris, blade paths, enemy claw arcs, floating text, and the empty-crate
 * wind puff.
 *
 * The two melee shapes are drawn by two functions and they are not the same
 * effect wearing different colours — see `drawSwings` and `drawSlashes`.
 *
 * Dust draws under entities; the rest draws over them. Floating text is
 * screen-space so it stays legible at any zoom. Wind and the death puff are
 * world-space after darkness, additive, greyscale — air leaving the ground,
 * not a player-tinted beam.
 */

import type { Effects, WindPuff, DeathBurst } from '../../game/effects';
import { fadeOf } from '../../lib/math';
import { hudFont } from '../../theme/fonts';
import { palette } from '../../theme/palette';
import type { Projection } from '../projection';
import { effectFrame, type VfxSheet } from '../vfx';
import {
  drawOriented,
  sheetLife,
  weaponFrame,
  type WeaponVfxAtlas,
  type WeaponVfxSheet,
} from '../weapon-vfx';

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

/**
 * World space, over entities.
 *
 * `weapons` is the oriented fire atlas (`render/weapon-vfx.ts`). It is
 * optional and null-safe on purpose: assets load asynchronously and may not
 * be built at all, and the game has to keep drawing shots either way — so
 * every sprite path below has the canvas primitive it replaced sitting next
 * to it as a fallback.
 */
export function drawCombatEffects(
  ctx: CanvasRenderingContext2D,
  effects: Effects,
  tileSize: number,
  weapons: WeaponVfxAtlas | null = null,
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

  drawMuzzles(ctx, effects, tileSize, fx, weapons);
  drawBursts(ctx, effects, tileSize, weapons);
  drawSwings(ctx, effects, tileSize, fx);
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
 * Fire at the barrel — one per trigger pull.
 *
 * ADDITIVE, because it is a light rather than paint: the whole reason this
 * layer runs after the darkness pass is that a muzzle flash should brighten
 * the ground it is standing on instead of being dimmed by the night it is
 * lighting up. `lighter` is also what lets the sheet's dark red outer step
 * disappear against the forest and its white core blow out, which is the
 * effect doing its own tone mapping.
 *
 * The ART owns the timing. Each sheet is played once from `age` and simply
 * stops when its frames run out; the list entry lives a little longer (see
 * `Flash.life`) so nothing is swept away mid-animation. Nothing here needs
 * to know how many frames a flash has.
 */
function drawMuzzles(
  ctx: CanvasRenderingContext2D,
  effects: Effects,
  tileSize: number,
  fx: ReturnType<typeof palette>['effects'],
  weapons: WeaponVfxAtlas | null,
): void {
  if (effects.flashes.length === 0) return;
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  for (const flash of effects.flashes) {
    const sheet: WeaponVfxSheet | null | undefined =
      flash.kind === 'blast' ? weapons?.blast : weapons?.muzzle;
    if (sheet) {
      if (flash.age >= sheetLife(sheet)) continue;
      // Scaled about the barrel by the weapon's own `flash`, and by the
      // world's tile size against the tile the art was authored at, so the
      // fire stays the same physical size if the game is ever rescaled.
      const scale = (flash.size ?? 1) * (tileSize / (weapons?.tile || 16));
      drawOriented(ctx, sheet, flash.x, flash.y, flash.dx, flash.dy, flash.age, 1, scale);
      continue;
    }
    // No atlas: the circle this replaced, on its original short clock.
    const fade = Math.max(0, 1 - flash.age / 0.07);
    if (fade <= 0) continue;
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
  ctx.restore();
  ctx.globalAlpha = 1;
}

/**
 * A round arriving: a star at the point of contact, additive like the muzzle.
 *
 * Un-rotated. An impact has no facing — the direction of the shot is carried
 * by the debris `spawnImpact` kicks back along the ray, and spinning a
 * symmetric burst to match would be work nobody can see.
 */
function drawBursts(
  ctx: CanvasRenderingContext2D,
  effects: Effects,
  tileSize: number,
  weapons: WeaponVfxAtlas | null,
): void {
  if (effects.bursts.length === 0) return;
  const sheet = weapons?.impact;
  // Without the atlas there is nothing to draw: the debris and the core
  // spark from `spawnImpact` already carried this event on their own, and a
  // circle here would be a second, worse version of the burst rather than a
  // fallback for it.
  if (!sheet) return;
  const life = sheetLife(sheet);
  const unit = tileSize / (weapons?.tile || 16);
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  for (const burst of effects.bursts) {
    if (burst.age >= life) continue;
    const frame = weaponFrame(sheet, burst.age);
    const scale = burst.size * unit;
    const w = sheet.frameWidth * scale;
    const h = sheet.frameHeight * scale;
    ctx.drawImage(
      sheet.image,
      frame * sheet.frameWidth,
      0,
      sheet.frameWidth,
      sheet.frameHeight,
      burst.x - sheet.anchorX * scale,
      burst.y - sheet.anchorY * scale,
      w,
      h,
    );
  }
  ctx.restore();
  ctx.globalAlpha = 1;
}

/**
 * The player's blade: a white path swept out of the body, at speed.
 *
 * It is a PATH and not an arc, and that distinction is the effect. A static
 * arc that fades is a decal — it says a swing happened somewhere near here.
 * What is drawn instead is where the edge IS at this instant, with a tail
 * behind it: the stroke starts at one lip of the cone, races round to the
 * other in the first two thirds of the effect's life, and the tail catches up
 * and closes over the last third. Watched at 60 Hz that reads as a blade
 * travelling, which is the thing the player is actually doing.
 *
 * Three strokes on the same wedge, widest first:
 *
 *   glow   a wide soft band, only on the cut — the finisher throws light and
 *          the two slashes do not, which is what separates them at a glance
 *   body   the tail: the part of the path already travelled, fading behind
 *   core   the leading edge, one third the width and pure white
 *
 * The radius grows a little over the life so the path opens away from the
 * body rather than orbiting it, and `sweep` flips the direction of travel so
 * two consecutive slashes cross into an X instead of repeating.
 *
 * Nothing here knows whether the swing hit anything: `landed` only thickens
 * it. Blood, numbers and wounds are the victim's business and are drawn on
 * the victim.
 */
function drawSwings(
  ctx: CanvasRenderingContext2D,
  effects: Effects,
  tileSize: number,
  fx: ReturnType<typeof palette>['effects'],
): void {
  if (effects.swings.length === 0) return;
  ctx.lineCap = 'round';

  for (const swing of effects.swings) {
    const fade = fadeOf(swing);
    const t = 1 - fade;
    const facing = Math.atan2(swing.dy, swing.dx);
    const half = swing.arc * 0.5;

    // Where the edge is now, and how much path is behind it. `travel` eases
    // out so the swing decelerates into its follow-through instead of
    // stopping dead; `tail` shrinks at the end so the stroke closes rather
    // than fading as a full-length band.
    const travel = 1 - (1 - Math.min(1, t / 0.66)) ** 2;
    const tail = Math.min(travel, t < 0.66 ? 0.55 : 0.55 * (1 - (t - 0.66) / 0.34));
    if (tail <= 0.001) continue;

    const lead = -half + swing.arc * travel;
    const back = lead - swing.arc * tail;
    // Screen angles run the other way when the swing is thrown left-handed.
    const from = facing + (swing.sweep > 0 ? back : -back);
    const to = facing + (swing.sweep > 0 ? lead : -lead);
    const counter = swing.sweep <= 0;

    const radius = swing.reach * (0.62 + 0.34 * t);
    const weight = (swing.landed ? 1 : 0.72) * (swing.cut ? 1.5 : 1);

    if (swing.cut) {
      stroke(ctx, swing.x, swing.y, radius, from, to, counter, fx.bladeGlow,
        tileSize * 0.2 * weight, 0.22 * fade);
    }
    stroke(ctx, swing.x, swing.y, radius, from, to, counter, fx.blade,
      tileSize * 0.085 * weight, 0.7 * fade);
    // The core is drawn on the leading QUARTER of the path only: white all
    // the way along would be a ribbon, and a blade is bright where the metal
    // is and dim where the air it left is.
    const coreFrom = to - (to - from) * 0.28;
    stroke(ctx, swing.x, swing.y, radius, coreFrom, to, counter, fx.bladeCore,
      tileSize * 0.03 * weight, fade);
  }

  ctx.lineCap = 'butt';
  ctx.globalAlpha = 1;
}

function stroke(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  radius: number,
  from: number,
  to: number,
  counter: boolean,
  color: string,
  width: number,
  alpha: number,
): void {
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.beginPath();
  ctx.arc(cx, cy, radius, from, to, counter);
  ctx.stroke();
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
      d.tone === 'darkGold'
        ? fx.darkGoldText
        : d.tone === 'reward'
          ? fx.rewardText
          : fx.damageText;
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
 * Dirt and air kicked when a body hits the floor. World pixels, after
 * darkness, additive, greyscale — the same family as the empty-crate gust,
 * not a blood tint. The hue of dirt is the dust particles under the body.
 */
export function drawDeathBursts(
  ctx: CanvasRenderingContext2D,
  sheet: VfxSheet | null,
  deaths: DeathBurst[],
): void {
  if (!sheet || deaths.length === 0) return;
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  for (const burst of deaths) {
    const fade = fadeOf(burst);
    const frame = effectFrame(sheet, burst.age);
    ctx.globalAlpha = 0.8 * fade;
    ctx.drawImage(
      sheet.image,
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
