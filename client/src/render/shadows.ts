/**
 * Ground contact: the one place a standing thing meets the floor.
 *
 * Every prop, body, coin and drop in this game used to draw its own hard
 * ellipse at a fixed alpha, in six different files, pointing nowhere. That is
 * enough to say "this is not floating" and nothing else: a crate two tiles
 * from a bonfire and a crate alone in the black wood wore exactly the same
 * mark, so nothing on the floor ever reacted to a light moving past it.
 *
 * Two terms replace it, and they answer different questions.
 *
 *   CONTACT   ambient occlusion. A soft dark pool right at the base, always
 *             there, brightest-free of any light in the scene. It is the
 *             crease where the object stops the sky reaching the ground, and
 *             it is what makes a silhouette read as SITTING on the floor
 *             rather than pasted over it.
 *   CAST      the shadow itself. Thrown AWAY from whatever is lighting the
 *             object, longer the further it stands from that light (a low
 *             lamp rakes; standing on top of one casts almost nothing), and
 *             fading out entirely where nothing is burning.
 *
 * The light field is a module-level singleton, refilled once per frame by the
 * renderer — the same shape `wind.ts` already uses, and for the same reason:
 * the alternative is threading a light list through `ground()`, `paintProps`,
 * the entity context, the loot pass and the rift pass, five signatures deep,
 * to hand every one of them the same six numbers.
 *
 * IT IS NOT PIXEL ART, and that is deliberate. A shadow is light, and the
 * house rule puts light on the smooth side of the split — so the mark is one
 * baked radial blob, stamped with smoothing ON, and never a hard ellipse.
 *
 * WHAT IS NOT HERE: the trees and the rocks. Their contact is baked into the
 * static ground canvas (`layers/terrain.paintProps`, and the rocks carry a
 * shadow painted into the sprite by `make_textures.py`), which is a cache
 * rebuilt when the map changes and not when a lantern walks past. A trunk that
 * swung its shadow around the player would cost a full ground rebake every
 * frame; a trunk with a still shadow costs nothing and nobody has ever looked
 * at a tree to find out where the fire is.
 */

import { createSurface } from '../lib/canvas';
import { palette } from '../theme/palette';
import type { Projection } from './projection';

/** Anything that can throw a shadow, in world px. */
interface ShadowLight {
  x: number;
  y: number;
  /** 0..1 at the source. Flicker is already folded in by the caller. */
  power: number;
  /** World px at which it can no longer move a shadow. */
  reach: number;
}

/**
 * How much of the world's vertical is squashed by the camera's slope.
 *
 * The same number the ellipses have always implied — every contact mark in the
 * game is roughly a third as deep as it is wide — stated once so a shadow
 * thrown north is correctly SHORTER on screen than the same shadow thrown east.
 */
const SQUASH = 0.42;

/** Cast length as a share of the object's height, at the edge of a light. */
const CAST_REACH = 0.85;
/** …and directly under it, where a lamp is overhead and the mark is a pool. */
const CAST_MIN = 0.25;
/** The cast never grows past this share of the object's own height. */
const CAST_CAP = 1.35;
/** Contact pool width, as a share of the caller's radius. */
const CONTACT_WIDTH = 0.92;
/** How much of the caller's alpha the ambient pool keeps with no light at all. */
const CONTACT_FLOOR = 0.8;

/** Blob resolution. Stamped scaled, so this only sets how smooth the edge is. */
const BLOB = 64;

const lights: ShadowLight[] = [];
let count = 0;
let blob: HTMLCanvasElement | null = null;
let blobTone = '';

/** Drop the frame's lights. Called by the renderer before it fills them. */
export function beginShadows(): void {
  count = 0;
}

/**
 * State a light for this frame. Cheap enough to call for every fire, lamp,
 * muzzle flash and the local lantern — the query below is linear in this list
 * and the list is a handful.
 */
export function addShadowLight(x: number, y: number, power: number, reach: number): void {
  if (power <= 0.02 || reach <= 0) return;
  const light = lights[count];
  if (light) {
    light.x = x;
    light.y = y;
    light.power = power;
    light.reach = reach;
  } else {
    lights.push({ x, y, power, reach });
  }
  count++;
}

/**
 * Where the light at a point is coming FROM, and how much of it there is.
 *
 * Every light in range contributes its direction weighted by what it delivers
 * here, so two fires either side of a barrel argue and the mark ends up
 * between them rather than snapping to whichever one won. `k` is the total,
 * clamped: it is what decides whether there is a cast shadow at all.
 */
export function lightAt(x: number, y: number): { dx: number; dy: number; k: number; t: number } {
  let sumX = 0;
  let sumY = 0;
  let sum = 0;
  let range = 0;
  for (let i = 0; i < count; i++) {
    const light = lights[i];
    const dx = x - light.x;
    const dy = y - light.y;
    const dist = Math.hypot(dx, dy);
    if (dist >= light.reach) continue;
    const near = dist / light.reach;
    // Falls off with the square, like the pools it is standing in.
    const weight = light.power * (1 - near) * (1 - near);
    if (weight <= 0.001) continue;
    const inv = dist > 0.001 ? 1 / dist : 0;
    sumX += dx * inv * weight;
    sumY += dy * inv * weight;
    sum += weight;
    range += near * weight;
  }
  if (sum <= 0.001) return { dx: 0, dy: 0, k: 0, t: 0 };
  const len = Math.hypot(sumX, sumY);
  if (len <= 0.001) return { dx: 0, dy: 0, k: 0, t: 0 };
  return {
    dx: sumX / len,
    dy: sumY / len,
    k: Math.min(1, sum),
    t: Math.min(1, range / sum),
  };
}

/** The soft mark itself, baked once. Rebuilt if the stylesheet's tone moves. */
function shadowBlob(): HTMLCanvasElement {
  const tone = palette().entity.shadow;
  if (blob && blobTone === tone) return blob;
  const surface = createSurface(BLOB, BLOB, 'ground-shadow');
  const half = BLOB / 2;
  const gradient = surface.ctx.createRadialGradient(half, half, 0, half, half, half);
  gradient.addColorStop(0, tone);
  gradient.addColorStop(0.45, tone);
  gradient.addColorStop(1, 'rgb(0 0 0 / 0)');
  surface.ctx.fillStyle = gradient;
  surface.ctx.fillRect(0, 0, BLOB, BLOB);
  blob = surface.canvas;
  blobTone = tone;
  return blob;
}

/**
 * Ground a standing thing.
 *
 * Everything is in WORLD px — a caller drawing in screen space hands its
 * `Projection` and a caller already under the world transform hands
 * `WORLD_SPACE`, so one routine serves both and neither has to know which.
 *
 * `x` / `y` is where the object MEETS THE FLOOR, not its centre. `rise` is how
 * tall it stands above that point; it is the only thing that decides how far
 * the cast reaches, which is why a coin's shadow stays a smudge and a fuel
 * drum's lies across the grass.
 */
export function groundShadow(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  x: number,
  y: number,
  radiusX: number,
  radiusY: number,
  rise: number,
  alpha = 1,
): void {
  if (alpha <= 0.01 || radiusX <= 0) return;
  const mark = shadowBlob();
  const { dx, dy, k, t } = lightAt(x, y);
  const cx = view.rawX(x);
  const cy = view.rawY(y);
  const width = view.size(radiusX) * 2;
  const height = view.size(radiusY) * 2;

  ctx.save();
  ctx.imageSmoothingEnabled = true;

  // The cast first, so the contact pool sits on top of it and the darkest
  // point of the pair is still where the object actually touches the floor.
  if (k > 0.02 && rise > 0) {
    const reach = Math.min(rise * CAST_CAP, rise * (CAST_MIN + CAST_REACH * t));
    const angle = Math.atan2(dy * SQUASH, dx);
    // Spans from the base out to `reach` past it: half-length is half of the
    // pool plus the throw, so the centre sits at half the throw.
    const long = width + view.size(reach);
    ctx.save();
    ctx.translate(cx + view.size(dx * reach * 0.5), cy + view.size(dy * reach * 0.5 * SQUASH));
    ctx.rotate(angle);
    ctx.globalAlpha = alpha * k * 0.72;
    ctx.drawImage(mark, -long / 2, -height / 2, long, height);
    ctx.restore();
  }

  ctx.globalAlpha = alpha * (CONTACT_FLOOR + (1 - CONTACT_FLOOR) * k);
  ctx.drawImage(
    mark,
    cx - (width * CONTACT_WIDTH) / 2,
    cy - height / 2,
    width * CONTACT_WIDTH,
    height,
  );
  ctx.restore();
}
