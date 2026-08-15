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
import type { DrawableCoin, DrawableEntity } from '../types';

/** Player name label size, in screen px. One step of the font's pixel grid. */
const NAME_LABEL_PX = HUD_GRID;
/*
 * The nameplate, in design pixels, measured off Departure Mono's own metrics:
 * caps rise 8 above the baseline and descenders drop 3 below it. Measuring the
 * card off those rather than off the em box keeps the padding optically even.
 *
 * Descender space is reserved whether or not a name has one, so two cards side
 * by side are the same height and sit on the same line.
 *
 * These are the lobby's numbers (game/lobby-scene.ts `drawLabels`) with no dpr
 * term: the arena canvas is backed at CSS resolution (see Renderer.resize), so
 * one design pixel is one canvas pixel here.
 */
const LABEL_CAP = 8;
const LABEL_DESCENT = 3;
const LABEL_PAD_X = 4;
/** Width of the identity bar down the card's leading edge. */
const LABEL_ACCENT = 2;
const LABEL_CARD_H = LABEL_CAP + LABEL_DESCENT + 5;
/** Clearance between the pointer's tip and the head it points at. */
const LABEL_TIP_GAP = 2;

/**
 * "Confirmed", as a pixel stamp: one entry per lit cell, `[x, y]` from the
 * mark's top-left. Six wide and four tall, with the rising arm longer than the
 * falling one so it reads as a tick and not as a V.
 *
 * Stamped rather than typed or stroked. A glyph would be at the mercy of
 * whether Departure Mono has one (it is a pixel face with a small set), and a
 * stroked path at four pixels tall antialiases into a grey smudge.
 */
const LABEL_TICK: readonly (readonly [number, number])[] = [
  [5, 0],
  [0, 1],
  [4, 1],
  [1, 2],
  [3, 2],
  [2, 3],
];
const LABEL_TICK_W = 6;
const LABEL_TICK_H = 4;
/** Gap between the tick and the name it precedes. */
const LABEL_TICK_GAP = 3;
/** Coin bob amplitude in world px — tiny so it still reads as grounded. */
const COIN_BOB = 0.35;
/** Draw scale vs the processed 16px frame. */
const COIN_SCALE = 0.375;

export interface EntityContext {
  ctx: CanvasRenderingContext2D;
  view: Projection;
  config: GameConfig;
  book: SpriteBook;
}

export function drawShadow(entity: EntityContext, target: DrawableEntity): void {
  if (!target.alive || target.visibility <= 0.01) return;
  const { ctx, view } = entity;

  ctx.globalAlpha = target.visibility;
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
  ctx.globalAlpha = 1;
}

/** Soft ground puddle under each coin — drawn before the sprite. */
export function drawCoinShadows(entity: EntityContext, coins: DrawableCoin[]): void {
  const { ctx, view } = entity;
  ctx.fillStyle = palette().entity.shadow;
  for (const coin of coins) {
    ctx.beginPath();
    ctx.ellipse(
      view.x(coin.x),
      view.y(coin.y + 0.75),
      view.size(0.6),
      view.size(0.3),
      0,
      0,
      Math.PI * 2,
    );
    ctx.fill();
  }
}

/**
 * Spinning gold pickups. The sheet is a Y-axis tumble (`make_coin.py`);
 * `walkFrameOrder` + `fps` are the spin. One row — no facing.
 */
export function drawCoins(entity: EntityContext, coins: DrawableCoin[], sheetName: string): void {
  const { ctx, view, book } = entity;
  const sheet = book.get(sheetName);
  const image = book.image(sheetName, null);
  if (!sheet || !image) return;

  const w = sheet.frameWidth * COIN_SCALE;
  const h = sheet.frameHeight * COIN_SCALE;
  const row = sheet.rows.down ?? 0;
  const order = sheet.walkFrameOrder;
  const fps = sheet.fps || 12;

  for (const coin of coins) {
    const col = order[Math.floor(coin.animTime * fps) % order.length];
    const bob = Math.sin(coin.animTime * 7 + hashId(coin.id)) * COIN_BOB;
    const dx = view.x(coin.x - w / 2);
    const dy = view.y(coin.y - h + 0.75 + bob);
    const dw = view.size(w);
    const dh = view.size(h);
    ctx.drawImage(
      image,
      col * sheet.frameWidth,
      row * sheet.frameHeight,
      sheet.frameWidth,
      sheet.frameHeight,
      dx,
      dy,
      dw,
      dh,
    );
  }
}

function hashId(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) | 0;
  return (h & 0xffff) / 0xffff * Math.PI * 2;
}

export function drawEntity(entity: EntityContext, target: DrawableEntity): void {
  // Unlit enemies are not drawn at all — see DrawableEntity.visibility.
  if (!target.alive || target.visibility <= 0.01) return;
  const { ctx, view, book } = entity;

  const sheet = book.get(target.sheet);
  const image = book.image(target.sheet, target.tint);
  // Art still loading (or missing): draw nothing rather than a wrong sprite.
  if (!sheet || !image) return;

  const facing = facingFromAim(target.ax, target.ay);
  const row = sheet.rows[facing] ?? 0;
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

  ctx.globalAlpha = target.visibility;
  ctx.drawImage(image, col * w, row * h, w, h, dx, dy, dw, dh);
  blitGear(entity, target, facing, dx, dy, dw, dh);

  if (target.hitFlash > 0) {
    ctx.globalCompositeOperation = 'lighter';
    ctx.globalAlpha = Math.min(1, target.hitFlash * 0.95) * target.visibility;
    ctx.drawImage(image, col * w, row * h, w, h, dx, dy, dw, dh);
    blitGear(entity, target, facing, dx, dy, dw, dh);
    ctx.globalCompositeOperation = 'source-over';
    ctx.globalAlpha = target.visibility;
  }

  if (target.kind === 'player') {
    drawAimIndicator(entity, target, px, py);
    drawHealthBar(entity, target, view.rawX(px), spriteTop);
  } else if (target.hp < target.maxHp) {
    drawHealthBar(entity, target, view.rawX(px), spriteTop);
  }
  ctx.globalAlpha = 1;
}

/**
 * Equipped overlay, registered to the same 16x16 grid as the body. Same
 * facing and walk column, same multiply tint — a hue on the pack would be
 * a second identity.
 */
function blitGear(
  { ctx, book }: EntityContext,
  target: DrawableEntity,
  facing: string,
  dx: number,
  dy: number,
  dw: number,
  dh: number,
): void {
  if (!target.gear) return;
  const sheet = book.get(target.gear);
  const image = book.image(target.gear, target.tint);
  if (!sheet || !image) return;
  const row = sheet.rows[facing] ?? 0;
  const col = frameIndex(sheet, target.animTime, target.moving);
  ctx.drawImage(
    image,
    col * sheet.frameWidth,
    row * sheet.frameHeight,
    sheet.frameWidth,
    sheet.frameHeight,
    dx,
    dy,
    dw,
    dh,
  );
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

/**
 * Names, on a card above the head — the same card the lobby draws over the
 * seats at the fire (game/lobby-scene.ts `drawLabels`): inset panel fill, a
 * hairline border, a 2px bar in the player's own colour down the leading edge,
 * and a stepped pointer touching the head. Walking out of the camp is a change
 * of place, not a change of chrome, so the plate over a teammate's head has to
 * survive the trip unchanged.
 *
 * The identity colour lives in the BAR, not in the glyphs. Six players in six
 * tints is six different legibilities against the night, and the one thing a
 * name has to do is read; yours is full ink, everyone else's is muted, which
 * is the same distinction the roster makes.
 */
export function drawNameLabels(entity: EntityContext, targets: DrawableEntity[]): void {
  const { ctx, view, config, book } = entity;
  const tone = palette();

  ctx.font = hudFont(NAME_LABEL_PX);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'alphabetic';

  for (const target of targets) {
    if (!target.alive || !target.name || target.visibility <= 0.01) continue;
    const alpha = target.visibility;
    const frameHeight = book.get(target.sheet)?.frameHeight ?? config.spriteHeight;
    const offset = frameHeight - target.halfHeight + config.tileSize * 0.35;

    const cx = view.x(target.x + target.recoilX);
    // The tip of the pointer touches the head; the card floats above it.
    const tipY = view.y(target.y + target.recoilY - offset);
    const cardBottom = tipY - LABEL_TIP_GAP;
    const cardTop = cardBottom - LABEL_CARD_H;
    const baseline = cardBottom - LABEL_DESCENT - 2;

    // A player who has not confirmed gets no mark at all — an empty box or a
    // greyed tick is a second thing to read before you learn nothing. The card
    // is measured with the tick's space only when it is there, so an unready
    // plate is exactly the name and nothing else.
    const tick = target.ready ? LABEL_TICK_W + LABEL_TICK_GAP : 0;
    const textWidth = Math.ceil(ctx.measureText(target.name).width);
    const width = LABEL_ACCENT + LABEL_PAD_X * 2 + tick + textWidth;
    const left = cx - Math.round(width / 2);

    ctx.globalAlpha = alpha * 0.88;
    ctx.fillStyle = tone.panelInset;
    ctx.fillRect(left, cardTop, width, LABEL_CARD_H);

    // Border as four fills rather than a stroke: a 1px stroke straddles the
    // path and comes out as two half-lit rows at this size.
    ctx.globalAlpha = alpha * (target.isLocal ? 0.9 : 0.5);
    ctx.fillStyle = tone.panelBorder;
    ctx.fillRect(left, cardTop, width, 1);
    ctx.fillRect(left, cardBottom - 1, width, 1);
    ctx.fillRect(left, cardTop, 1, LABEL_CARD_H);
    ctx.fillRect(left + width - 1, cardTop, 1, LABEL_CARD_H);

    // The colour bar, and the pointer below it. The pointer's first step
    // overlaps the bottom border so the two merge instead of leaving a seam
    // where the card ends.
    ctx.globalAlpha = alpha;
    ctx.fillStyle = target.color;
    ctx.fillRect(left, cardTop, LABEL_ACCENT, LABEL_CARD_H);
    ctx.globalAlpha = alpha * 0.88;
    ctx.fillStyle = tone.panelInset;
    for (let step = 0; step < 3; step++) {
      ctx.fillRect(cx - (2 - step), cardBottom - 1 + step, 5 - step * 2, 1);
    }

    ctx.globalAlpha = alpha;
    if (target.ready) {
      const tickX = left + LABEL_ACCENT + LABEL_PAD_X;
      // Centred on the CAP BLOCK, not on the card: the tick is read as part of
      // the word, so it sits on the line the letters sit on.
      const tickY = baseline - LABEL_CAP + Math.round((LABEL_CAP - LABEL_TICK_H) / 2);
      ctx.fillStyle = tone.entity.labelShadow;
      for (const [dx, dy] of LABEL_TICK) ctx.fillRect(tickX + dx + 1, tickY + dy + 1, 1, 1);
      // The meter green, which everywhere else in this game means "full" —
      // borrowing it costs nothing and saves the player learning a colour.
      ctx.fillStyle = tone.hp.high;
      for (const [dx, dy] of LABEL_TICK) ctx.fillRect(tickX + dx, tickY + dy, 1, 1);
    }

    // Centred on the space BESIDE the colour bar and the tick rather than on
    // the card, so neither pushes the name off its own plate.
    const textX = Math.round(left + LABEL_ACCENT + LABEL_PAD_X + tick + textWidth / 2);
    ctx.fillStyle = tone.entity.labelShadow;
    ctx.fillText(target.name, textX + 1, baseline + 1);
    ctx.fillStyle = target.isLocal ? tone.ink : tone.inkMuted;
    ctx.fillText(target.name, textX, baseline);
  }

  ctx.globalAlpha = 1;
  ctx.textAlign = 'left';
}
