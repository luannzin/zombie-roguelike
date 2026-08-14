/**
 * Enemy senses, drawn: the sight cone on the ground and the mark over the head
 * of whatever has committed to you.
 *
 * The cone is the SAME wedge the server tests against — reach and width come
 * from the creature's stat block in `welcome.config.enemyTypes`, pointed along
 * the facing the snapshot carries. Nothing here is decorative geometry; if this
 * drifted from `ai.look` the game would be teaching a rule it does not enforce.
 *
 * `awareness` — the server's detection meter — is the only thing driving it:
 *
 *   0.0   nothing at all              it is wandering; the woods stay dark
 *   0.1   a short yellow sliver       it caught something
 *   0.5   amber, longer, brighter     it is working you out
 *   1.0   red, full reach, pulsing    it has you, and it is marked
 *
 * The cone is a REACTION, not furniture. Drawing one over every idle creature
 * would turn the dark into a diagram and leave nothing to be afraid of; this
 * way the first sliver of yellow in the trees is information the player earned
 * and has about two seconds to act on.
 *
 * It grows to the reach the server enforces and never past it. Under-drawing
 * while a creature is merely suspicious errs toward danger; a cone longer than
 * the rule would promise safety that is not there. The other thing that moves
 * the reach is the LANTERN, and it moves it a long way — see below.
 *
 * That ramp is the entire stealth read, so it is drawn on the FLOOR rather than
 * as an overlay: it is occluded by the same darkness pass as everything else,
 * which means a cone reaching into the dark fades out exactly where the enemy's
 * own sight does not — the tell and the world agree.
 *
 * A cone is only ever drawn for an enemy the team can already SEE (`visibility`
 * scales it to nothing otherwise). Painting the cone of something hidden in the
 * dark would hand the player a sonar and undo the lantern. The alert mark obeys
 * the same rule twice over: it is scaled by `visibility` AND drawn under the
 * darkness, so a hunter at the edge of the light wears a mark that is as hard
 * to make out as it is.
 *
 * The reach it draws is the reach against the LOCAL player, which depends on
 * their own lamp (see `Game.sightReach`). Switching the lantern on visibly
 * stretches every cone on screen toward you. That is the whole point of the
 * layer: the cost of seeing is being seen, and it is drawn, not explained.
 */

import { clamp01 } from '../../lib/math';
import { palette, type Channels } from '../../theme/palette';
import type { EntityContext } from './entities';
import type { DrawableEntity } from '../types';

/** Fill alpha of a fully committed cone. Low: this lies over terrain. */
const FILL_ALPHA = 0.2;
/** The arc's outline, as a multiple of the fill. It is what gives it an edge. */
const EDGE_ALPHA = 2.4;
/**
 * Awareness at which the cone appears at all, and how much of its weight and
 * reach it has on that first frame.
 *
 * Below the threshold there is NO cone. An idle forest full of drawn wedges is
 * a map screen: it turns the dark into a diagram and there is nothing left to
 * be afraid of. The cone is a reaction — it exists because something is
 * happening — so it opens up out of nothing the moment a creature catches
 * movement and grows to its full reach as that hardens into a hunt.
 */
const NOTICE_AT = 0.05;
const NOTICE_ALPHA = 0.45;
const NOTICE_REACH = 0.4;
/** Fraction of the reach that stays at full fill before it fades out. */
const CORE = 0.35;
/** Committed cones breathe. Depth and rate of that pulse. */
const PULSE_DEPTH = 0.18;
const PULSE_RATE = 7;
/** Awareness at or above which an enemy is hunting, and wears the mark. */
const ALERT_AT = 0.999;

/**
 * The alert mark, in WORLD pixels of the art's own grid (1 unit = tileSize/16).
 * A 2x8 exclamation: a five-tall bar, a one-tall gap, a two-tall dot.
 */
const MARK_W = 2;
const MARK_H = 8;
/** How far above the top of the sprite it floats, same units. */
const MARK_LIFT = 5;
/** Bob amplitude and rate, so it reads as an alarm rather than as a label. */
const MARK_BOB = 1.5;
const MARK_BOB_RATE = 9;

/**
 * Sight cones for every entity that has one. WORLD space, before the darkness
 * pass — see the header for why that ordering is the point.
 */
export function drawVisionCones(
  ctx: CanvasRenderingContext2D,
  entities: readonly DrawableEntity[],
  time: number,
  zoom: number,
): void {
  const tone = palette().enemyView;
  // World space is scaled by `zoom`, so a width of 1 here would be a four pixel
  // rope around a shape that is meant to be a hint.
  const hairline = 1 / Math.max(1, zoom);

  for (const target of entities) {
    if (target.viewRange <= 0 || !target.alive) continue;
    // Hidden in the dark means hidden: no cone either.
    const seen = target.visibility;
    if (seen <= 0.01) continue;

    const awareness = clamp01(target.awareness);
    // Nothing has noticed anything: no cone. See NOTICE_AT.
    if (awareness < NOTICE_AT) continue;
    // Re-based so the first visible frame is the bottom of the ramp rather
    // than 5% up it — the cone has to open from nothing, not pop in.
    const ramp = (awareness - NOTICE_AT) / (1 - NOTICE_AT);

    // Committed cones breathe; the rest hold still, or a clearing full of
    // half-interested zombies would shimmer.
    const pulse =
      awareness >= ALERT_AT ? 1 + Math.sin(time * PULSE_RATE) * PULSE_DEPTH : 1;
    const alpha = FILL_ALPHA * (NOTICE_ALPHA + (1 - NOTICE_ALPHA) * ramp) * seen * pulse;
    if (alpha <= 0.002) continue;

    // Grows to — and never past — the reach the server enforces. Under-drawing
    // while it is only suspicious is honest in the safe direction; a cone
    // longer than the rule would promise safety that is not there.
    const reach = target.viewRange * (NOTICE_REACH + (1 - NOTICE_REACH) * ramp);
    const half = (target.viewDegrees * Math.PI) / 360;
    const facing = Math.atan2(target.ay, target.ax);
    // The cone leaves the body at ground level, not from the box centre: it is
    // a shape lying on the floor, and starting it at the waist would make a
    // creature look like it was seeing out of its chest.
    const ox = target.x;
    const oy = target.y + target.halfHeight;
    const [r, g, b] = mix(tone, ramp);

    const fade = ctx.createRadialGradient(ox, oy, reach * CORE, ox, oy, reach);
    fade.addColorStop(0, `rgba(${r},${g},${b},${alpha})`);
    fade.addColorStop(1, `rgba(${r},${g},${b},0)`);

    ctx.beginPath();
    ctx.moveTo(ox, oy);
    ctx.arc(ox, oy, reach, facing - half, facing + half);
    ctx.closePath();
    ctx.fillStyle = fade;
    ctx.fill();

    // A hairline along the far arc only. Stroking the whole wedge would draw
    // two spokes back to the body and read as a radar sweep.
    ctx.beginPath();
    ctx.arc(ox, oy, reach, facing - half, facing + half);
    ctx.strokeStyle = `rgba(${r},${g},${b},${Math.min(0.5, alpha * EDGE_ALPHA)})`;
    ctx.lineWidth = hairline;
    ctx.stroke();
  }
}

/**
 * The mark over a hunter's head.
 *
 * WORLD space, drawn before the darkness pass, for the same reason the cone is:
 * it is a thing standing in the forest, and it has to be swallowed by the night
 * exactly as hard as the creature wearing it. Painted as a label over the
 * darkness it would be a bright red glyph floating above a zombie you cannot
 * see — a free tracker, and the opposite of what the dark is for.
 *
 * Drawn as rectangles on the world pixel grid rather than as type, so it stays
 * pixel art at any zoom: a bar, a gap, a dot, on a one-pixel dark bed.
 */
export function drawAlertMarks(
  entity: EntityContext,
  entities: readonly DrawableEntity[],
  time: number,
): void {
  const { ctx, config, book } = entity;
  const tone = palette().enemyView;
  const shadow = palette().entity.labelShadow;
  // The art's own pixel. Everything below is a whole multiple of it.
  const unit = config.tileSize / 16;

  for (const target of entities) {
    if (target.viewRange <= 0 || !target.alive) continue;
    if (target.awareness < ALERT_AT || target.visibility <= 0.01) continue;

    const frameHeight = book.get(target.sheet)?.frameHeight ?? config.spriteHeight;
    // Same anchor the name labels use: the top of the sprite, whatever its
    // height, so a taller creature wears it on its own head.
    const spriteTop = target.y + target.recoilY + target.halfHeight - frameHeight;
    const bob = Math.round(Math.sin(time * MARK_BOB_RATE) * MARK_BOB) * unit;
    const x = Math.round(target.x + target.recoilX - unit);
    const top = spriteTop - MARK_LIFT * unit + bob;

    ctx.globalAlpha = target.visibility;
    // Bed first: over a pale sprite or a lit trunk the mark needs its own
    // ground to sit on, or it disappears into whatever is behind it.
    ctx.fillStyle = shadow;
    ctx.fillRect(x - unit, top - unit, MARK_W * unit + 2 * unit, MARK_H * unit + 2 * unit);
    ctx.fillStyle = tone.mark;
    ctx.fillRect(x, top, MARK_W * unit, (MARK_H - 3) * unit);
    ctx.fillRect(x, top + (MARK_H - 2) * unit, MARK_W * unit, 2 * unit);
  }
  ctx.globalAlpha = 1;
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
