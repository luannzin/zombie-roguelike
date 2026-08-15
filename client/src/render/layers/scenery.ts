/**
 * Scenery layer: the scenes the server placed, drawn.
 *
 * `layers/terrain.ts` draws the PLACE. This draws what happened in it. The
 * pieces arrive already grouped and positioned on the map payload (see
 * `server/app/scenery.py`), so nothing here decides where anything goes — it
 * only decides how each piece meets the ground and the light.
 *
 * Two entry points, because a scene is stacked the same way the forest is:
 *
 *   bakeSceneryDecals()  blood, boot prints, dropped clothing, broken things.
 *                        Painted straight into the terrain layer's ground
 *                        canvas alongside its own litter, so they cost exactly
 *                        nothing per frame and can never occlude a body.
 *   drawSceneryProp()    cabins, tents, fences, signs, crates, cold firepits.
 *                        Bottom-anchored on a contact point and handed to the
 *                        renderer's depth sort, so a player passes in front of
 *                        and behind them the same way they pass a bonfire.
 *
 * WHY THE STANDING PASS IS NOT A SECOND BAKE. Everything here is static
 * geometry and could have gone into the prop cache with the rocks — except
 * that a baked prop is behind every character on screen, and the largest thing
 * in this file is a building. A player walking behind a cabin has to disappear
 * behind it. That single requirement is what puts these in the entity sort,
 * and once they are there, animating a few of them is free.
 *
 * WHAT MOVES, AND WHY SO LITTLE. A sign on a post swings; canvas breathes; a
 * dead fire still smokes. Crates are not scenery any more — they live on
 * `world.crates` and play a one-shot smash when they break. Everything else
 * here has STOPPED. The sway comes off the sheet's own `sway` field rather
 * than a table here, so the art decides what the wind can push.
 */

import type { Effects } from '../../game/effects';
import type { SceneryPiece, TileMap } from '../../game/world';
import { createSurface } from '../../lib/canvas';
import { palette } from '../../theme/palette';
import type { Camera } from '../camera';
import type { Projection } from '../projection';
import type { SceneryAtlas, SceneryDecal } from '../scenery';
import * as wind from '../wind';

/** Radians/second of the sway oscillation, before per-prop variation. */
const SWAY_RATE = 1.1;

/** Share of a print's life spent at full strength before it starts to fade. */
const FOOTPRINT_HOLD = 0.35;

/** Contact shadow, matching the one baked under the terrain's own props. */
const SHADOW_WIDTH = 0.7;
/** In world px, so it stays the same depth of contact at any sprite size. */
const SHADOW_HEIGHT = 4;
const SHADOW_ALPHA = 0.3;

/** Smoke: how many puffs are alive on a cold fire at once. */
const SMOKE_PUFFS = 5;
/** Seconds for one puff to rise and fade out. */
const SMOKE_LIFE = 3.6;
/** How far a puff climbs over its life, in world px. */
const SMOKE_RISE = 22;
/** Peak alpha of a puff. Low — this is a hint of heat, not a chimney. */
const SMOKE_ALPHA = 0.14;

/** A pixel-space window, for the uncached live path. */
export interface Bounds {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

function overlaps(
  piece: SceneryPiece,
  width: number,
  height: number,
  bounds: Bounds,
): boolean {
  return (
    piece.x + width / 2 >= bounds.x0 &&
    piece.x - width / 2 <= bounds.x1 &&
    piece.y + height / 2 >= bounds.y0 &&
    piece.y - height / 2 <= bounds.y1
  );
}

/**
 * Every flat piece, painted into the ground canvas.
 *
 * Called from the terrain layer's bake, after the soil and its own litter, so
 * a blood stain lands ON the leaves rather than under them: the leaves have
 * been falling for months and the blood happened last.
 */
export function bakeSceneryDecals(
  ctx: CanvasRenderingContext2D,
  world: TileMap,
  atlas: SceneryAtlas,
  bounds: Bounds | null = null,
): void {
  for (const piece of world.scenery.flat) {
    const sheet = atlas.decals[piece.kind];
    if (!sheet) continue;
    // `bounds` is the pixel window when the caller is painting live instead of
    // baking (a map too large to cache). Culling here rather than at the call
    // site keeps the two paths one function; a full-map scenery walk sixty
    // times a second is the cliff this avoids.
    if (bounds && !overlaps(piece, sheet.frameWidth, sheet.frameHeight, bounds)) continue;
    // Centred, not bottom-anchored: a thing lying on the floor has no feet.
    const frame = ((piece.variant % sheet.frames) + sheet.frames) % sheet.frames;
    const x = Math.round(piece.x - sheet.frameWidth / 2);
    const y = Math.round(piece.y - sheet.frameHeight / 2);
    drawFrame(ctx, sheet.image, frame, sheet.frameWidth, sheet.frameHeight, x, y, piece.flip);
  }
}

/**
 * Boot prints, in world space, over the floor and under everything else.
 *
 * Drawn LIVE rather than baked, unlike every other flat thing, because these
 * fade — and they have to fade, or a map turns into a solid mat of prints after
 * five minutes and stops carrying any information at all. The fade is also
 * what makes them readable as AGE: on an extraction run the freshest prints
 * are the ones going the way you last went, and a trail that got fainter as it
 * receded is a direction as much as a path.
 *
 * Culled against the camera, because the list is intentionally long-lived and
 * most of it is behind you.
 */
export function drawFootprints(
  ctx: CanvasRenderingContext2D,
  effects: Effects,
  atlas: SceneryAtlas,
  camera: Camera,
): void {
  const sheet = atlas.decals.tracks;
  if (!sheet || effects.footprints.length === 0) return;

  const left = camera.renderX - sheet.frameWidth;
  const top = camera.renderY - sheet.frameHeight;
  const right = camera.renderX + camera.viewWidth + sheet.frameWidth;
  const bottom = camera.renderY + camera.viewHeight + sheet.frameHeight;

  for (const print of effects.footprints) {
    if (print.x < left || print.x > right || print.y < top || print.y > bottom) continue;
    // Flat for most of its life and then fades. A print that started
    // disappearing immediately would never read as a trail, only as a smear
    // trailing the player.
    const remaining = 1 - print.age / print.life;
    const fade = remaining > FOOTPRINT_HOLD ? 1 : remaining / FOOTPRINT_HOLD;
    const frame = print.frame % sheet.frames;
    const dx = Math.round(print.x - sheet.frameWidth / 2);
    const dy = Math.round(print.y - sheet.frameHeight / 2);
    ctx.globalAlpha = print.depth * fade;
    ctx.drawImage(
      sheet.image,
      frame * sheet.frameWidth, 0, sheet.frameWidth, sheet.frameHeight,
      dx, dy, sheet.frameWidth, sheet.frameHeight,
    );
    if (print.blood > 0.02) {
      ctx.globalAlpha = print.depth * fade * print.blood * 0.9;
      ctx.drawImage(
        bloodTracks(sheet),
        frame * sheet.frameWidth, 0, sheet.frameWidth, sheet.frameHeight,
        dx, dy, sheet.frameWidth, sheet.frameHeight,
      );
    }
  }
  ctx.globalAlpha = 1;
}

let tracksBlood: HTMLCanvasElement | null = null;
let tracksBloodSrc: HTMLImageElement | null = null;

/** One multiply-tinted copy of the tracks sheet, in blood. */
function bloodTracks(sheet: SceneryDecal): HTMLCanvasElement {
  if (tracksBlood && tracksBloodSrc === sheet.image) return tracksBlood;
  const { canvas, ctx } = createSurface(
    sheet.image.width,
    sheet.image.height,
    'scenery/tracks-blood',
  );
  ctx.drawImage(sheet.image, 0, 0);
  ctx.globalCompositeOperation = 'source-in';
  ctx.fillStyle = palette().effects.blood[1] ?? palette().effects.blood[0];
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.globalCompositeOperation = 'source-over';
  tracksBlood = canvas;
  tracksBloodSrc = sheet.image;
  return canvas;
}

/**
 * One standing piece, in SCREEN space, so the renderer can depth-sort it with
 * the party. Mirrors `TerrainLayer.fire` — same anchoring, same reason.
 */
export function drawSceneryProp(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  atlas: SceneryAtlas,
  piece: SceneryPiece,
  time: number,
  anim = 0,
  hitFlash = 0,
): void {
  const sheet = atlas.props[piece.kind];
  if (!sheet) return;

  const frame = sheetFrame(sheet, piece.variant, anim);
  const width = sheet.frameWidth * view.zoom;
  const height = sheet.frameHeight * view.zoom;

  // Lean is applied at the TOP of the sprite only, by skewing the draw — a
  // whole sprite sliding sideways reads as the ground moving. Canvas cannot
  // skew a drawImage without a transform, so the cheap honest version is used
  // instead: shift the sprite and leave the base where it is by drawing the
  // bottom row separately. At these sizes the difference is one pixel, and one
  // pixel of movement is the entire effect.
  const lean = sheet.sway > 0 ? swayOf(piece, time) * sheet.sway * view.zoom : 0;
  const x = view.x(piece.x) - Math.round(width / 2);
  const y = view.y(piece.y) - height;

  // Contact shadow, the same one the rocks and trees get baked with. Without
  // it a crate hovers: at this camera angle the only thing telling you a
  // silhouette is standing ON the floor rather than floating above it is the
  // dark ellipse where it meets the ground.
  ctx.globalAlpha = SHADOW_ALPHA;
  ctx.fillStyle = palette().entity.shadow;
  ctx.beginPath();
  ctx.ellipse(
    view.x(piece.x),
    view.y(piece.y) - (SHADOW_HEIGHT * view.zoom) / 2,
    (width * SHADOW_WIDTH) / 2,
    (SHADOW_HEIGHT * view.zoom) / 2,
    0, 0, Math.PI * 2,
  );
  ctx.fill();
  ctx.globalAlpha = 1;

  blitProp(ctx, sheet, frame, x, y, width, height, lean, piece.flip);
  // Same additive white blink a body gets when a shot lands. A smash without
  // it reads as the wood just starting to play, not as a hit.
  if (hitFlash > 0) {
    ctx.globalCompositeOperation = 'lighter';
    ctx.globalAlpha = Math.min(1, hitFlash * 0.95);
    blitProp(ctx, sheet, frame, x, y, width, height, lean, piece.flip);
    ctx.globalCompositeOperation = 'source-over';
    ctx.globalAlpha = 1;
  }

  if (sheet.smokes) drawSmoke(ctx, view, piece, time);
}

function blitProp(
  ctx: CanvasRenderingContext2D,
  sheet: { image: HTMLImageElement; frameWidth: number; frameHeight: number },
  frame: number,
  x: number,
  y: number,
  width: number,
  height: number,
  lean: number,
  flip: boolean,
): void {
  if (lean !== 0) {
    const foot = Math.max(1, Math.round(width / sheet.frameWidth));
    ctx.drawImage(
      sheet.image,
      frame * sheet.frameWidth, 0, sheet.frameWidth, sheet.frameHeight - 1,
      Math.round(x + lean), y, width, height - foot,
    );
    ctx.drawImage(
      sheet.image,
      frame * sheet.frameWidth, sheet.frameHeight - 1, sheet.frameWidth, 1,
      x, y + height - foot, width, foot,
    );
    return;
  }
  drawFrame(
    ctx, sheet.image, frame, sheet.frameWidth, sheet.frameHeight,
    x, y, flip, width, height,
  );
}

/**
 * A thin column off a cold fire.
 *
 * Deliberately drawn AFTER the sprite and before the darkness pass, so it is
 * dimmed with everything else: smoke you can see in the pitch dark is a
 * particle effect, and smoke that only shows up when your lantern sweeps over
 * it is a discovery. Puffs are a fixed pool phased off the prop's own position
 * rather than a spawner, so two fires on screen never breathe in step and
 * neither one allocates.
 */
function drawSmoke(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  piece: SceneryPiece,
  time: number,
): void {
  const seed = piece.x * 0.037 + piece.y * 0.061;
  ctx.fillStyle = palette().effects.dustSmear;
  const size = Math.max(1, Math.round(view.zoom));

  for (let index = 0; index < SMOKE_PUFFS; index++) {
    const life = ((time / SMOKE_LIFE + index / SMOKE_PUFFS + seed) % 1 + 1) % 1;
    // Fades in fast and out slow, the way a puff thins as it spreads.
    const alpha = SMOKE_ALPHA * Math.min(1, life * 5) * (1 - life) ** 1.4;
    if (alpha <= 0.001) continue;
    // Drifts sideways more as it rises: near the embers the air still has a
    // direction, higher up it does not.
    const drift = Math.sin(time * 0.7 + index * 2.1 + seed * 6) * life * 5;
    ctx.globalAlpha = alpha;
    ctx.fillRect(
      Math.round(view.x(piece.x + drift)) - size,
      Math.round(view.y(piece.y - 4 - life * SMOKE_RISE)),
      size * (1 + Math.round(life * 2)),
      size,
    );
  }
  ctx.globalAlpha = 1;
}

/**
 * -1..1 lean, on the same wind the undergrowth is bending in.
 *
 * Reading `wind.lean` rather than a local sine is the entire reason this looks
 * like weather: when a gust crosses a homestead, the signpost swings on the
 * same front as the weeds around its base. A sign on its own clock is the
 * single clearest tell that a scene was assembled out of parts.
 */
function swayOf(piece: SceneryPiece, time: number): number {
  const phase = piece.x * 0.11 + piece.y * 0.07;
  const rate = SWAY_RATE * (0.8 + ((phase % 1) + 1) % 1 * 0.4);
  return wind.lean(piece.x, piece.y, time, 1, phase, rate);
}

/**
 * Frame index on a prop sheet. Variant sheets are a single strip; a crate
 * sheet is kinds × breakFrames, packed kind-major, and `anim` walks the smash.
 */
export function sheetFrame(
  sheet: { frames: number; kinds?: number; breakFrames?: number },
  variant: number,
  anim: number,
): number {
  const kinds = sheet.kinds ?? 0;
  const breakFrames = sheet.breakFrames ?? 0;
  if (kinds > 0 && breakFrames > 0) {
    const kind = ((variant % kinds) + kinds) % kinds;
    const frame = Math.max(0, Math.min(breakFrames - 1, anim));
    return kind * breakFrames + frame;
  }
  return ((variant % sheet.frames) + sheet.frames) % sheet.frames;
}

export function crateAnimFrame(
  sheet: { breakFrames?: number; fps?: number },
  age: number,
): number {
  const frames = sheet.breakFrames ?? 1;
  const fps = sheet.fps ?? 12;
  return Math.max(0, Math.min(frames - 1, Math.floor(age * fps)));
}

export function crateBreakDone(
  sheet: { breakFrames?: number; fps?: number },
  age: number,
): boolean {
  const frames = sheet.breakFrames ?? 1;
  const fps = sheet.fps ?? 12;
  return age >= frames / fps;
}

function drawFrame(
  ctx: CanvasRenderingContext2D,
  image: HTMLImageElement,
  frame: number,
  frameWidth: number,
  frameHeight: number,
  x: number,
  y: number,
  flip: boolean,
  width = frameWidth,
  height = frameHeight,
): void {
  if (!flip) {
    ctx.drawImage(
      image, frame * frameWidth, 0, frameWidth, frameHeight, x, y, width, height,
    );
    return;
  }
  // Mirrored around the sprite's own centre. Worth the save/restore: it
  // doubles the readings of every asymmetric piece — a cabin whose door is on
  // the other side, a fence run that falls the other way — for no extra art.
  ctx.save();
  ctx.translate(x + width, y);
  ctx.scale(-1, 1);
  ctx.drawImage(image, frame * frameWidth, 0, frameWidth, frameHeight, 0, 0, width, height);
  ctx.restore();
}
