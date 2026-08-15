/**
 * Blood pools under persistent corpses.
 *
 * The fallen BODY is drawn from a death sheet (pixel poses, not a rotated
 * walk frame). This file is the STAIN it leaves: scenery `blood.png`, the
 * same frames a scene already uses for a pool somebody else left. Growing
 * one under a kill turns the map into a record of the fight, and walking
 * through it tints the next few boot prints — see `spawnFootprint`'s `blood`.
 *
 * Flat, no outline, world space, under entities. Same contract as the
 * scenery blood baked into the ground, except these appear during play so
 * they cannot go into the bake.
 */

import type { DrawableCorpse } from '../types';
import type { Camera } from '../camera';
import { clamp01 } from '../../lib/math';
import type { SceneryAtlas } from '../scenery';

/** Matches `DEATH_FRAMES / DEATH_FPS` in make_vfx.py. */
export const DEATH_TIME = 12 / 16;
/** Matches `DEATH_IMPACT` in make_vfx.py. The VFX flash; the body sheet lands near here. */
export const DEATH_IMPACT = 0.48;
/** Seconds the death-sheet timeline takes to reach its prone rest (5 frames at 12 fps). */
export const DEATH_FALL = 4 / 12;
/** Seconds the pool takes to finish spreading. */
export const POOL_GROW = 1.55;
/** `make_scenery.py` blood kinds: 0 spray, 1 pool. */
const BLOOD_SPRAY_FRAME = 0;
const BLOOD_POOL_FRAME = 1;

export function poolRadius(age: number): number {
  const grown = clamp01(age / POOL_GROW);
  return 3.2 + grown * 5.5;
}

export function poolWetness(age: number): number {
  const grown = clamp01(age / POOL_GROW);
  return 0.4 + grown * 0.6;
}

function easeOut(t: number): number {
  const x = clamp01(t);
  return 1 - (1 - x) ** 3;
}

/** World space, with the boot prints. Hidden in the dark like everything else. */
export function drawBloodPools(
  ctx: CanvasRenderingContext2D,
  corpses: readonly DrawableCorpse[],
  atlas: SceneryAtlas,
  camera: Camera,
): void {
  const sheet = atlas.decals.blood;
  if (!sheet || corpses.length === 0) return;

  const fw = sheet.frameWidth;
  const fh = sheet.frameHeight;
  const left = camera.renderX - fw;
  const top = camera.renderY - fh;
  const right = camera.renderX + camera.viewWidth + fw;
  const bottom = camera.renderY + camera.viewHeight + fh;

  for (const body of corpses) {
    if (body.visibility <= 0.02) continue;
    if (body.x < left || body.x > right || body.y < top || body.y > bottom) continue;

    const grown = easeOut(body.age / POOL_GROW);
    const alpha = body.visibility;

    if (body.age < 0.28) {
      const spray = 1 - body.age / 0.28;
      const scale = 0.28 + (1 - spray) * 0.16;
      blit(
        ctx,
        sheet.image,
        BLOOD_SPRAY_FRAME,
        fw,
        fh,
        body.x,
        body.y + body.halfHeight,
        scale,
        alpha * spray * 0.75,
        body.dx < 0,
      );
    }

    const scale = 0.18 + grown * 0.30;
    blit(
      ctx,
      sheet.image,
      BLOOD_POOL_FRAME,
      fw,
      fh,
      body.x,
      body.y + body.halfHeight,
      scale,
      alpha * (0.55 + grown * 0.45),
      body.dx < 0,
    );
  }
  ctx.globalAlpha = 1;
}

function blit(
  ctx: CanvasRenderingContext2D,
  image: HTMLImageElement,
  frame: number,
  fw: number,
  fh: number,
  x: number,
  y: number,
  scale: number,
  alpha: number,
  flip: boolean,
): void {
  const dw = fw * scale;
  const dh = fh * scale;
  const dx = Math.round(x - dw / 2);
  const dy = Math.round(y - dh / 2);
  ctx.globalAlpha = alpha;
  if (flip) {
    ctx.save();
    ctx.translate(dx + dw, dy);
    ctx.scale(-1, 1);
    ctx.drawImage(image, frame * fw, 0, fw, fh, 0, 0, dw, dh);
    ctx.restore();
  } else {
    ctx.drawImage(image, frame * fw, 0, fw, fh, dx, dy, dw, dh);
  }
}
