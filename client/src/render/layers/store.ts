/**
 * The merchant's camp, drawn.
 *
 * Only his own kit is here. The glade he is standing in is an ordinary forest
 * map — its soil, grass and trees come from `layers/terrain`, his tent is a
 * scenery prop in the standing sort, and his torches feed the same light field
 * a cabin lamp does. That is the whole reason the camp stopped being an
 * interior: almost none of it needs special drawing any more.
 *
 * What is left goes in four places in the frame:
 *
 *   MAT          flat on the ground, with the boot prints. Under everybody.
 *   TABLES,      IN the entity sort, merged like scenery: a player walking
 *   TORCHES,     behind a table has to disappear behind it, and the merchant
 *   MERCHANT     is a body standing on the ground like any other. A table
 *                draws its own stock immediately after itself, so a gun is
 *                never sorted away from what it is lying on.
 *   FIRE, GLOW   additive, after the darkness pass, like every other light.
 *   PRICES       last, with the name labels. A price tag is a thing the
 *                MERCHANT is telling you, not an object in the clearing, so
 *                nothing in the clearing may occlude it.
 */

import type { Projection } from '../projection';
import type { GunAtlas } from '../guns';
import type { MerchantAtlas, MerchantPose } from '../merchant';
import { merchantFrame } from '../merchant';
import type { StoreAtlas } from '../store';
import { COIN_PX, tableTopY, torchFlameY } from '../store';
import { palette } from '../../theme/palette';
import { hudFont } from '../../theme/fonts';
import type { StoreFixtures, Stand } from '../../game/world';

/** Price tag geometry, in screen pixels. */
const PRICE_TEXT_PX = 11;
const PRICE_PAD_X = 4;
const PRICE_CARD_H = 14;
const PRICE_GAP = 3;
/** How far above the table's surface the tag floats, in world pixels. */
const PRICE_LIFT = 13;

/** One thing on the pitch that stands up and has to be depth-sorted. */
export interface StoreStanding {
  kind: 'table' | 'torch' | 'merchant';
  /** Contact row, world pixels — what it is sorted by. */
  y: number;
  x: number;
  /** Tables only. */
  stand?: Stand;
  /** Torches only. */
  variant?: number;
}

/**
 * What the camp is doing this frame. Null on every other map.
 *
 * `nearId` is the stall the local player is close enough to buy from, decided
 * in `Game` against the same reach the server checks. It drives BOTH the lift
 * and the pool under the weapon, because they are two halves of one statement.
 */
export interface StoreScene {
  fixtures: StoreFixtures;
  pose: MerchantPose;
  nearId: string | null;
}

/** Everything that goes into the entity depth sort, in ascending contact. */
export function storeStanding(scene: StoreScene | null): StoreStanding[] {
  if (!scene) return [];
  const out: StoreStanding[] = scene.fixtures.stands.map((stand) => ({
    kind: 'table' as const,
    x: stand.x,
    y: stand.y,
    stand,
  }));
  for (const torch of scene.fixtures.torches) {
    out.push({ kind: 'torch', x: torch.x, y: torch.y, variant: torch.variant });
  }
  out.push({
    kind: 'merchant',
    x: scene.fixtures.merchantX,
    y: scene.fixtures.merchantY,
  });
  out.sort((a, b) => a.y - b.y);
  return out;
}

/** The mat. Flat, world space, drawn with the ground. */
export function drawStoreFloor(
  ctx: CanvasRenderingContext2D,
  atlas: StoreAtlas | null,
  scene: StoreScene | null,
): void {
  if (!atlas || !scene) return;
  const rug = atlas.rug;
  ctx.drawImage(
    rug.image,
    0, 0, rug.frameWidth, rug.frameHeight,
    Math.round(scene.fixtures.rugX - rug.frameWidth / 2),
    Math.round(scene.fixtures.rugY - rug.frameHeight / 2),
    rug.frameWidth,
    rug.frameHeight,
  );
}

/** One table (with its stock), one torch, or the merchant. From the sort. */
export function drawStoreProp(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  atlas: StoreAtlas,
  guns: GunAtlas | null,
  merchant: MerchantAtlas | null,
  piece: StoreStanding,
  scene: StoreScene,
  liftPx: number,
): void {
  if (piece.kind === 'merchant') {
    drawMerchant(ctx, view, merchant, scene, piece);
    return;
  }
  if (piece.kind === 'torch') {
    const torch = atlas.torch;
    const frame = (piece.variant ?? 0) % torch.frames;
    const zoom = view.zoom;
    ctx.drawImage(
      torch.image,
      frame * torch.frameWidth, 0, torch.frameWidth, torch.frameHeight,
      view.x(piece.x) - Math.round((torch.frameWidth * zoom) / 2),
      view.y(piece.y) - torch.frameHeight * zoom,
      torch.frameWidth * zoom,
      torch.frameHeight * zoom,
    );
    return;
  }
  const stand = piece.stand;
  if (!stand) return;

  const table = atlas.table;
  const frame = stand.variant % table.frames;
  const zoom = view.zoom;
  const left = view.x(piece.x) - Math.round((table.frameWidth * zoom) / 2);
  const top = view.y(piece.y) - table.frameHeight * zoom;
  ctx.drawImage(
    table.image,
    frame * table.frameWidth, 0, table.frameWidth, table.frameHeight,
    left, top, table.frameWidth * zoom, table.frameHeight * zoom,
  );

  if (stand.sold || !guns) return;
  const gun = guns.items[stand.key];
  if (!gun) return;
  // The row this table's surface is at, out of the ART. `topY` is measured from
  // the table frame's own top edge, so it has to be added to where that edge
  // landed on screen rather than to the contact.
  const surface = top + tableTopY(table, frame) * zoom;
  const lift = stand.id === scene.nearId ? liftPx * zoom : 0;
  ctx.drawImage(
    guns.image,
    gun.frame * guns.frameWidth, 0, guns.frameWidth, guns.frameHeight,
    view.x(piece.x) - Math.round((guns.frameWidth * zoom) / 2),
    Math.round(surface - guns.frameHeight * zoom - lift),
    guns.frameWidth * zoom,
    guns.frameHeight * zoom,
  );
}

function drawMerchant(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  atlas: MerchantAtlas | null,
  scene: StoreScene,
  piece: StoreStanding,
): void {
  if (!atlas) return;
  const frame = merchantFrame(scene.pose, atlas);
  if (!frame) return;
  const zoom = view.zoom;
  ctx.drawImage(
    frame.image,
    frame.sx, 0, atlas.frameWidth, atlas.frameHeight,
    view.x(piece.x) - Math.round(atlas.frameWidth * atlas.anchorX * zoom),
    view.y(piece.y) - atlas.frameHeight * atlas.anchorY * zoom,
    atlas.frameWidth * zoom,
    atlas.frameHeight * zoom,
  );
}

/**
 * The price over each table: a coin and a number.
 *
 * Drawn LAST, in screen space, with the name labels — because a price is
 * something the merchant is telling you rather than an object in the clearing,
 * and a tree in front of it must never hide it. It is on the world for the
 * same reason the loot tooltip is: the answer to "what does that cost" has to
 * be readable from down the glade, before you have walked to anything, or the
 * zone becomes four identical tables you have to visit to compare.
 *
 * AFFORDABILITY IS IN THE COLOUR. A price the party cannot meet is drawn muted
 * rather than hidden or struck through: it is still the information, and a
 * shop that greys out its own stock is telling you what to want. A sold table
 * draws nothing at all — the gap is the message.
 */
export function drawStorePrices(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  atlas: StoreAtlas | null,
  scene: StoreScene | null,
  balance: number,
): void {
  if (!atlas || !scene) return;
  const tone = palette();
  const table = atlas.table;

  ctx.font = hudFont(PRICE_TEXT_PX);
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';

  for (const stand of scene.fixtures.stands) {
    if (stand.sold) continue;
    const frame = stand.variant % table.frames;
    const surface = stand.y - table.frameHeight + tableTopY(table, frame);
    const cx = view.x(stand.x);
    const bottom = view.y(surface - PRICE_LIFT);
    const top = bottom - PRICE_CARD_H;

    const label = String(stand.price);
    const textWidth = Math.ceil(ctx.measureText(label).width);
    const coinWidth = atlas.coin ? COIN_PX + PRICE_GAP : 0;
    const width = PRICE_PAD_X * 2 + coinWidth + textWidth;
    const left = Math.round(cx - width / 2);

    const afford = stand.price <= balance;
    const near = stand.id === scene.nearId;

    ctx.globalAlpha = near ? 0.94 : 0.82;
    ctx.fillStyle = tone.panelInset;
    ctx.fillRect(left, top, width, PRICE_CARD_H);
    // Border as four fills rather than a stroke: at this size a 1px stroke
    // straddles the path and comes out as two half-lit rows.
    ctx.globalAlpha = near ? 0.95 : 0.5;
    ctx.fillStyle = tone.panelBorder;
    ctx.fillRect(left, top, width, 1);
    ctx.fillRect(left, bottom - 1, width, 1);
    ctx.fillRect(left, top, 1, PRICE_CARD_H);
    ctx.fillRect(left + width - 1, top, 1, PRICE_CARD_H);

    ctx.globalAlpha = afford ? 1 : 0.45;
    if (atlas.coin) {
      ctx.drawImage(
        atlas.coin, 0, 0, COIN_PX, COIN_PX,
        left + PRICE_PAD_X,
        top + Math.round((PRICE_CARD_H - COIN_PX) / 2),
        COIN_PX, COIN_PX,
      );
    }
    ctx.fillStyle = afford ? tone.ink : tone.inkMuted;
    ctx.fillText(
      label,
      left + PRICE_PAD_X + coinWidth,
      bottom - Math.round((PRICE_CARD_H - PRICE_TEXT_PX) / 2) - 2,
    );
  }
  ctx.globalAlpha = 1;
}

/**
 * The torches burning, and the pool under the weapon E is offering.
 *
 * Additive, after the darkness pass. The torches are what make this clearing
 * navigable at all — the lantern is off here and the glade is a forest at
 * night, so the line of fires down the lane is both the light and the
 * direction. Their POOLS come from the map's own light rows (they are
 * `SceneLight`s like any cabin lamp); this is the visible flame on top.
 */
export function drawStoreLight(
  ctx: CanvasRenderingContext2D,
  atlas: StoreAtlas | null,
  scene: StoreScene | null,
  time: number,
): void {
  if (!atlas || !scene) return;
  const previous = ctx.globalCompositeOperation;
  ctx.globalCompositeOperation = 'lighter';

  const fire = atlas.torchfire;
  const torch = atlas.torch;
  scene.fixtures.torches.forEach((row, index) => {
    // Offset per torch: a row of fires playing the same frame at the same
    // instant reads as copies of one sprite, which is what they are and what
    // the eye must not notice. Same trick the exit torches use.
    const step = Math.floor(time * fire.fps + index * 3) % fire.frames;
    const variant = row.variant % torch.frames;
    const flame = torchFlameY(torch, variant);
    ctx.drawImage(
      fire.image,
      step * fire.frameWidth, 0, fire.frameWidth, fire.frameHeight,
      Math.round(row.x - fire.frameWidth / 2),
      Math.round(row.y - torch.frameHeight + flame - fire.anchorY),
      fire.frameWidth,
      fire.frameHeight,
    );
  });

  if (scene.nearId !== null) {
    const stand = scene.fixtures.stands.find((row) => row.id === scene.nearId);
    if (stand && !stand.sold) {
      const glow = atlas.glow;
      const table = atlas.table;
      const frame = stand.variant % table.frames;
      const surface = stand.y - table.frameHeight + tableTopY(table, frame);
      const step = Math.floor(time * glow.fps) % glow.frames;
      ctx.drawImage(
        glow.image,
        step * glow.frameWidth, 0, glow.frameWidth, glow.frameHeight,
        Math.round(stand.x - glow.frameWidth / 2),
        Math.round(surface - glow.anchorY),
        glow.frameWidth,
        glow.frameHeight,
      );
    }
  }

  ctx.globalCompositeOperation = previous;
}
