/**
 * World loot: small standing icons, a rarity glow, and either a beam or motes.
 *
 * Sprites sit with the coins, under the party, in screen space via
 * `Projection`. Light (glow, motes, beam) goes AFTER the darkness pass in
 * world space — the context already has the camera. The SPRITE stays dark
 * with the night. The VFX do not: a whisper of motes and aura leaks
 * through so a drop can be felt before the lantern reaches it. Fully lit
 * they run at full strength (`lit(1, floor) === 1`).
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

/** Specks around every drop. Epic / legendary keep the column AND a few motes. */
const MOTE_COUNT: Record<LootRarity, number> = {
  common: 4,
  uncommon: 5,
  rare: 6,
  epic: 3,
  legendary: 4,
};

const MOTE_ALPHA: Record<LootRarity, number> = {
  common: 0.32,
  uncommon: 0.4,
  rare: 0.48,
  epic: 0.36,
  legendary: 0.42,
};

/** How much of the VFX remains when the sprite is fully dark. */
const DARK_GLOW = 0.28;
const DARK_MOTE = 0.4;
const DARK_BEAM = 0.16;

function lit(visibility: number, floor: number): number {
  return visibility * (1 - floor) + floor;
}

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
    // Scaled about its CONTACT, not its centre: a bigger drop grows upward and
    // outward from the ground it is lying on, the same way a bigger prop
    // would. Growing about the middle would sink half of it into the floor.
    const w = frameWidth * drop.scale;
    const h = frameHeight * drop.scale;
    ctx.globalAlpha = drop.visibility;
    ctx.drawImage(
      image,
      drop.frame * frameWidth,
      0,
      frameWidth,
      frameHeight,
      view.x(drop.x - w / 2),
      view.y(drop.y - h + 0.6 + bob),
      view.size(w),
      view.size(h),
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
    const pulse = 0.78 + 0.22 * Math.sin(time * 2.6 + drop.phase);
    const [r, g, b] = glow[drop.rarity];
    const alpha = GLOW_ALPHA[drop.rarity] * lit(drop.visibility, DARK_GLOW) * pulse;
    fillGlow(ctx, drop.x, drop.y + 0.4, GLOW_RADIUS[drop.rarity], [r, g, b], alpha);
  }
  ctx.restore();
}

/**
 * Rising specks. Same world-space pass as the glow. Deterministic from
 * `time` and the drop's phase — no pool, no spawn, so two clients looking
 * at the same drop see the same motes. A few still rise in the dark.
 */
export function drawLootMotes(
  ctx: CanvasRenderingContext2D,
  drops: DrawableLoot[],
  time: number,
  tileSize: number,
): void {
  const glow = palette().rarityGlow;
  const unit = Math.max(1, Math.round(tileSize / 16));
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  for (const drop of drops) {
    const count = MOTE_COUNT[drop.rarity];
    if (count === 0) continue;
    const bob = Math.sin(drop.animTime * 3.2 + drop.phase) * 0.6;
    const [r, g, b] = glow[drop.rarity];
    const peak = MOTE_ALPHA[drop.rarity] * lit(drop.visibility, DARK_MOTE);
    ctx.fillStyle = `rgb(${r},${g},${b})`;
    for (let i = 0; i < count; i++) {
      const seed = drop.phase * 1.37 + i * 2.399;
      const frac = seed - Math.floor(seed);
      const period = 2.1 + frac * 1.4;
      const cycle = ((time + seed * 4) / period) % 1;
      const angle = seed * Math.PI * 2 + time * (0.34 + (i % 3) * 0.12);
      const orbit = tileSize * (0.18 + 0.16 * frac);
      const lift = cycle * tileSize * 0.62;
      const x = drop.x + Math.cos(angle) * orbit;
      const y =
        drop.y +
        bob -
        tileSize * 0.35 -
        lift +
        Math.sin(angle * 1.7) * tileSize * 0.06;
      const fade = Math.sin(cycle * Math.PI);
      const twinkle = 0.65 + 0.35 * Math.abs(Math.sin(time * 8.2 + seed * 6));
      const alpha = peak * fade * fade * twinkle;
      const px = Math.round(x);
      const py = Math.round(y);
      ctx.globalAlpha = alpha * 0.35;
      ctx.fillRect(px, py + unit, unit, unit);
      ctx.globalAlpha = alpha;
      const spark = fade > 0.72 ? unit + 1 : unit;
      ctx.fillRect(px, py, spark, spark);
    }
  }
  ctx.restore();
}

/**
 * Exclusive looping column for epic and legendary. Tint is the rarity colour.
 * Same space as `drawLootAuras` and as combat flashes: world pixels, not
 * `view.x` / `view.size`. A ghost of it remains in the dark.
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
    if (!drop.beam) continue;
    const frame = effectFrame(sheet, time + drop.phase);
    const image = effectImage(sheet, colors[drop.rarity]);
    ctx.globalAlpha = lit(drop.visibility, DARK_BEAM) * 0.85;
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
