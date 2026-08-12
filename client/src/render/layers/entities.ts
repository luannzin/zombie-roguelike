/**
 * Entity layer: ground shadows, sprites, aim indicators, floating health bars
 * and name labels.
 *
 * Everything here is drawn in SCREEN space (identity transform) so placement
 * can be rounded to whole display pixels — see `projection.ts`.
 */

import type { GameConfig } from '../../net/protocol';
import { clamp01 } from '../../lib/math';
import { hudFont } from '../../theme/fonts';
import { hpColor, palette } from '../../theme/palette';
import type { Projection } from '../projection';
import { facingFromAim, frameIndex, type SpriteSheet, type TintCache } from '../sprites';
import type { DrawablePlayer } from '../types';
import { fillTextShadowed } from './effects';

/** Player name label size, in screen px (unscaled by zoom). */
const NAME_LABEL_PX = 11;

export interface EntityContext {
  ctx: CanvasRenderingContext2D;
  view: Projection;
  config: GameConfig;
  sheet: SpriteSheet;
  tints: TintCache;
}

export function drawShadow(entity: EntityContext, player: DrawablePlayer): void {
  if (!player.alive) return;
  const { ctx, view, config } = entity;

  ctx.fillStyle = palette().entity.shadow;
  ctx.beginPath();
  ctx.ellipse(
    view.x(player.x + player.recoilX),
    view.y(player.y + player.recoilY + config.playerHalfHeight),
    view.size(config.playerHalfWidth * 1.15),
    view.size(config.playerHalfHeight * 0.75),
    0,
    0,
    Math.PI * 2,
  );
  ctx.fill();
}

export function drawPlayer(entity: EntityContext, player: DrawablePlayer): void {
  if (!player.alive) return;
  const { ctx, view, config, sheet, tints } = entity;

  const row = sheet.rows[facingFromAim(player.ax, player.ay)] ?? 0;
  const col = frameIndex(sheet, player.animTime, player.moving);
  const image = tints.get(player.color);

  const w = sheet.frameWidth;
  const h = sheet.frameHeight;
  // The sprite's bottom edge sits on the bottom of the collision box, so a
  // 1x1.5-tile character stands correctly on a 0.6x0.45-tile footprint.
  const px = player.x + player.recoilX;
  const py = player.y + player.recoilY;
  const spriteTop = py + config.playerHalfHeight - h;
  const dx = view.x(px - w / 2);
  const dy = view.y(spriteTop);
  const dw = view.size(w);
  const dh = view.size(h);

  ctx.drawImage(image, col * w, row * h, w, h, dx, dy, dw, dh);

  if (player.hitFlash > 0) {
    ctx.globalCompositeOperation = 'lighter';
    ctx.globalAlpha = Math.min(1, player.hitFlash * 0.95);
    ctx.drawImage(image, col * w, row * h, w, h, dx, dy, dw, dh);
    ctx.globalCompositeOperation = 'source-over';
    ctx.globalAlpha = 1;
  }

  drawAimIndicator(entity, player, px, py);
  drawHealthBar(entity, player, view.rawX(px), spriteTop);
}

function drawAimIndicator(
  { ctx, view, config }: EntityContext,
  player: DrawablePlayer,
  px: number,
  py: number,
): void {
  const cx = view.rawX(px);
  const cy = view.rawY(py);
  const ts = config.tileSize;

  const aim = palette().entity;
  ctx.strokeStyle = player.isLocal ? aim.aimLocal : aim.aimRemote;
  ctx.lineWidth = Math.max(1, view.zoom * 0.7);
  ctx.beginPath();
  ctx.moveTo(cx + view.size(player.ax * ts * 0.4), cy + view.size(player.ay * ts * 0.4));
  ctx.lineTo(cx + view.size(player.ax * ts * 0.75), cy + view.size(player.ay * ts * 0.75));
  ctx.stroke();
}

function drawHealthBar(
  { ctx, view, config }: EntityContext,
  player: DrawablePlayer,
  centerX: number,
  spriteTop: number,
): void {
  const ts = config.tileSize;
  const unit = Math.max(1, Math.round(ts * 0.0625) * view.zoom); // 1 world px
  const barW = Math.round(ts * 0.875) * view.zoom;
  const barH = unit * 3;
  const ratio = clamp01(player.hp / player.maxHp);
  const barX = Math.round(centerX - barW / 2);
  const barY = view.y(spriteTop - ts * 0.125);

  ctx.fillStyle = palette().entity.barBackdrop;
  ctx.fillRect(barX, barY, barW, barH);
  ctx.fillStyle = hpColor(ratio);
  ctx.fillRect(barX + unit, barY + unit, Math.round((barW - 2 * unit) * ratio), unit);
}

export function drawNameLabels(entity: EntityContext, players: DrawablePlayer[]): void {
  const { ctx, view, config, sheet } = entity;

  ctx.font = hudFont(NAME_LABEL_PX);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'bottom';

  const labelShadow = palette().entity.labelShadow;
  const nameOffset = sheet.frameHeight - config.playerHalfHeight + config.tileSize * 0.35;
  for (const player of players) {
    if (!player.alive) continue;
    fillTextShadowed(
      ctx,
      player.name,
      view.x(player.x + player.recoilX),
      view.y(player.y + player.recoilY - nameOffset),
      player.color,
      labelShadow,
    );
  }
}
