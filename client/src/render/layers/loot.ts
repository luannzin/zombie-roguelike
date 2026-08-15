/**
 * World loot: small standing icons, a rarity glow, and either a beam or motes.
 *
 * Sprites sit with the coins, under the party, in screen space via
 * `Projection`. Light (glow, motes, beam) goes AFTER the darkness pass in
 * world space — the context already has the camera. An unlit drop is not
 * drawn at all: a legendary column in the dark would be a free tracker.
 * Epic and legendary own the column; the other three rarities get a few
 * rising specks in the rarity colour instead.
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

/** Specks around a drop that has no beam. Count is the whole tell. */
const MOTE_COUNT: Record<LootRarity, number> = {
  common: 3,
  uncommon: 4,
  rare: 5,
  epic: 0,
  legendary: 0,
};

const MOTE_ALPHA: Record<LootRarity, number> = {
  common: 0.28,
  uncommon: 0.36,
  rare: 0.44,
  epic: 0,
  legendary: 0,
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

/**
 * Ground puddle in the rarity colour. Drawn additive, after darkness, in
 * WORLD space — the context already carries zoom and camera, so these are
 * raw drop coordinates. Running them through `Projection` would place the
 * glow in a second, empty map.
 */
export function drawLootAuras(
  ctx: CanvasRenderingContext2D,
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
    fillGlow(ctx, drop.x, drop.y + 0.4, GLOW_RADIUS[drop.rarity], [r, g, b], alpha);
  }
  ctx.restore();
}

/**
 * Slow rising specks for common / uncommon / rare. Same world-space pass as
 * the glow. Deterministic from `time` and the drop's phase — no pool, no
 * spawn, so two clients looking at the same drop see the same motes.
 */
export function drawLootMotes(
  ctx: CanvasRenderingContext2D,
  drops: DrawableLoot[],
  time: number,
  tileSize: number,
): void {
  const glow = palette().rarityGlow;
  const unit = tileSize / 16;
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  for (const drop of drops) {
    const count = MOTE_COUNT[drop.rarity];
    if (count === 0 || drop.beam || drop.visibility <= 0.01) continue;
    const bob = Math.sin(drop.animTime * 3.2 + drop.phase) * 0.6;
    const [r, g, b] = glow[drop.rarity];
    const peak = MOTE_ALPHA[drop.rarity] * drop.visibility;
    ctx.fillStyle = `rgb(${r},${g},${b})`;
    for (let i = 0; i < count; i++) {
      const seed = drop.phase * 1.37 + i * 2.399;
      const frac = seed - Math.floor(seed);
      const period = 2.4 + frac * 1.2;
      const cycle = ((time + seed * 4) / period) % 1;
      const angle = seed * Math.PI * 2 + time * (0.28 + (i % 3) * 0.1);
      const orbit = tileSize * (0.2 + 0.1 * frac);
      const lift = cycle * tileSize * 0.5;
      const x = drop.x + Math.cos(angle) * orbit;
      const y =
        drop.y +
        bob -
        tileSize * 0.35 -
        lift +
        Math.sin(angle * 1.7) * tileSize * 0.05;
      const fade = Math.sin(cycle * Math.PI);
      ctx.globalAlpha = peak * fade * fade;
      ctx.fillRect(Math.round(x - unit / 2), Math.round(y - unit / 2), unit, unit);
    }
  }
  ctx.restore();
}

/**
 * Exclusive looping column for epic and legendary. Tint is the rarity colour.
 * Same space as `drawLootAuras` and as combat flashes: world pixels, not
 * `view.x` / `view.size`.
 */
export function drawLootBeams(
  ctx: CanvasRenderingContext2D,
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
    ctx.globalAlpha = drop.visibility * 0.85;
    ctx.drawImage(
      image,
      frame * sheet.frameWidth,
      0,
      sheet.frameWidth,
      sheet.frameHeight,
      Math.round(drop.x - sheet.frameWidth / 2),
      Math.round(drop.y - sheet.anchorY),
      sheet.frameWidth,
      sheet.frameHeight,
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
