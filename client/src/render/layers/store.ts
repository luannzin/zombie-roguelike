/**
 * The merchant's clearing, drawn.
 *
 * Only what is HIS is here. The room he is parked in is an ordinary forest map
 * — its soil, grass and trees come from `layers/terrain`, and his torch ring
 * feeds the same light field a cabin lamp does. That is the whole reason the
 * shop stopped being an interior: almost none of it needs special drawing any
 * more.
 *
 * What is left goes in four places in the frame:
 *
 *   MAT          flat on the ground, with the boot prints. Under everybody.
 *   WAGON,       IN the entity sort, merged like scenery: a player walking
 *   COUNTER,     behind the cart has to disappear behind it, and the merchant
 *   TABLES,      is a body standing on the ground like any other. A table
 *   TORCHES,     draws its own goods immediately after itself, so a gun is
 *   MERCHANT     never sorted away from the pedestal it is floating over.
 *   FIRE, GLOW   additive, after the darkness pass, like every other light.
 *   PRICES       last. A price tag is a thing the MERCHANT is telling you, not
 *                an object in the clearing, so nothing in the clearing may
 *                occlude it — and it carries the item's NAME in its rarity
 *                colour, because six tables in a grid with six numbers over
 *                them is a spreadsheet until you can tell them apart.
 *
 * THE GOODS FLOAT. A gun on a table you are standing at lifts off the boards
 * and BREATHES there — it does not rise to a fixed offset and stop, because a
 * sprite parked in mid-air is a bug and one that is still moving is an offer.
 * The pool underneath (`glow`) is the other half of the same statement.
 */

import type { Projection } from '../projection';
import type { GunAtlas } from '../guns';
import type { MerchantAtlas, MerchantPose } from '../merchant';
import { merchantFrame } from '../merchant';
import type { StoreAtlas } from '../store';
import { COIN_PX, tableTopY, torchFlameY } from '../store';
import type { MachineAtlas } from '../machine';
import { bandCell } from '../machine';
import type { SkillAtlas } from '../skills';
import { drawCanister } from '../skills';
import type { MachinePull } from '../../game/machine';
import {
  CAN_THROW,
  burstProgress,
  canPose,
  leverPose,
  payLineFlash,
  pullGain,
  reelScroll,
} from '../../game/machine';
import { palette } from '../../theme/palette';
import { hudFont } from '../../theme/fonts';
import type { StoreFixtures, Stand } from '../../game/world';

/** Price tag geometry, in screen pixels. */
const PRICE_TEXT_PX = 11;
const NAME_TEXT_PX = 10;
const PRICE_PAD_X = 4;
const PRICE_CARD_H = 14;
const NAME_ROW_H = 12;
const PRICE_GAP = 3;
/** How far above the table's surface the tag floats, in world pixels. */
const PRICE_LIFT = 20;

/**
 * How fast the goods breathe on a table you are standing at, in radians a
 * second, and how much of the lift the breath is.
 *
 * SLOW AND SHALLOW. The lift is what says "this is being offered"; the breath
 * is what stops the lift reading as a sprite that got stuck one row too high.
 * Anything faster than this is a bobbing collectible out of a different game.
 */
const FLOAT_RATE = 2.6;
const FLOAT_DEPTH = 0.28;

/** How long the pay line stays lit after the third reel lands, in seconds. */
const PAY_LINE_FLASH = 0.55;

/** One thing on the pitch that stands up and has to be depth-sorted. */
export interface StoreStanding {
  kind: 'table' | 'kit' | 'wagon' | 'counter' | 'torch' | 'merchant' | 'machine';
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
  /**
   * The lever pull running right now, or null. It is the CLIENT's own copy of
   * a ceremony the server resolved in one frame — see `game/machine.ts`.
   */
  pull: MachinePull | null;
  /**
   * 0..1: how much the cabinet is inviting the local player. It is 1 when they
   * are holding an unspent level and 0 when they are not, and it drives the
   * marquee's brightness and nothing else.
   *
   * THIS IS THE WORLD DOING THE TUTORIAL. A machine that burns harder the
   * moment you have something to spend on it says "this is for you" from the
   * far end of the glade, before any prompt, before any tooltip — which is the
   * one thing a HUD line could never do at that distance.
   */
  invite: number;
  /** Skill icon frame per catalog key, straight off `config.skills`. */
  iconOf: (key: string) => number;
  /**
   * The catalog row behind a stall's key: what to call it and what colour to
   * say it in. Straight off `config.loot`, so the shop and the buy tooltip
   * name the same gun the same way.
   */
  labelOf: (key: string) => { name: string; rarity: string };
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
  for (const piece of scene.fixtures.kit) {
    out.push({ kind: 'kit', x: piece.x, y: piece.y, variant: piece.variant });
  }
  if (scene.fixtures.wagonX !== null && scene.fixtures.wagonY !== null) {
    out.push({ kind: 'wagon', x: scene.fixtures.wagonX, y: scene.fixtures.wagonY });
  }
  if (scene.fixtures.counterX !== null && scene.fixtures.counterY !== null) {
    out.push({ kind: 'counter', x: scene.fixtures.counterX, y: scene.fixtures.counterY });
  }
  out.push({
    kind: 'merchant',
    x: scene.fixtures.merchantX,
    y: scene.fixtures.merchantY,
  });
  if (scene.fixtures.machineX !== null && scene.fixtures.machineY !== null) {
    out.push({
      kind: 'machine',
      x: scene.fixtures.machineX,
      y: scene.fixtures.machineY,
    });
  }
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

/** One table (with its stock), one torch, the merchant, or the machine. */
export function drawStoreProp(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  atlas: StoreAtlas,
  guns: GunAtlas | null,
  merchant: MerchantAtlas | null,
  piece: StoreStanding,
  scene: StoreScene,
  liftPx: number,
  machine: MachineAtlas | null,
  skills: SkillAtlas | null,
  time: number,
): void {
  if (piece.kind === 'merchant') {
    drawMerchant(ctx, view, merchant, scene, piece);
    return;
  }
  if (piece.kind === 'machine') {
    drawMachine(ctx, view, machine, skills, scene, piece);
    return;
  }
  if (piece.kind === 'kit') {
    // His gear, on his side of the room. Drawn exactly like a torch and with
    // no state of its own: nothing here opens, lifts or sells, and the ART is
    // what says so — see the module docstring in make_store.py.
    drawSheet(ctx, view, atlas.kit, piece.variant ?? 0, piece.x, piece.y);
    return;
  }
  if (piece.kind === 'wagon') {
    // One frame, no state. It is the backdrop the pitch is arranged against.
    drawSheet(ctx, view, atlas.wagon, 0, piece.x, piece.y);
    return;
  }
  if (piece.kind === 'counter') {
    drawSheet(ctx, view, atlas.counter, 0, piece.x, piece.y);
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
  const lift = standLift(stand.id === scene.nearId, liftPx, time) * zoom;
  ctx.drawImage(
    guns.image,
    gun.frame * guns.frameWidth, 0, guns.frameWidth, guns.frameHeight,
    view.x(piece.x) - Math.round((guns.frameWidth * zoom) / 2),
    Math.round(surface - guns.frameHeight * zoom - lift),
    guns.frameWidth * zoom,
    guns.frameHeight * zoom,
  );
}

/**
 * How far the goods on one table are off its boards right now, in world pixels.
 *
 * ZERO WHEN NOBODY IS AT IT, and everything else is the breath. The lift is
 * not eased in from zero on the frame the player walks into range: it snaps to
 * the bottom of the breath and starts rising, which is a smaller lie than a
 * ramp (the item is only ever a couple of pixels out) and reads as the table
 * answering rather than as an animation starting.
 */
function standLift(near: boolean, liftPx: number, time: number): number {
  if (!near) return 0;
  return liftPx * (1 - FLOAT_DEPTH + FLOAT_DEPTH * Math.sin(time * FLOAT_RATE));
}

/**
 * The cabinet, its reels, its arm and whatever is sitting in its tray.
 *
 * ONE CALL, because the parts are pinned to the body's own frame: the reel
 * windows and the lever pivot are offsets the ART ships (`machine.reelSlots`,
 * `machine.leverAnchor`), so drawing them anywhere else would mean a second
 * opinion about where the front panel is.
 *
 * The canister is drawn HERE rather than with the effects for the same reason
 * the gun on a table is drawn with the table: it is lying on the machine, and
 * a sort that could put a body between a tray and the thing in it would be
 * visibly wrong from the first frame.
 */
function drawMachine(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  atlas: MachineAtlas | null,
  skills: SkillAtlas | null,
  scene: StoreScene,
  piece: StoreStanding,
): void {
  if (!atlas) return;
  const zoom = view.zoom;
  const cab = atlas.cabinet;
  const pull = scene.pull;
  // Frame 1 is the shell settled a pixel lower on its feet. It is only used
  // while the arm is actually down — the cabinet takes the hit and comes back
  // up, which is the difference between a machine that was pulled and a
  // picture of a machine.
  const body = pull && pull.elapsed < pull.timing.claim ? 1 : 0;
  const left = view.x(piece.x) - Math.round((cab.frameWidth * zoom) / 2);
  const top = view.y(piece.y) - cab.frameHeight * zoom;
  ctx.drawImage(
    cab.image,
    body * cab.frameWidth, 0, cab.frameWidth, cab.frameHeight,
    left, top, cab.frameWidth * zoom, cab.frameHeight * zoom,
  );

  // THE THREE BANDS. Each window is a scrolling view onto one tall strip, so a
  // spin is a strip going past rather than a frame index changing — see
  // `reelScroll`. An idle machine parks each band on a different cell, which
  // is what makes an unpulled cabinet read as three reels instead of one
  // pattern printed three times.
  for (let index = 0; index < atlas.reelSlots.length; index++) {
    const [rx, ry] = atlas.reelSlots[index];
    const dx = left + rx * zoom;
    const dy = top + ry * zoom;
    if (!pull) {
      drawBand(ctx, atlas, index * 3 + 1, dx, dy, zoom, 0);
      continue;
    }
    const landing = bandCell(atlas, pull.rarity, index);
    const pose = reelScroll(pull, index, atlas.reelHeight, atlas.bandCells, landing);
    drawBand(ctx, atlas, pose.offset / atlas.reelHeight, dx, dy, zoom, pose.speed);
  }

  // The arm. `leverPose` is 0..1 and the sheet's frames are the sweep, so the
  // only thing here is picking the nearest one.
  const arm = leverPose(pull);
  const lever = atlas.lever;
  const armFrame = Math.min(lever.frames - 1, Math.round(arm * (lever.frames - 1)));
  const [ax, ay] = atlas.leverAnchor;
  const [px, py] = atlas.leverPivot;
  ctx.drawImage(
    lever.image,
    armFrame * lever.frameWidth, 0, lever.frameWidth, lever.frameHeight,
    left + (ax - px) * zoom, top + (ay - py) * zoom,
    lever.frameWidth * zoom, lever.frameHeight * zoom,
  );

  if (!pull || !skills) return;
  const can = canPose(pull);
  if (!can) return;
  const [tx, ty] = atlas.trayMouth;
  // Out of the hole and to the right, so it lands clear of the tray lip
  // instead of on top of it. A canister that settled inside the slot it came
  // out of would read as never having been delivered.
  const cx = left + (tx + can.travel * CAN_THROW) * zoom;
  const cy = top + (ty - can.lift) * zoom;
  ctx.globalAlpha = can.claimed ? Math.max(0, 1 - (can.lift - 0) / 26) : 1;
  drawCanister(
    ctx,
    skills,
    pull.rarity,
    scene.iconOf(pull.key),
    cx,
    cy,
    zoom,
    // Breathes while it is sitting there being looked at, and the breath is
    // bigger the better the pull was.
    pullGain(pull) * (0.7 + 0.3 * Math.sin(pull.elapsed * 7)),
  );
  ctx.globalAlpha = 1;
}

/**
 * One reel window: a `reelHeight` slice of the band at `cells` cells down it.
 *
 * TWO BLITS, because the window wraps. The strip has no ends — the last cell is
 * followed by the first — so a view that straddles the seam is the bottom of
 * the sheet and then the top of it, and the alternative (a sheet with a
 * duplicate cell glued on) is a second copy of the art that has to be kept in
 * step with the first.
 *
 * THE BLUR IS THE SAME DRAW AGAIN, offset by how far the band travels in a
 * frame and faded by how fast it is going. It costs one more blit per reel and
 * it is the entire difference between a strip that is moving and a strip that
 * is teleporting: at full speed the cells smear into each other, and as the
 * reel slows the smear closes up until the last few faces go past one at a
 * time, readable, which is the beat the whole ceremony is built around.
 */
function drawBand(
  ctx: CanvasRenderingContext2D,
  atlas: MachineAtlas,
  cells: number,
  dx: number,
  dy: number,
  zoom: number,
  speed: number,
): void {
  const cellH = atlas.reelHeight;
  const bandH = Math.max(1, atlas.bandCells * cellH);
  const width = atlas.reelWidth;

  const blit = (offset: number, alpha: number) => {
    const from = ((offset % bandH) + bandH) % bandH;
    const first = Math.min(cellH, bandH - from);
    ctx.globalAlpha = alpha;
    ctx.drawImage(
      atlas.strip.image,
      0, from, width, first,
      dx, dy, width * zoom, first * zoom,
    );
    if (first < cellH) {
      ctx.drawImage(
        atlas.strip.image,
        0, 0, width, cellH - first,
        dx, dy + first * zoom, width * zoom, (cellH - first) * zoom,
      );
    }
  };

  const base = cells * cellH;
  blit(base, 1);
  if (speed > 0.02) {
    // Half a cell of smear at full tilt. More than that and the band stops
    // reading as a band; less and a spinning reel looks like a still.
    const smear = speed * cellH * 0.5;
    blit(base - smear, speed * 0.5);
    blit(base + smear, speed * 0.35);
  }
  ctx.globalAlpha = 1;
}

/** One bottom-anchored frame out of a store sheet, at a contact point. */
function drawSheet(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  sheet: { image: HTMLImageElement; frameWidth: number; frameHeight: number; frames: number },
  variant: number,
  x: number,
  y: number,
): void {
  const frame = ((variant % sheet.frames) + sheet.frames) % sheet.frames;
  const zoom = view.zoom;
  ctx.drawImage(
    sheet.image,
    frame * sheet.frameWidth, 0, sheet.frameWidth, sheet.frameHeight,
    view.x(x) - Math.round((sheet.frameWidth * zoom) / 2),
    view.y(y) - sheet.frameHeight * zoom,
    sheet.frameWidth * zoom,
    sheet.frameHeight * zoom,
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
 * The tag over each table: what it is, in its rarity colour, and what it costs.
 *
 * Drawn LAST, in screen space — because a price is something the merchant is
 * telling you rather than an object in the clearing, and a tree in front of it
 * must never hide it. It is on the world for the same reason the loot tooltip
 * is: the answer to "what is that and what does it cost" has to be readable
 * from the middle of the room, before you have walked to anything.
 *
 * THE NAME IS ON IT NOW, and that is what the grid cost. Four tables strung
 * along a lane could be read as a sequence — you walked past them in order and
 * the prices climbed. Six in a square are compared at a glance and at a
 * distance, and six bare numbers over six identical pedestals is a puzzle: the
 * stock is rolled WITH REPLACEMENT, so two of them really can be the same gun
 * at two prices, and the only way to see that from across the clearing is to
 * write it down. The rarity colour does the rest of the work — it is the same
 * ladder loot already uses, so "the purple one is the good one" needs no
 * second language.
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

  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';

  for (const stand of scene.fixtures.stands) {
    if (stand.sold) continue;
    const frame = stand.variant % table.frames;
    const surface = stand.y - table.frameHeight + tableTopY(table, frame);
    const cx = view.x(stand.x);
    const bottom = view.y(surface - PRICE_LIFT);
    const card = PRICE_CARD_H + NAME_ROW_H;
    const top = bottom - card;

    const item = scene.labelOf(stand.key);
    const label = String(stand.price);

    ctx.font = hudFont(PRICE_TEXT_PX);
    const priceWidth = Math.ceil(ctx.measureText(label).width);
    ctx.font = hudFont(NAME_TEXT_PX);
    const nameWidth = Math.ceil(ctx.measureText(item.name).width);
    const coinWidth = atlas.coin ? COIN_PX + PRICE_GAP : 0;
    const width = PRICE_PAD_X * 2 + Math.max(coinWidth + priceWidth, nameWidth);
    const left = Math.round(cx - width / 2);

    const afford = stand.price <= balance;
    const near = stand.id === scene.nearId;

    ctx.globalAlpha = near ? 0.94 : 0.82;
    ctx.fillStyle = tone.panelInset;
    ctx.fillRect(left, top, width, card);
    // Border as four fills rather than a stroke: at this size a 1px stroke
    // straddles the path and comes out as two half-lit rows.
    ctx.globalAlpha = near ? 0.95 : 0.5;
    ctx.fillStyle = tone.panelBorder;
    ctx.fillRect(left, top, width, 1);
    ctx.fillRect(left, bottom - 1, width, 1);
    ctx.fillRect(left, top, 1, card);
    ctx.fillRect(left + width - 1, top, 1, card);
    // The hairline between the two rows. It is what stops a name and a number
    // in different colours reading as one string that changed its mind.
    ctx.globalAlpha = near ? 0.55 : 0.3;
    ctx.fillRect(left + 1, top + NAME_ROW_H, width - 2, 1);

    ctx.globalAlpha = near ? 1 : 0.85;
    ctx.font = hudFont(NAME_TEXT_PX);
    ctx.fillStyle = rarityInk(item.rarity);
    ctx.fillText(
      item.name,
      left + Math.round((width - nameWidth) / 2),
      top + NAME_ROW_H - Math.round((NAME_ROW_H - NAME_TEXT_PX) / 2) - 1,
    );

    ctx.globalAlpha = afford ? 1 : 0.45;
    if (atlas.coin) {
      ctx.drawImage(
        atlas.coin, 0, 0, COIN_PX, COIN_PX,
        left + PRICE_PAD_X,
        top + NAME_ROW_H + Math.round((PRICE_CARD_H - COIN_PX) / 2),
        COIN_PX, COIN_PX,
      );
    }
    ctx.font = hudFont(PRICE_TEXT_PX);
    ctx.fillStyle = afford ? tone.ink : tone.inkMuted;
    ctx.fillText(
      label,
      left + PRICE_PAD_X + coinWidth,
      bottom - Math.round((PRICE_CARD_H - PRICE_TEXT_PX) / 2) - 2,
    );
  }
  ctx.globalAlpha = 1;
}

/** One rarity ink as a CSS colour, out of the same tokens the HUD uses. */
function rarityInk(rarity: string): string {
  const [r, g, b] = rarityTone(rarity);
  return `rgb(${r} ${g} ${b})`;
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
  machine: MachineAtlas | null,
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

  drawMachineLight(ctx, machine, scene, time);

  ctx.globalCompositeOperation = previous;
}

/**
 * The cabinet's own light: the crown chasing, the backlight behind the reels,
 * and the payout flash.
 *
 * ALL THREE ARE GREYSCALE SHEETS AND ALL THREE ARE TINTED HERE, which is what
 * lets one marquee sheet say two different things. Idle, it burns
 * `--scene-neon` — the only electric colour in the game, so a party reads
 * "there is a machine down there" off a colour they have seen nowhere else.
 * Mid-pull it burns the WINNING RARITY, so the light coming off the cabinet is
 * already telling the glade what came out before the canister has cleared the
 * tray. The tint is the whole payload; the sheet never changes.
 *
 * The burst is scaled by `pullGain`, which is the rarity ladder and nothing
 * else: a legendary throws a wider, brighter version of exactly the ring a
 * common throws. Five hand-authored flashes would be five things to learn.
 */
function drawMachineLight(
  ctx: CanvasRenderingContext2D,
  atlas: MachineAtlas | null,
  scene: StoreScene,
  time: number,
): void {
  if (!atlas) return;
  const { machineX, machineY } = scene.fixtures;
  if (machineX === null || machineY === null) return;

  const cab = atlas.cabinet;
  const originX = machineX - cab.frameWidth / 2;
  const originY = machineY - cab.frameHeight;
  const pull = scene.pull;
  const tone = palette();
  const rarity = pull ? rarityTone(pull.rarity) : tone.scene.neon;

  // The reels' backlight. Steady, and only really visible once the glade is
  // dark around it — it is a lamp behind glass, not a signal.
  const win = atlas.window;
  const [firstX, firstY] = atlas.reelSlots[0] ?? [0, 0];
  const winStep = Math.floor(time * win.fps) % win.frames;
  ctx.globalAlpha = 0.85;
  tinted(ctx, win.image, winStep * win.frameWidth, win.frameWidth, win.frameHeight,
    Math.round(originX + firstX - 1), Math.round(originY + firstY - 1), rarity);

  // The crown. `invite` is the local player holding an unspent level: the
  // machine burns harder for somebody who can use it, which is the world doing
  // the job a tutorial line would otherwise be asked to do.
  const marquee = atlas.marquee;
  const step = Math.floor(time * marquee.fps * (1 + scene.invite * 0.6)) % marquee.frames;
  const [crownX, crownY] = atlas.crown;
  ctx.globalAlpha = 0.55 + scene.invite * 0.45;
  tinted(ctx, marquee.image, step * marquee.frameWidth, marquee.frameWidth, marquee.frameHeight,
    Math.round(originX + crownX - marquee.frameWidth / 2),
    Math.round(originY + crownY - marquee.anchorY),
    rarity);

  // THE PAY LINE. Three windows agreeing on one row is the rule a slot machine
  // has, and until now nothing on this cabinet ever said the row had happened:
  // the burst fired at the TRAY, which is where the prize comes out rather than
  // where it was decided. A bar across all three windows on the frame the last
  // reel lands is the machine reacting to its own result, and the burst below
  // is the consequence of it.
  if (pull) {
    const flash = payLineFlash(pull, PAY_LINE_FLASH);
    if (flash >= 0) {
      const fade = (1 - flash) ** 1.5;
      const height = 1 + pullGain(pull) * 2.5;
      const [firstX] = atlas.reelSlots[0] ?? [0, 0];
      const [lastX] = atlas.reelSlots[atlas.reelSlots.length - 1] ?? [0, 0];
      const span = lastX + atlas.reelWidth - firstX;
      ctx.globalAlpha = Math.min(1, fade * pullGain(pull));
      ctx.fillStyle = `rgb(${rarity[0]} ${rarity[1]} ${rarity[2]})`;
      ctx.fillRect(
        Math.round(originX + firstX - 1),
        Math.round(originY + atlas.payLine - height / 2),
        span + 2,
        Math.max(1, Math.round(height)),
      );
    }

    const burst = atlas.burst;
    const seconds = burst.frames / burst.fps;
    const progress = burstProgress(pull, seconds);
    if (progress >= 0) {
      const gain = pullGain(pull);
      const frame = Math.min(burst.frames - 1, Math.floor(progress * burst.frames));
      const size = burst.frameWidth * (0.6 + gain * 0.7);
      const [tx, ty] = atlas.trayMouth;
      ctx.globalAlpha = Math.min(1, gain);
      tinted(ctx, burst.image, frame * burst.frameWidth, burst.frameWidth, burst.frameHeight,
        Math.round(originX + tx - size / 2), Math.round(originY + ty - size / 2),
        rarity, size);
    }
  }
  ctx.globalAlpha = 1;
}

/**
 * Blit one greyscale frame through a colour.
 *
 * An offscreen tint canvas would be the tidy way and it is the wrong one here:
 * the sheets are small, this runs a few times a frame, and every other
 * additive pass in this renderer draws its sheet straight. `globalCompositeOperation`
 * is already `lighter` when this is called, so a greyscale sheet multiplied by
 * a fill is exactly what a coloured light looks like.
 */
function tinted(
  ctx: CanvasRenderingContext2D,
  image: HTMLImageElement,
  sx: number,
  sw: number,
  sh: number,
  dx: number,
  dy: number,
  tone: readonly number[],
  size?: number,
): void {
  const w = size ?? sw;
  const h = size ?? sh;
  const buffer = tintBuffer(sw, sh);
  if (!buffer) {
    ctx.drawImage(image, sx, 0, sw, sh, dx, dy, w, h);
    return;
  }
  const { canvas, ctx: bctx } = buffer;
  bctx.clearRect(0, 0, sw, sh);
  bctx.globalCompositeOperation = 'source-over';
  bctx.drawImage(image, sx, 0, sw, sh, 0, 0, sw, sh);
  bctx.globalCompositeOperation = 'multiply';
  bctx.fillStyle = `rgb(${tone[0]} ${tone[1]} ${tone[2]})`;
  bctx.fillRect(0, 0, sw, sh);
  // Multiply also paints the transparent pixels, so the alpha of the sheet has
  // to be put back or the tint arrives as a solid rectangle.
  bctx.globalCompositeOperation = 'destination-in';
  bctx.drawImage(image, sx, 0, sw, sh, 0, 0, sw, sh);
  ctx.drawImage(canvas, 0, 0, sw, sh, dx, dy, w, h);
}

/**
 * One scratch canvas, grown to the largest frame anybody has asked for.
 *
 * Reused rather than allocated per call: this runs up to three times a frame
 * for the whole time a party is in the shop, and a fresh canvas each time is
 * the classic way to make a garbage collector visible in a frame graph.
 */
let tintCanvas: HTMLCanvasElement | null = null;
let tintCtx: CanvasRenderingContext2D | null = null;

function tintBuffer(
  width: number,
  height: number,
): { canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D } | null {
  if (typeof document === 'undefined') return null;
  if (!tintCanvas) {
    tintCanvas = document.createElement('canvas');
    tintCtx = tintCanvas.getContext('2d');
  }
  if (!tintCanvas || !tintCtx) return null;
  if (tintCanvas.width < width || tintCanvas.height < height) {
    tintCanvas.width = Math.max(tintCanvas.width, width);
    tintCanvas.height = Math.max(tintCanvas.height, height);
  }
  tintCtx.imageSmoothingEnabled = false;
  return { canvas: tintCanvas, ctx: tintCtx };
}

/** The five rarity colours, as channels, out of the same tokens the HUD uses. */
function rarityTone(rarity: string): readonly number[] {
  const glow = palette().rarityGlow as Record<string, readonly number[]>;
  return glow[rarity] ?? palette().scene.neon;
}
