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
import { stainFade } from '../../game/entity-visuals';
import { createSurface, type OffscreenSurface } from '../../lib/canvas';
import { clamp01 } from '../../lib/math';
import { HUD_GRID, hudFont } from '../../theme/fonts';
import { hpColor, palette } from '../../theme/palette';
import type { GoreAtlas } from '../gore';
import type { GunAtlas } from '../guns';
import { gunHand } from '../guns';
import type { Projection } from '../projection';
import { facingFromAim, frameIndex, timelineFrame, type SpriteBook } from '../sprites';
import type { DrawableCoin, DrawableCorpse, DrawableEntity } from '../types';

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
  /** Wound decals stamped on hurt bodies. Null until the atlas lands. */
  gore: GoreAtlas | null;
  /** Held gun sprites. Null until the atlas lands. */
  guns: GunAtlas | null;
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
  const spin = target.hitSpin;
  const spun = Math.abs(spin) > 0.01;
  if (spun) {
    ctx.save();
    ctx.translate(dx + dw / 2, dy + dh);
    ctx.rotate(spin);
    ctx.translate(-(dx + dw / 2), -(dy + dh));
  }

  ctx.globalAlpha = target.visibility;
  ctx.drawImage(image, col * w, row * h, w, h, dx, dy, dw, dh);
  blitGear(entity, target, facing, dx, dy, dw, dh);
  drawHeldPack(entity, target, facing, dx, dy, dw, dh);

  if (target.hitFlash > 0) {
    ctx.globalCompositeOperation = 'lighter';
    ctx.globalAlpha = Math.min(1, target.hitFlash * 0.95) * target.visibility;
    ctx.drawImage(image, col * w, row * h, w, h, dx, dy, dw, dh);
    blitGear(entity, target, facing, dx, dy, dw, dh);
    ctx.globalCompositeOperation = 'source-over';
    ctx.globalAlpha = target.visibility;
  }

  // After the flash, not under it: the white blink is the moment the hit
  // lands, the wound is what the hit left, and the second has to outlast the
  // first on screen or it never registers as damage.
  drawStains(entity, target, image, col * w, row * h, w, h, dx, dy, dw, dh);
  if (spun) ctx.restore();

  if (target.kind === 'player') {
    drawHeldGun(entity, target, px, py);
    drawHealthBar(entity, target, view.rawX(px), spriteTop);
  } else if (target.hp < target.maxHp) {
    drawHealthBar(entity, target, view.rawX(px), spriteTop);
  }
  ctx.globalAlpha = 1;
}

/**
 * A dead enemy, collapsed onto the floor. Screen space, under living bodies.
 *
 * The body is a real death sheet (`<name>-death`): a one-shot timeline that
 * holds the last frame. Never rotate or squash a walk sprite — 16px through
 * a canvas transform is the mush this sheet exists to replace. The row is
 * the killing blow, not the last walk facing. Gear uses matching `-death`
 * overlays so a hat stays on the head as it falls.
 */
export function drawCorpseSprites(
  entity: EntityContext,
  corpses: readonly DrawableCorpse[],
): void {
  if (corpses.length === 0) return;
  for (const body of corpses) {
    if (body.visibility <= 0.02) continue;
    drawOneCorpse(entity, body);
  }
  entity.ctx.globalAlpha = 1;
}

function deathSheetName(name: string): string {
  return `${name}-death`;
}

function drawOneCorpse(entity: EntityContext, body: DrawableCorpse): void {
  const { ctx, view, book } = entity;
  const deathName = deathSheetName(body.sheet);
  const death = book.get(deathName);
  const sheet = death ?? book.get(body.sheet);
  const image = death ? book.image(deathName, null) : book.image(body.sheet, null);
  if (!sheet || !image) return;

  const fallX = body.dx !== 0 ? body.dx : body.ax;
  const fallY = body.dy !== 0 ? body.dy : body.ay;
  const facing = facingFromAim(fallX, fallY);
  const row = sheet.rows[facing] ?? 0;
  const col = death ? timelineFrame(sheet, body.age) : sheet.idleFrame;
  const w = sheet.frameWidth;
  const h = sheet.frameHeight;
  const spriteTop = body.y + body.halfHeight - h;
  const dx = view.x(body.x - w / 2);
  const dy = view.y(spriteTop);
  const dw = view.size(w);
  const dh = view.size(h);

  const impactAt = death ? Math.max(0, sheet.frames - 2) / sheet.fps : 0;
  const flash = death ? Math.max(0, 1 - Math.abs(body.age - impactAt) * 14) : 0;
  const settled = !death || col >= sheet.frames - 1;
  const dim = settled ? 0.88 : 1;

  ctx.globalAlpha = body.visibility * dim;
  ctx.drawImage(image, col * w, row * h, w, h, dx, dy, dw, dh);
  blitCorpseGear(entity, body, facing, col, dx, dy, dw, dh, !!death);
  drawStains(entity, corpseAsTarget(body), image, col * w, row * h, w, h, dx, dy, dw, dh);

  if (flash > 0.04) {
    ctx.globalCompositeOperation = 'lighter';
    ctx.globalAlpha = Math.min(1, flash * 0.85) * body.visibility;
    ctx.drawImage(image, col * w, row * h, w, h, dx, dy, dw, dh);
    ctx.globalCompositeOperation = 'source-over';
  }
}

function blitCorpseGear(
  { ctx, book }: EntityContext,
  body: DrawableCorpse,
  facing: string,
  col: number,
  dx: number,
  dy: number,
  dw: number,
  dh: number,
  useDeath: boolean,
): void {
  for (const name of body.gear) {
    const sheetName = useDeath ? deathSheetName(name) : name;
    const sheet = book.get(sheetName);
    const image = book.image(sheetName, null);
    if (!sheet || !image) continue;
    const row = sheet.rows[facing] ?? 0;
    const frame = Math.min(col, sheet.frames - 1);
    ctx.drawImage(
      image,
      frame * sheet.frameWidth,
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

function corpseAsTarget(body: DrawableCorpse): DrawableEntity {
  return {
    id: body.id,
    kind: 'enemy',
    sheet: body.sheet,
    tint: null,
    gear: body.gear,
    color: '',
    name: '',
    ready: false,
    x: body.x,
    y: body.y,
    ax: body.ax,
    ay: body.ay,
    hp: 0,
    maxHp: 1,
    stamina: 0,
    staminaMax: 0,
    winded: false,
    alive: false,
    moving: false,
    animTime: 0,
    isLocal: false,
    hitFlash: 0,
    stains: body.stains,
    visibility: body.visibility,
    awareness: 0,
    alertKnown: false,
    viewRange: 0,
    viewDegrees: 0,
    recoilX: 0,
    recoilY: 0,
    hitSpin: 0,
    pour: null,
    halfWidth: 0,
    halfHeight: body.halfHeight,
    weapon: null,
    gunKick: 0,
    gunPump: 0,
  };
}

/**
 * Equipped overlays, registered to the same 16x16 grid as the body. Same
 * facing and walk column. A tinted target (the player) multiply-tints
 * every layer; an untinted one (a zombie) keeps the art's own colours.
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
  for (const name of target.gear) {
    const sheet = book.get(name);
    const image = book.image(name, target.tint);
    if (!sheet || !image) continue;
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
}

/**
 * The backpack, mid-pour: off the shoulders, out at arm's length, upside down.
 *
 * THE PACK LEAVING THE BACK IS THE WHOLE READ. A character standing next to a
 * platform while items appear out of them is a spawner; the same character
 * holding their own bag over the deck and turning it over is somebody paying
 * for the flight home. So while a pour is running the game takes the pack out
 * of `gear` and hands it here instead, and this draws the SAME sheet, the same
 * frame and the same row through one extra transform.
 *
 * At `grip` 0 that transform is the identity, which is not a coincidence — it
 * is what makes the handoff from worn to held invisible. Everything else is
 * eased off that: out along the aim (which is pointed at the deck for the
 * length of the ceremony), up, and over onto its mouth.
 */
function drawHeldPack(
  { ctx, view, book }: EntityContext,
  target: DrawableEntity,
  facing: string,
  dx: number,
  dy: number,
  dw: number,
  dh: number,
): void {
  const pose = target.pour;
  if (!pose || pose.grip <= 0.001) return;
  const sheet = book.get(pose.sheet);
  const image = book.image(pose.sheet, target.tint);
  if (!sheet || !image) return;

  const row = sheet.rows[facing] ?? 0;
  const col = frameIndex(sheet, target.animTime, target.moving);
  const g = pose.grip;
  const zoom = view.zoom;
  // The shake only exists while things are actually coming out. A bag being
  // lifted or put back is being handled; a bag being emptied is being WORKED.
  const shaking = pose.phase === POUR_DUMP ? 1 : 0;
  const shake = Math.sin(pose.age * 34) * shaking;

  // Held out along the aim and up. The body is already facing the deck, so
  // "out" is "over the platform" without this needing to know where that is.
  const outX = (target.ax * 5.5 + shake * 0.7) * zoom * g;
  const outY = (target.ay * 2.5 - 7 + shake * 0.4) * zoom * g;
  // Over onto its mouth, turning the way the body is leaning.
  const angle = g * Math.PI * (target.ax < 0 ? -1 : 1) + shake * 0.05 * g;
  const cx = dx + dw / 2 + outX;
  const cy = dy + dh / 2 + outY;

  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(angle);
  ctx.drawImage(
    image,
    col * sheet.frameWidth,
    row * sheet.frameHeight,
    sheet.frameWidth,
    sheet.frameHeight,
    -dw / 2,
    -dh / 2,
    dw,
    dh,
  );
  ctx.restore();
}

/** The beat where things are actually falling out. Mirrors `entities.py`. */
const POUR_DUMP = 2;

/**
 * One scratch frame, reused by every wounded body on screen.
 *
 * Grown to the largest sprite frame seen and never shrunk: this is one small
 * canvas for the whole game, and reallocating it per entity per frame would
 * cost more than everything else in this layer put together.
 */
let stainScratch: OffscreenSurface | null = null;

function scratchFor(w: number, h: number): OffscreenSurface {
  if (!stainScratch || stainScratch.canvas.width < w || stainScratch.canvas.height < h) {
    stainScratch = createSurface(
      Math.max(w, stainScratch?.canvas.width ?? 0),
      Math.max(h, stainScratch?.canvas.height ?? 0),
      'entities/stains',
    );
  }
  return stainScratch;
}

/**
 * Wounds, painted ONTO the creature — masked to the sprite's own alpha so no
 * part of a splat can hang in the air beside it.
 *
 * This is the whole difference between blood and a sticker. A wound is
 * composited in the sheet's own 16x16 space first: the marks are stamped on
 * the sprite's pixel grid (so they never straddle a half pixel and shimmer as
 * the camera moves), then `destination-in` against the body frame throws away
 * everything that missed, and only then is the result blown up to the dest
 * rect the body was drawn into. Clipping AFTER the zoom would leave blood on
 * the transparent corners of the frame; clipping before it means the creature
 * is wearing the wound.
 *
 * Masking against the BODY and not the gear on purpose: overlays are
 * registered to the same grid and sit inside that silhouette, so the body is
 * the outline of the whole thing, and a hat is the one piece that pokes out of
 * it — which is not where a chest wound goes anyway.
 *
 * Drawn plainly (no additive, no tint) and dimmed by the creature's own
 * `visibility`: a wound is part of the picture of the creature, not a light on
 * top of it, so it goes into the dark when the creature does.
 */
function drawStains(
  { ctx, gore }: EntityContext,
  target: DrawableEntity,
  image: CanvasImageSource,
  sx: number,
  sy: number,
  w: number,
  h: number,
  dx: number,
  dy: number,
  dw: number,
  dh: number,
): void {
  if (!gore || target.stains.length === 0) return;

  const scratch = scratchFor(w, h);
  const paint = scratch.ctx;
  paint.clearRect(0, 0, w, h);

  const gw = gore.frameWidth;
  const gh = gore.frameHeight;
  for (const stain of target.stains) {
    paint.globalAlpha = stainFade(stain);
    const left = Math.round(w / 2 + stain.u * (w / 2) - gw / 2);
    const top = Math.round(h - stain.v * h - gh / 2);
    const frame = stain.frame * gw;
    if (stain.flip) {
      // Mirrored so six frames read as twelve. Cheap here: only a body that
      // has been hit has stains at all.
      paint.save();
      paint.translate(left + gw, top);
      paint.scale(-1, 1);
      paint.drawImage(gore.image, frame, 0, gw, gh, 0, 0, gw, gh);
      paint.restore();
    } else {
      paint.drawImage(gore.image, frame, 0, gw, gh, left, top, gw, gh);
    }
  }

  // Keep only what landed on the creature.
  paint.globalAlpha = 1;
  paint.globalCompositeOperation = 'destination-in';
  paint.drawImage(image, sx, sy, w, h, 0, 0, w, h);
  paint.globalCompositeOperation = 'source-over';

  ctx.globalAlpha = target.visibility;
  ctx.drawImage(scratch.canvas, 0, 0, w, h, dx, dy, dw, dh);
}

function drawHeldGun(
  { ctx, view, guns }: EntityContext,
  target: DrawableEntity,
  px: number,
  py: number,
): void {
  if (!target.weapon) return;
  if (!guns) {
    drawAimFallback(ctx, view, target, px, py);
    return;
  }
  const spec = guns.items[target.weapon];
  if (!spec) {
    drawAimFallback(ctx, view, target, px, py);
    return;
  }

  const angle = Math.atan2(target.ay, target.ax);
  const flip = target.ax < 0;
  // The atlas row decides how far out the hand is — a rifle is pushed off
  // the chest, the knife is tucked against it — so the weapon has to be
  // passed in, not just its pose.
  const hand = gunHand({
    x: px,
    y: py,
    ax: target.ax,
    ay: target.ay,
    weapon: target.weapon,
    guns,
    pump: target.gunPump,
  });
  const sx = view.rawX(hand.x);
  const sy = view.rawY(hand.y);
  // Per-weapon draw scale, folded into the zoom so the sprite grows and
  // shrinks around the GRIP and the hand does not drift as it scales.
  const zoom = view.zoom * (spec.scale ?? 1);
  const kick = flip ? -target.gunKick : target.gunKick;

  ctx.save();
  ctx.translate(sx, sy);
  ctx.rotate(angle + kick);
  if (flip) ctx.scale(1, -1);
  ctx.globalAlpha = target.visibility;
  ctx.drawImage(
    guns.image,
    spec.frame * guns.frameWidth,
    0,
    guns.frameWidth,
    guns.frameHeight,
    -spec.gripX * zoom,
    -spec.gripY * zoom,
    guns.frameWidth * zoom,
    guns.frameHeight * zoom,
  );
  ctx.restore();
}

function drawAimFallback(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  target: DrawableEntity,
  px: number,
  py: number,
): void {
  const cx = view.rawX(px);
  const cy = view.rawY(py);
  const ts = 16;
  const aim = palette().entity;
  ctx.strokeStyle = target.isLocal ? aim.aimLocal : aim.aimRemote;
  ctx.lineWidth = Math.max(1, view.zoom * 0.7);
  ctx.beginPath();
  ctx.moveTo(cx + view.size(target.ax * ts * 0.4), cy + view.size(target.ay * ts * 0.4));
  ctx.lineTo(cx + view.size(target.ax * ts * 0.75), cy + view.size(target.ay * ts * 0.75));
  ctx.stroke();
}

/**
 * The gauge over a body: health, and under it — for a player — breath.
 *
 * ONE PLATE, TWO ROWS. Both bars live inside the same backdrop, separated by a
 * single pixel of it, because two separately framed meters floating over a head
 * read as HUD stuck to the world rather than as one thing belonging to that
 * body. The run row is inset a pixel on each side and is the quieter colour: it
 * is the LESSER reading, and the one that has to carry across a dark forest at
 * a glance is the one that says somebody is about to die.
 *
 * The plate is anchored by its BOTTOM edge, always the same distance off the
 * head. A player's is two rows tall and an enemy's is one, and a player's stays
 * two rows whether the bar is full or not — geometry that changed with the
 * number would jog the health bar up and down the head every time somebody
 * sprinted, which is exactly the twitch that makes a world-space meter look
 * pasted on.
 */
function drawHealthBar(
  { ctx, view, config }: EntityContext,
  target: DrawableEntity,
  centerX: number,
  spriteTop: number,
): void {
  const ts = config.tileSize;
  const unit = Math.max(1, Math.round(ts * 0.0625) * view.zoom); // 1 world px
  const barW = Math.round(ts * 0.875) * view.zoom;
  const barX = Math.round(centerX - barW / 2);
  const innerW = barW - 2 * unit;
  const runs = target.staminaMax > 0;
  // 1px border, the health row, then — for a body that runs — 1px of backdrop
  // as a separator, the breath row, and the bottom border.
  const plateH = unit * (runs ? 5 : 3);
  const bottom = view.y(spriteTop - ts * 0.125) + unit * 3;
  const plateY = bottom - plateH;

  const ratio = clamp01(target.hp / target.maxHp);
  ctx.fillStyle = palette().entity.barBackdrop;
  ctx.fillRect(barX, plateY, barW, plateH);
  ctx.fillStyle = hpColor(ratio);
  ctx.fillRect(barX + unit, plateY + unit, Math.round(innerW * ratio), unit);

  if (!runs) return;
  const breath = clamp01(target.stamina / target.staminaMax);
  const tone = palette().stamina;
  const runW = innerW - 2 * unit;
  ctx.fillStyle = target.winded ? tone.spent : tone.ready;
  ctx.fillRect(barX + 2 * unit, plateY + unit * 3, Math.round(runW * breath), unit);
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
