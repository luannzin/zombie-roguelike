/**
 * Entity layer: ground shadows, sprites, aim indicators, floating health bars
 * and name labels — for players and enemies alike.
 *
 * Everything here is drawn in SCREEN space (identity transform) so placement
 * can be rounded to whole display pixels — see `projection.ts`.
 *
 * The only per-kind branches are presentation ones: enemies get no name label,
 * no aim indicator (their facing is the sprite), and a health bar only once
 * they are hurt — an arena of full green bars is noise, a damaged one is
 * information.
 */

import type { GameConfig } from '../../net/protocol';
import { clamp01 } from '../../lib/math';
import { HUD_GRID, hudFont } from '../../theme/fonts';
import { hpColor, palette } from '../../theme/palette';
import type { Projection } from '../projection';
import { facingFromAim, frameIndex, type SpriteBook } from '../sprites';
import type { DrawableEntity } from '../types';
import { drawCenteredText } from './effects';

/** Player name label size, in screen px. One step of the font's pixel grid. */
const NAME_LABEL_PX = HUD_GRID;

export interface EntityContext {
  ctx: CanvasRenderingContext2D;
  view: Projection;
  config: GameConfig;
  book: SpriteBook;
}

export function drawShadow(entity: EntityContext, target: DrawableEntity): void {
  if (!target.alive) return;
  const { ctx, view } = entity;

  ctx.fillStyle = palette().entity.shadow;
  ctx.beginPath();
  ctx.ellipse(
    view.x(target.x + target.recoilX),
    view.y(target.y + target.recoilY + target.halfHeight),
    view.size(target.halfWidth * 1.15),
    view.size(target.halfHeight * 0.75),
    0,
    0,
    Math.PI * 2,
  );
  ctx.fill();
}

export function drawEntity(entity: EntityContext, target: DrawableEntity): void {
  if (!target.alive) return;
  const { ctx, view, book } = entity;

  const sheet = book.get(target.sheet);
  const image = book.image(target.sheet, target.tint);
  // Art still loading (or missing): draw nothing rather than a wrong sprite.
  if (!sheet || !image) return;

  const row = sheet.rows[facingFromAim(target.ax, target.ay)] ?? 0;
  const col = frameIndex(sheet, target.animTime, target.moving);

  const w = sheet.frameWidth;
  const h = sheet.frameHeight;
  // The sprite's bottom edge sits on the bottom of the collision box, so a
  // taller creature stands correctly on the same footprint.
  const px = target.x + target.recoilX;
  const py = target.y + target.recoilY;
  const spriteTop = py + target.halfHeight - h;
  const dx = view.x(px - w / 2);
  const dy = view.y(spriteTop);
  const dw = view.size(w);
  const dh = view.size(h);

  ctx.drawImage(image, col * w, row * h, w, h, dx, dy, dw, dh);

  if (target.hitFlash > 0) {
    ctx.globalCompositeOperation = 'lighter';
    ctx.globalAlpha = Math.min(1, target.hitFlash * 0.95);
    ctx.drawImage(image, col * w, row * h, w, h, dx, dy, dw, dh);
    ctx.globalCompositeOperation = 'source-over';
    ctx.globalAlpha = 1;
  }

  if (target.kind === 'player') {
    drawAimIndicator(entity, target, px, py);
    drawHealthBar(entity, target, view.rawX(px), spriteTop);
  } else if (target.hp < target.maxHp) {
    drawHealthBar(entity, target, view.rawX(px), spriteTop);
  }
}

function drawAimIndicator(
  { ctx, view, config }: EntityContext,
  target: DrawableEntity,
  px: number,
  py: number,
): void {
  const cx = view.rawX(px);
  const cy = view.rawY(py);
  const ts = config.tileSize;

  const aim = palette().entity;
  ctx.strokeStyle = target.isLocal ? aim.aimLocal : aim.aimRemote;
  ctx.lineWidth = Math.max(1, view.zoom * 0.7);
  ctx.beginPath();
  ctx.moveTo(cx + view.size(target.ax * ts * 0.4), cy + view.size(target.ay * ts * 0.4));
  ctx.lineTo(cx + view.size(target.ax * ts * 0.75), cy + view.size(target.ay * ts * 0.75));
  ctx.stroke();
}

function drawHealthBar(
  { ctx, view, config }: EntityContext,
  target: DrawableEntity,
  centerX: number,
  spriteTop: number,
): void {
  const ts = config.tileSize;
  const unit = Math.max(1, Math.round(ts * 0.0625) * view.zoom); // 1 world px
  const barW = Math.round(ts * 0.875) * view.zoom;
  const barH = unit * 3;
  const ratio = clamp01(target.hp / target.maxHp);
  const barX = Math.round(centerX - barW / 2);
  const barY = view.y(spriteTop - ts * 0.125);

  ctx.fillStyle = palette().entity.barBackdrop;
  ctx.fillRect(barX, barY, barW, barH);
  ctx.fillStyle = hpColor(ratio);
  ctx.fillRect(barX + unit, barY + unit, Math.round((barW - 2 * unit) * ratio), unit);
}

export function drawNameLabels(entity: EntityContext, targets: DrawableEntity[]): void {
  const { ctx, view, config, book } = entity;

  ctx.font = hudFont(NAME_LABEL_PX);
  ctx.textBaseline = 'bottom';

  const labelShadow = palette().entity.labelShadow;
  for (const target of targets) {
    if (!target.alive || !target.name) continue;
    const frameHeight = book.get(target.sheet)?.frameHeight ?? config.spriteHeight;
    const offset = frameHeight - target.halfHeight + config.tileSize * 0.35;
    drawCenteredText(
      ctx,
      target.name,
      view.x(target.x + target.recoilX),
      view.y(target.y + target.recoilY - offset),
      target.color,
      labelShadow,
    );
  }
}
