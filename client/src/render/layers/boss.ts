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
import { drawBossImpact, drawBossTrail, drawSweepWind } from './boss-vfx';
import type { GameConfig } from '../../net/protocol';

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
  config: GameConfig | null = null,
): void {
  if (!atlas) return;
  const row = boss.row;
  // ASLEEP HE IS NOT DRAWN. He stands on the map from the moment it is built
  // so that the arrival has a body to belong to, but the party must not walk
  // into the yard and find him waiting in it — the shadow is the reveal.
  if (row.s === 'sleep') return;

  const frame = bossFrame(row, atlas, config);
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
    // Silhouette-only wash: the sprite is re-blitted over itself additively,
    // the same way `layers/entities` flashes a zombie. Additive rather than a
    // rectangle, or the flash is a glowing box round a body rather than the
    // body glowing.
    //
    // TWICE, ON A HARD HIT, AND THAT IS NOT A TWEAK. `lighter` adds the
    // sprite's own values to itself, so how bright a body flashes depends on
    // how bright the body already was — and he is the darkest thing in the
    // game, a mass of soot and rust lit by four fires. At 0.85 alpha a zombie
    // visibly blinks and he barely moved, which is how a boss ends up looking
    // like bullets are passing through him. A second pass is what makes the
    // brightest frame actually read as white.
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    const passes = boss.hitFlash > 0.45 ? 2 : 1;
    for (let pass = 0; pass < passes; pass++) {
      ctx.globalAlpha = Math.min(0.9, boss.hitFlash);
      ctx.drawImage(frame.image, frame.sx, 0, atlas.frameWidth, atlas.frameHeight,
                    dx, dy, w, h);
    }
    ctx.restore();
  }

  // AFTER THE BODY, ALL OF IT. The bar passes in front of him through most
  // of every swing — it is bolted to the arm nearest the camera — so a trail
  // drawn under the sprite would disappear behind the shoulder it came off.
  if (config) {
    drawSweepWind(ctx, view, row, config, time);
  }
  drawBossTrail(ctx, view, boss.trail, row.rage === true);
  for (const hit of boss.hits) drawBossImpact(ctx, view, hit);

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
