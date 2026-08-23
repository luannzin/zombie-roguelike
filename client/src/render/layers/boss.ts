/**
 * The Sawyer, painted: one 128x120 frame, his shadow, his flash, his crescents.
 *
 * `render/boss.ts` decides WHICH frame (the atlas, the facing, the playhead
 * off the wire). This decides where it lands and what is drawn over it.
 *
 * THREE THINGS MAKE A 128px SPRITE FEEL HEAVY and none of them is the sprite:
 *
 *   THE SHADOW    a real contact pool under the FOOTPRINT — which is on the
 *                 manifest in tiles, and is nothing like the frame's width.
 *                 A shadow sized off `frameWidth` would be seven tiles across
 *                 and he would read as hovering over a stain.
 *   THE FLASH     a white wash over the whole silhouette on every landed hit.
 *                 It is the only feedback a player gets that a 2400-health
 *                 body is taking damage at all: the bar moves a pixel a shot,
 *                 the flash moves every time.
 *   THE WOBBLE    he never stands perfectly still. Two pixels of shake on the
 *                 frames his engine is loudest is the difference between a
 *                 body and a decal.
 *
 * THE SPRITE IS NOT PIXEL-SNAPPED TO THE TILE GRID and that is on purpose:
 * he moves at 2.9 tiles a second and snapping a 128px frame to whole pixels
 * at that speed visibly steps. Everything else in this game is snapped; he is
 * the exception, and the reason is that he is the only thing big enough for
 * the stepping to be more visible than the softness.
 */

import type { Projection } from '../projection';
import type { DrawableBoss } from '../types';
import type { BossAtlas } from '../boss';
import { bossFrame, crescentFrame } from '../boss';

/** How wide the contact pool is, as a multiple of his footprint. */
const SHADOW_SPREAD = 1.15;
const SHADOW_SQUASH = 0.30;

export function drawBoss(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  atlas: BossAtlas | null,
  boss: DrawableBoss,
  time: number,
  shadowColour: string,
): void {
  if (!atlas) return;
  const row = boss.row;
  // ASLEEP HE IS NOT DRAWN. He stands on the map from the moment it is built
  // so that the arrival has a body to belong to, but the party must not walk
  // into the yard and find him waiting in it — the shadow is the reveal.
  if (row.s === 'sleep') return;

  const frame = bossFrame(row, atlas);
  if (!frame) return;

  const zoom = view.zoom;
  const w = atlas.frameWidth * zoom;
  const h = atlas.frameHeight * zoom;
  const sx = view.x(row.x + boss.shakeX);
  const sy = view.y(row.y + boss.shakeY);
  const dx = sx - w * atlas.anchorX;
  const dy = sy - h * atlas.anchorY;

  // The contact pool. Not drawn during the arrival — he is in the air, and
  // `make_sawyer.py` bakes the FALLING shadow into those frames because a
  // runtime field can only draw what is standing on the floor.
  if (row.s !== 'arrive') {
    const tile = view.zoom * 16;
    const rx = atlas.footprint.w * tile * SHADOW_SPREAD * 0.5;
    ctx.save();
    ctx.globalAlpha = 0.42;
    ctx.fillStyle = shadowColour;
    ctx.beginPath();
    ctx.ellipse(sx, sy, rx, rx * SHADOW_SQUASH, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  ctx.drawImage(frame.image, frame.sx, 0, atlas.frameWidth, atlas.frameHeight,
                dx, dy, w, h);

  if (boss.hitFlash > 0.002) {
    // Silhouette-only wash: the sprite is redrawn as a solid white stencil and
    // composited over itself. `source-atop` rather than a rectangle, or the
    // flash is a glowing box round a body rather than the body glowing.
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    ctx.globalAlpha = Math.min(0.85, boss.hitFlash);
    ctx.drawImage(frame.image, frame.sx, 0, atlas.frameWidth, atlas.frameHeight,
                  dx, dy, w, h);
    ctx.restore();
  }

  drawCrescents(ctx, view, atlas, row.crest, time);
}

/** The thrown chain, mid-flight. Additive: it is carrying its own fire. */
function drawCrescents(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  atlas: BossAtlas,
  crest: DrawableBoss['row']['crest'],
  time: number,
): void {
  if (!crest || crest.length === 0) return;
  const spec = atlas.crescent;
  if (!spec) return;
  for (const one of crest) {
    const picked = crescentFrame(one, atlas, time);
    if (!picked) continue;
    const size = picked.size * view.zoom;
    ctx.drawImage(
      picked.image,
      picked.sx, 0, spec.frameWidth, spec.frameHeight,
      view.x(one.x) - size / 2,
      view.y(one.y) - size / 2,
      size, size,
    );
  }
}
