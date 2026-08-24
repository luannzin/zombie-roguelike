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

import type { Effects, WindPuff, DeathBurst, LevelUp } from '../../game/effects';
import type { DrawableSpit, DrawableVolley } from '../types';
import { fadeOf } from '../../lib/math';
import { hudFont } from '../../theme/fonts';
import { palette } from '../../theme/palette';
import type { Projection } from '../projection';
import { effectFrame, effectImage, type VfxSheet } from '../vfx';
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
/**
 * Creature projectiles in the air.
 *
 * OVER EVERYTHING, and that is the one decision here. A disc is the only thing
 * on screen the player must never lose behind a tree or a shoulder, because
 * losing it is taking the hit — so it is drawn after the depth sort rather
 * than inside it, exactly like a health bar.
 *
 * IT IS DRAWN AS A COMET, not a ball. A circle in flight has no direction in
 * it, and direction is the whole of what the player has to read: a disc coming
 * AT you and one crossing in front of you demand completely different
 * responses, and at this size a trail is the only thing that tells them apart.
 * The tail runs backwards along the velocity, so it is the flight path itself
 * rather than a decoration pointing somewhere plausible.
 *
 * `lighter`, so it survives the darkness pass — a projectile that dimmed with
 * the forest would be invisible in exactly the conditions it is thrown in.
 */
export function drawSpits(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  spits: DrawableSpit[],
): void {
  if (spits.length === 0) return;
  const tone = palette().spit;
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  for (const spit of spits) {
    const x = view.x(spit.x);
    const y = view.y(spit.y);
    const r = Math.max(1.5, spit.radius * view.zoom);
    const speed = Math.hypot(spit.dx, spit.dy) || 1;
    // A tail proportional to the disc rather than to the speed: the speed is
    // a constant per creature, and a trail that grew with it would be a
    // second, quieter way of saying the same thing.
    const tail = r * 3.4;
    const bx = x - (spit.dx / speed) * tail;
    const by = y - (spit.dy / speed) * tail;

    const trail = ctx.createLinearGradient(bx, by, x, y);
    trail.addColorStop(0, 'rgb(0 0 0 / 0)');
    trail.addColorStop(1, tone);
    ctx.globalAlpha = 0.5;
    ctx.strokeStyle = trail;
    ctx.lineWidth = r * 1.1;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(bx, by);
    ctx.lineTo(x, y);
    ctx.stroke();

    // The head: a hot core inside a soft halo, so it reads at one pixel and
    // still has a size at ten.
    ctx.globalAlpha = 0.55;
    const glow = ctx.createRadialGradient(x, y, 0, x, y, r * 2.2);
    glow.addColorStop(0, tone);
    glow.addColorStop(1, 'rgb(0 0 0 / 0)');
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(x, y, r * 2.2, 0, Math.PI * 2);
    ctx.fill();

    ctx.globalAlpha = 1;
    ctx.fillStyle = tone;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
  ctx.globalAlpha = 1;
}

/**
 * WHAT AN ULTIMATE PUT IN THE AIR. The crescent, and whatever throws one next.
 *
 * DRAWN AS AN ARC AND NOT AS A DISC, which is the whole separation from
 * `drawSpits` above. They are one mechanic on the server and they must never
 * be one picture: a spit is a small wet ball coming at you and this is a
 * BLADE'S WIDTH of steel crossing the clearing, and the thing the player has
 * to read off it in a quarter of a second is HOW WIDE IT IS — because that is
 * exactly the question "is it going to catch the thing next to me" asks.
 *
 * So the shape is the arc's own sweep, perpendicular to travel, at the radius
 * the catalog row actually bills at. It is not decoration sized to look
 * dramatic: draw it narrower than it hits and the player learns a lie about a
 * weapon they only get to use once a fight.
 *
 * THREE PASSES, cheapest last:
 *
 *   1. the WAKE — a fan of the same arc, a few frames behind, fading. An arc
 *      with no wake reads as a stationary crescent that teleports;
 *   2. the EDGE — the arc itself, thick and hot;
 *   3. the TIPS — a bright cap at each end, because an arc that fades out at
 *      its ends has no length, and length is what says "this is wide".
 *
 * `lighter` for the same reason the spits use it: an ultimate that dimmed with
 * the forest would be invisible in the dark it is thrown in.
 */
export function drawVolleys(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  volleys: DrawableVolley[],
): void {
  if (volleys.length === 0) return;
  const tone = palette().ultimate.arc;
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  ctx.lineCap = 'round';
  for (const shot of volleys) {
    const speed = Math.hypot(shot.dx, shot.dy) || 1;
    const ux = shot.dx / speed;
    const uy = shot.dy / speed;
    const heading = Math.atan2(uy, ux);
    const r = Math.max(3, shot.radius * view.zoom);
    // A HALF-DISC OPENING FORWARD. Ninety degrees each side of the heading is
    // the widest an arc can be drawn and still read as pointing somewhere —
    // past that it closes into a ring, and a ring is a shockwave.
    const half = Math.PI * 0.46;

    // 1. THE WAKE. Four ghosts along the travel line, each one a step back and
    // a step dimmer. Spacing is in RADII rather than in pixels so a wider arc
    // leaves a longer wake without a second number to tune.
    for (let i = 4; i >= 1; i -= 1) {
      const back = r * 0.55 * i;
      const gx = view.x(shot.x) - ux * back;
      const gy = view.y(shot.y) - uy * back;
      ctx.globalAlpha = 0.09 * (5 - i);
      ctx.strokeStyle = tone;
      ctx.lineWidth = Math.max(1, r * 0.22);
      ctx.beginPath();
      ctx.arc(gx, gy, r, heading - half, heading + half);
      ctx.stroke();
    }

    const x = view.x(shot.x);
    const y = view.y(shot.y);

    // 2. THE EDGE.
    ctx.globalAlpha = 0.95;
    ctx.strokeStyle = tone;
    ctx.lineWidth = Math.max(2, r * 0.34);
    ctx.beginPath();
    ctx.arc(x, y, r, heading - half, heading + half);
    ctx.stroke();

    // 3. THE TIPS.
    ctx.globalAlpha = 0.8;
    ctx.fillStyle = tone;
    for (const sign of [-1, 1]) {
      const a = heading + half * sign;
      ctx.beginPath();
      ctx.arc(x + Math.cos(a) * r, y + Math.sin(a) * r, Math.max(1.5, r * 0.2), 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.restore();
  ctx.globalAlpha = 1;
}

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
        : d.tone === 'heal'
          ? // The kit's own hue, the same one the ring over the head runs in,
            // so the number and the ring are visibly the same event.
            palette().heal
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

/**
 * A level arriving on the player who earned it: the summon column, in the
 * summon's own cold light.
 *
 * TINTED RATHER THAN GREYSCALE, unlike the gust and the death puff either
 * side of it. Those are AIR — dirt and pressure, which have no colour of
 * their own and take the scene's. This is the same beam that delivers a body
 * into the lobby, and that beam has always been light with a hue; drawn grey
 * in the middle of a forest it would read as one more puff of dust on a
 * player who just did the most important thing they will do all night.
 */
export function drawLevelUps(
  ctx: CanvasRenderingContext2D,
  sheet: VfxSheet | null,
  levelUps: LevelUp[],
): void {
  if (!sheet || levelUps.length === 0) return;
  const image = effectImage(sheet, palette().summon.spark);
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  for (const up of levelUps) {
    const frame = effectFrame(sheet, up.age);
    ctx.globalAlpha = 0.9 * fadeOf(up);
    ctx.drawImage(
      image,
      frame * sheet.frameWidth,
      0,
      sheet.frameWidth,
      sheet.frameHeight,
      Math.round(up.x - sheet.frameWidth / 2),
      Math.round(up.y - sheet.anchorY),
      sheet.frameWidth,
      sheet.frameHeight,
    );
  }
  ctx.restore();
}
