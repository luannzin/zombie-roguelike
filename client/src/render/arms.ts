/**
 * The arms that hold the weapon — plotted, not authored.
 *
 * WHY THIS IS DRAWN AT RUNTIME AND NOT ON THE SHEET. The player is four rows
 * of three frames (`server/tools/make_player.py`): down, left, right, up, with
 * the sleeves ending in one hand pixel each. The weapon points wherever the
 * mouse is. Those two facts cannot be reconciled by art — a held pose per aim
 * angle is a sheet nobody can regenerate — and until this file existed the
 * game simply did not try: the gun floated in front of the chest with a gap
 * between it and the body, which is what the whole "no gun animation" report
 * was actually looking at. A rifle nobody is holding is a prop lying in the
 * air at chest height.
 *
 * SO THE REACH IS THE ANIMATION. One line of world pixels from the shoulder
 * socket to the grip, stepped a pixel at a time and stamped as whole world
 * pixels, so it belongs to the same grid as the sprite it grows out of (root
 * AGENTS.md: the WORLD is pixel art). It follows the grip for free — every
 * recoil, every breath, every frame of the draw and every degree of a melee
 * arc already moves the grip, so the arm was never given an animation of its
 * own and cannot fall out of step with one.
 *
 * TWO HANDS ARE A CLASS TELL. A shoulder weapon gets a second reach to a
 * point along its own barrel (`weapon-feel.ts` decides which weapons, the
 * atlas decides where), and that second arm is most of what separates a rifle
 * from a very long pistol at sixteen pixels.
 *
 * The sleeve is the sheet's own cloth multiplied by the player's colour — the
 * same dye contract `sprites.ts` applies to the grey pixels of the art, run
 * here on two colours instead of a bitmap, because an arm authored in flat
 * grey would be the one part of a red player that stayed grey.
 */

import { palette } from '../theme/palette';
import type { Projection } from './projection';
import { parseColor } from './sprites';

/**
 * World px from the centreline out to an arm socket, and down from the top of
 * the 16px cell to the shoulder.
 *
 * Both are read off `make_player.py`'s anatomy: the coat is `BODY_HALF` 4
 * either side of `MID` 8 with a sleeve column proud of it, so the socket is
 * 4.5 out; the body starts at `BODY_TOP` 8 and the sleeve runs three rows
 * from 9, so the joint is 9.5 down. Getting these wrong does not look like a
 * bad number — it looks like an arm growing out of somebody's neck.
 */
const SHOULDER_OUT = 3.5;
const SHOULDER_DROP = 9.5;
/** How far down the ramp the far arm sits. One step, the way S13 spends one. */
const FAR_ARM_SHADE = 0.72;

export interface ArmArgs {
  ctx: CanvasRenderingContext2D;
  view: Projection;
  /** Body centre in world px, recoil folded in. */
  bodyX: number;
  /** Top of the 16px sprite cell in world px. */
  spriteTop: number;
  /**
   * How far the body has dropped on this walk frame, in world px. The sheet
   * bobs the torso a pixel on both contact poses and holds it up on the
   * passing pose; an arm rooted at a fixed height while the shoulder under it
   * moves is an arm that detaches twice a stride.
   */
  bob: number;
  /** The grip, world px — `gunPose`. */
  gripX: number;
  gripY: number;
  /** The support hand along the barrel, or null on a one-handed weapon. */
  supportX: number | null;
  supportY: number | null;
  /** The player's colour, or null for an untinted body. */
  tint: string | null;
  alpha: number;
}

export function drawArms(args: ArmArgs): void {
  const { ctx, view, bodyX, spriteTop, bob, gripX, gripY, alpha } = args;
  const cloth = sleeveOf(args.tint);
  const shoulderY = spriteTop + SHOULDER_DROP + bob;
  // THE NEAR SHOULDER IS THE ONE THE WEAPON IS ON. Which arm holds a gun is
  // not a fact about the character — the sprite is mirrored for half the
  // headings — it is a fact about where the grip currently is, and reaching
  // across the body for a weapon held out to the right is what the alternative
  // looks like.
  const side = gripX >= bodyX ? 1 : -1;
  const mainX = bodyX + SHOULDER_OUT * side;
  const offX = bodyX - SHOULDER_OUT * side;

  ctx.globalAlpha = alpha;
  const cell = Math.ceil(view.size(1));
  const twoHanded = args.supportX !== null && args.supportY !== null;
  // The support arm goes down FIRST and is a step darker: it is the far one,
  // reaching across the chest, and at this size overlap is the only depth cue
  // available. Drawn after the main arm it would read as the near one and the
  // body would look wrung.
  if (twoHanded) {
    reach(ctx, view, offX, shoulderY, args.supportX!, args.supportY!, cloth.dark, cell);
  }
  reach(ctx, view, mainX, shoulderY, gripX, gripY, cloth.sleeve, cell);
  ctx.globalAlpha = 1;
}

/**
 * The hands themselves, and they are drawn AFTER the weapon on purpose.
 *
 * A hand behind a grip is a weapon balanced on somebody's wrist. One world
 * pixel of skin over the pivot is what closes the fist round it — the same
 * single pixel the sheet spends on a hand, in the same colour, so the drawn
 * limb and the authored one are the same character's.
 */
export function drawHands(args: ArmArgs): void {
  const { ctx, view, gripX, gripY, alpha } = args;
  const cell = Math.ceil(view.size(1));
  ctx.globalAlpha = alpha;
  ctx.fillStyle = palette().entity.hand;
  ctx.fillRect(view.x(gripX), view.y(gripY), cell, cell);
  if (args.supportX !== null && args.supportY !== null) {
    ctx.fillRect(view.x(args.supportX), view.y(args.supportY), cell, cell);
  }
  ctx.globalAlpha = 1;
}

/**
 * One arm: a run of single world pixels from the shoulder to the hand.
 *
 * ONE PIXEL THICK, and that is the whole of the drawing. The first version
 * laid a shade row under every lit one for volume, which is the right
 * instinct on a mass and the wrong one on a limb: two pixels is a THIRD of
 * this character's torso, so the arms came out as clubs bolted to the
 * shoulders. The sheet itself spends one pixel on a sleeve and one on a hand
 * (`make_player.py`), and an arm drawn thicker than the art it grows out of
 * reads as a mistake even to somebody who could not say why.
 */
function reach(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  sx: number,
  sy: number,
  tx: number,
  ty: number,
  lit: string,
  cell: number,
): void {
  const dx = tx - sx;
  const dy = ty - sy;
  // One step per world pixel of the longer axis: any finer and the same cell
  // is stamped twice, any coarser and the arm has holes in it.
  const steps = Math.max(1, Math.round(Math.max(Math.abs(dx), Math.abs(dy))));
  ctx.fillStyle = lit;
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    ctx.fillRect(view.x(sx + dx * t), view.y(sy + dy * t), cell, cell);
  }
}

interface Sleeve {
  sleeve: string;
  shade: string;
  dark: string;
}

/**
 * The cloth ramp in this player's colour.
 *
 * Cached per tint for the same reason `TintCache` exists: a colour is chosen
 * once per player per room and the arms are redrawn sixty times a second, so
 * this multiplies three colours a few times a night instead of six times a
 * frame. `palette()` itself is re-read on a theme change, which is why the
 * cache is keyed on the base as well as the tint.
 */
const sleeves = new Map<string, Sleeve>();

function sleeveOf(tint: string | null): Sleeve {
  const fx = palette().entity;
  const key = `${tint ?? ''}|${fx.sleeve}`;
  const found = sleeves.get(key);
  if (found) return found;
  const made: Sleeve = {
    sleeve: dye(fx.sleeve, tint),
    shade: dye(fx.sleeveShade, tint),
    // The far arm's shadow. Not a fourth authored colour — the same ramp
    // step, one multiply further down.
    dark: dye(fx.sleeveShade, tint, FAR_ARM_SHADE),
  };
  sleeves.set(key, made);
  return made;
}

/**
 * `base` multiplied by the player's colour — the sheet's dye contract — and
 * optionally taken one step down the ramp with it.
 *
 * Both multiplies happen on the parsed bytes rather than by composing two
 * colour strings, because `parseColor` reads hex and an `rgb()` it had built
 * itself would come back white.
 */
function dye(base: string, tint: string | null, scale = 1): string {
  const [br, bg, bb] = parseColor(base);
  const [tr, tg, tb] = tint ? parseColor(tint) : ([255, 255, 255] as const);
  const r = (br * tr * scale) / 255;
  const g = (bg * tg * scale) / 255;
  const b = (bb * tb * scale) / 255;
  return `rgb(${Math.round(r)} ${Math.round(g)} ${Math.round(b)})`;
}
