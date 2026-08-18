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
import type { MachineAtlas } from '../machine';
import { reelBlur, reelFace } from '../machine';
import type { SkillAtlas } from '../skills';
import { drawCanister } from '../skills';
import type { MachinePull } from '../../game/machine';
import { CAN_THROW, burstProgress, canPose, leverPose, pullGain, reelPose } from '../../game/machine';
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
  kind: 'table' | 'kit' | 'torch' | 'merchant' | 'machine';
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
    // His gear, behind the counter. Drawn exactly like a torch and with no
    // state of its own: nothing here opens, lifts or sells, and the ART is
    // what says so — see the module docstring in make_store.py.
    drawSheet(ctx, view, atlas.kit, piece.variant ?? 0, piece.x, piece.y);
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

  // The three reels. Spinning ones cycle blur frames out of phase; a landed
  // one shows its rarity face and drops a pixel on the bounce, which is what
  // gives the stop weight.
  for (let index = 0; index < atlas.reelSlots.length; index++) {
    const [rx, ry] = atlas.reelSlots[index];
    let frame = index % Math.max(1, atlas.spinFrames);
    let sag = 0;
    if (pull) {
      const pose = reelPose(pull, index);
      if (pose.spinning) {
        frame = reelBlur(atlas, pull.elapsed, index);
      } else {
        frame = reelFace(atlas, pull.rarity);
        if (pose.bounce >= 0) sag = Math.sin(pose.bounce * Math.PI) * 1.4;
      }
    }
    ctx.drawImage(
      atlas.reel.image,
      frame * atlas.reelWidth, 0, atlas.reelWidth, atlas.reelHeight,
      left + rx * zoom, top + (ry + sag) * zoom,
      atlas.reelWidth * zoom, atlas.reelHeight * zoom,
    );
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

  if (pull) {
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
