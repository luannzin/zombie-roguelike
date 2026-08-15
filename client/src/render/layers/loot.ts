/**
 * World loot: small standing icons, a rarity glow, and (epic/legendary) a beam.
 *
 * Sprites sit with the coins, under the party. Auras go AFTER the darkness
 * pass — they are light, not things being lit. An unlit drop is not drawn
 * at all: a legendary column in the dark would be a free tracker.
 */

import type { LootRarity } from '../../net/protocol';
import { palette, type Channels } from '../../theme/palette';
import { effectFrame, effectImage, type VfxSheet } from '../vfx';
import type { LootAtlas } from '../loot';
import type { Projection } from '../projection';
import type { DrawableLoot } from '../types';

const GLOW_RADIUS: Record<LootRarity, number> = {
  common: 3.2,
  uncommon: 4.0,
  rare: 5.0,
  epic: 6.2,
  legendary: 7.2,
};

const GLOW_ALPHA: Record<LootRarity, number> = {
  common: 0.22,
  uncommon: 0.28,
  rare: 0.34,
  epic: 0.42,
  legendary: 0.5,
};

export function drawLootShadows(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  drops: DrawableLoot[],
): void {
  ctx.fillStyle = palette().entity.shadow;
  for (const drop of drops) {
    if (drop.visibility <= 0.01) continue;
    ctx.globalAlpha = drop.visibility;
    ctx.beginPath();
    ctx.ellipse(view.x(drop.x), view.y(drop.y + 0.6), view.size(0.9), view.size(0.4), 0, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

export function drawLootSprites(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  atlas: LootAtlas | null,
  drops: DrawableLoot[],
): void {
  if (!atlas) return;
  const { image, frameWidth, frameHeight } = atlas;
  for (const drop of drops) {
    if (drop.visibility <= 0.01) continue;
    const bob = Math.sin(drop.animTime * 3.2 + drop.phase) * 0.6;
    ctx.globalAlpha = drop.visibility;
    ctx.drawImage(
      image,
      drop.frame * frameWidth,
      0,
      frameWidth,
      frameHeight,
      view.x(drop.x - frameWidth / 2),
      view.y(drop.y - frameHeight + 0.6 + bob),
      view.size(frameWidth),
      view.size(frameHeight),
    );
  }
  ctx.globalAlpha = 1;
}

/** Ground puddle in the rarity colour. Drawn additive, after darkness. */
export function drawLootAuras(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  drops: DrawableLoot[],
  time: number,
): void {
  const glow = palette().rarityGlow;
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  for (const drop of drops) {
    if (drop.visibility <= 0.01) continue;
    const pulse = 0.82 + 0.18 * Math.sin(time * 3.4 + drop.phase);
    const [r, g, b] = glow[drop.rarity];
    const alpha = GLOW_ALPHA[drop.rarity] * drop.visibility * pulse;
    const radius = GLOW_RADIUS[drop.rarity];
    fillGlow(ctx, view.x(drop.x), view.y(drop.y + 0.4), view.size(radius), [r, g, b], alpha);
  }
  ctx.restore();
}

/** Exclusive looping column for epic and legendary. Tint is the rarity colour. */
export function drawLootBeams(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  sheet: VfxSheet | null,
  drops: DrawableLoot[],
  time: number,
): void {
  if (!sheet) return;
  const colors = palette().rarity;
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  for (const drop of drops) {
    if (!drop.beam || drop.visibility <= 0.01) continue;
    const frame = effectFrame(sheet, time + drop.phase);
    const image = effectImage(sheet, colors[drop.rarity]);
    const dx = view.x(drop.x - sheet.frameWidth / 2);
    const dy = view.y(drop.y - sheet.anchorY);
    ctx.globalAlpha = drop.visibility * 0.85;
    ctx.drawImage(
      image,
      frame * sheet.frameWidth,
      0,
      sheet.frameWidth,
      sheet.frameHeight,
      dx,
      dy,
      view.size(sheet.frameWidth),
      view.size(sheet.frameHeight),
    );
  }
  ctx.restore();
}

function fillGlow(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  radius: number,
  rgb: Channels,
  alpha: number,
): void {
  const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius);
  gradient.addColorStop(0, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${alpha})`);
  gradient.addColorStop(0.45, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${alpha * 0.35})`);
  gradient.addColorStop(1, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0)`);
  ctx.fillStyle = gradient;
  ctx.beginPath();
  ctx.ellipse(x, y, radius, radius * 0.55, 0, 0, Math.PI * 2);
  ctx.fill();
}
