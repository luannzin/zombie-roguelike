/**
 * Enemy senses, drawn: the sight cone on the ground and the mark over the head
 * of whatever has committed to you.
 *
 * The cone is the SAME wedge the server tests against — reach and width come
 * from the creature's stat block in `welcome.config.enemyTypes`, pointed along
 * the facing the snapshot carries. Nothing here is decorative geometry; if this
 * drifted from `ai.look` the game would be teaching a rule it does not enforce.
 *
 * One number drives all of it. `awareness` is the server's detection meter, and
 * it reads on the ground as a wedge that warms and reaches further as the thing
 * inside it works you out:
 *
 *   0.0   bone white, short, barely there    it is looking, not at you
 *   0.5   amber, longer, brighter            it has something and is deciding
 *   1.0   red, full reach, pulsing           it has you
 *
 * That ramp is the entire stealth read, so it is drawn on the FLOOR rather than
 * as an overlay: it is occluded by the same darkness pass as everything else,
 * which means a cone reaching into the dark fades out exactly where the enemy's
 * own sight does not — the tell and the world agree.
 *
 * A cone is only ever drawn for an enemy the team can already SEE (`visibility`
 * scales it to nothing otherwise). Painting the cone of something hidden in the
 * dark would hand the player a sonar and undo the lantern.
 */

import { clamp01 } from '../../lib/math';
import { HUD_GRID, hudFont } from '../../theme/fonts';
import { palette, type Channels } from '../../theme/palette';
import type { EntityContext } from './entities';
import { drawCenteredText } from './effects';
import type { DrawableEntity } from '../types';

/** Fill alpha at the tip of a fully alerted cone. Low: this lies over terrain. */
const FILL_ALPHA = 0.17;
/** The arc's outline, as a multiple of the fill. It is what gives it an edge. */
const EDGE_ALPHA = 2.4;
/** How much of the cone's alpha survives at rest. A calm cone is a whisper. */
const CALM_ALPHA = 0.4;
/** Extra reach at full awareness, as a fraction of the type's range. */
const GROWTH = 0.3;
/** Fraction of the reach that stays at full fill before it fades out. */
const CORE = 0.35;
/** Committed cones breathe. Depth and rate of that pulse. */
const PULSE_DEPTH = 0.18;
const PULSE_RATE = 7;
/** Awareness at or above which an enemy is hunting, and wears the mark. */
const ALERT_AT = 0.999;

/** Alert glyph size and how far above the sprite it floats, in screen px. */
const MARK_PX = HUD_GRID;
const MARK_LIFT = 6;
/** Bob amplitude and rate of the mark, so it reads as an alarm not a label. */
const MARK_BOB = 2.5;
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
    // Committed cones breathe; calm ones hold still, or every quiet corner of
    // the forest would shimmer.
    const pulse =
      awareness >= ALERT_AT ? 1 + Math.sin(time * PULSE_RATE) * PULSE_DEPTH : 1;
    const alpha = FILL_ALPHA * (CALM_ALPHA + (1 - CALM_ALPHA) * awareness) * seen * pulse;
    if (alpha <= 0.002) continue;

    const reach = target.viewRange * (1 + GROWTH * awareness);
    const half = (target.viewDegrees * Math.PI) / 360;
    const facing = Math.atan2(target.ay, target.ax);
    // The cone leaves the body at ground level, not from the box centre: it is
    // a shape lying on the floor, and starting it at the waist would make a
    // creature look like it was seeing out of its chest.
    const ox = target.x;
    const oy = target.y + target.halfHeight;
    const [r, g, b] = mix(tone, awareness);

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
 * The mark over a hunter's head. SCREEN space, with the name labels, because it
 * is a glyph on the font's pixel grid rather than a thing in the world — and
 * because it has to survive the darkness pass that just dimmed the cone.
 */
export function drawAlertMarks(
  entity: EntityContext,
  entities: readonly DrawableEntity[],
  time: number,
): void {
  const { ctx, view, config, book } = entity;
  const mark = palette().enemyView.mark;
  const shadow = palette().entity.labelShadow;

  ctx.font = hudFont(MARK_PX);
  ctx.textBaseline = 'bottom';

  for (const target of entities) {
    if (target.viewRange <= 0 || !target.alive) continue;
    if (target.awareness < ALERT_AT || target.visibility <= 0.01) continue;

    const frameHeight = book.get(target.sheet)?.frameHeight ?? config.spriteHeight;
    // Same anchor the name labels use: the top of the sprite, whatever its
    // height, so a taller creature wears it on its own head.
    const spriteTop = target.y + target.recoilY + target.halfHeight - frameHeight;
    const bob = Math.sin(time * MARK_BOB_RATE) * MARK_BOB;

    ctx.globalAlpha = target.visibility;
    drawCenteredText(
      ctx,
      '!',
      view.x(target.x + target.recoilX),
      view.y(spriteTop) - MARK_LIFT + bob,
      mark,
      shadow,
    );
  }
  ctx.globalAlpha = 1;
}

/** The palette's three stops, sampled at `t` — calm through alert to hunting. */
function mix(
  tone: { calm: Channels; alert: Channels; hunt: Channels },
  t: number,
): Channels {
  const cold = t < 0.5;
  const from = cold ? tone.calm : tone.alert;
  const to = cold ? tone.alert : tone.hunt;
  const local = cold ? t * 2 : (t - 0.5) * 2;
  return [
    Math.round(from[0] + (to[0] - from[0]) * local),
    Math.round(from[1] + (to[1] - from[1]) * local),
    Math.round(from[2] + (to[2] - from[2]) * local),
  ];
}
