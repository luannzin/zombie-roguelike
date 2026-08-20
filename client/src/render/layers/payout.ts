/**
 * The payout, drawn: the night's platforms coming home, and the gold coming
 * off them.
 *
 * Three passes, in the three places this renderer already puts things:
 *
 *   RIGS      world space, with the props. The skid descending, its shadow
 *             shrinking under it, and the four aircraft holding it — all off
 *             the same `/platform/` atlas the extraction uses, because it is
 *             the same machinery doing the same job in the other direction.
 *   LIGHT     additive, after the darkness pass. Rotor discs, nav strobes and
 *             the wash a rig throws at a metre off the deck.
 *   COINS     SCREEN space, last. See `drawPayoutCoins`.
 *
 * WHY GOLD IS AN OBJECT HERE AND NOWHERE ELSE.
 * Group gold is deliberately never a thing on the floor — dark gold is the
 * currency you walk over, and the two are separated by that as much as by
 * colour. This is the one exception and it is the moment the gold is CREATED:
 * a night's loot stops being cargo on a deck and becomes the party's balance,
 * and that transaction is the only thing in the game the player is owed a
 * picture of. It exists for about a second, in the air, on its way to a number
 * — it is never collectable and never lands on the ground.
 */

import type { Projection } from '../projection';
import type { PlatformAtlas } from '../platform';
import { palette } from '../../theme/palette';
import { warpHudPoint } from '../../lib/lens';
import {
  DESCENT_HEIGHT,
  cashProgress,
  departProgress,
  descentProgress,
  padTiming,
  type Payout,
  type PayoutPad,
} from '../../game/payout';

/** Platform prop frame for a skid under power. 1 is the green standby state. */
const DECK_STATE = 1;
/** How far a drone climbs while it leaves, in world pixels. */
const CLIMB = 420;
/** How many coins one platform throws, per hundred gold. Capped — see below. */
const COINS_PER_HUNDRED = 7;
/** Nobody can read more than this many discs, and past it they are confetti. */
const MAX_COINS = 22;
/** Frame size of `/hud/coin.png`. Must match make_hud_icons.py. */
const COIN_PX = 8;
/**
 * Which row the group balance sits on, in CSS pixels from the top.
 *
 * `Hud.tsx` puts it at `top-2.5` under the ready count; this is that row's
 * middle. It is a constant on purpose — see `drawPayoutCoins`.
 */
const BALANCE_ROW = 30;

/**
 * The rigs. World space, drawn with the props.
 *
 * A descending skid is drawn at its landing point LIFTED, with its own contact
 * shadow left on the ground and shrinking — that pair is the whole reason it
 * reads as being lowered rather than as a sprite sliding down the screen. The
 * eyes and the rope length come out of the atlas layout, exactly as they do on
 * the way up, so the lines are the same lines.
 */
export function drawPayoutRigs(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  atlas: PlatformAtlas | null,
  payout: Payout | null,
): void {
  if (!atlas || !payout) return;
  const deck = atlas.platform;
  const drone = atlas.drone;
  if (!deck) return;
  const zoom = view.zoom;
  const tone = palette();

  for (const pad of payout.pads) {
    const progress = descentProgress(payout, pad);
    if (progress < 0) continue;
    const lift = (1 - progress) * DESCENT_HEIGHT;
    const grounded = progress >= 1;

    // The shadow, on the ground, tightening as the thing gets closer to it.
    if (!grounded) {
      const spread = 0.45 + (1 - progress) * 0.9;
      ctx.globalAlpha = 0.16 + progress * 0.34;
      ctx.fillStyle = tone.entity.shadow;
      ctx.beginPath();
      ctx.ellipse(
        view.x(pad.x),
        view.y(pad.y),
        deck.frameWidth * 0.4 * spread * zoom,
        deck.frameHeight * 0.12 * spread * zoom,
        0, 0, Math.PI * 2,
      );
      ctx.fill();
      ctx.globalAlpha = 1;
    }

    const state = Math.min(DECK_STATE, deck.states - 1);
    const left = view.x(pad.x) - Math.round((deck.frameWidth * zoom) / 2);
    const top = view.y(pad.y - lift) - deck.frameHeight * zoom;
    ctx.drawImage(
      deck.image,
      state * deck.frameWidth, 0, deck.frameWidth, deck.frameHeight,
      left, top, deck.frameWidth * zoom, deck.frameHeight * zoom,
    );

    if (!drone) continue;
    const leaving = departProgress(payout, pad);
    if (leaving >= 1) continue;
    const climb = leaving < 0 ? 0 : leaving * CLIMB;
    ctx.globalAlpha = leaving < 0 ? 1 : Math.max(0, 1 - leaving * leaving);
    // One aircraft per eye, a rope above it, exactly as on the way up.
    for (let corner = 0; corner < atlas.layout.eyes.length; corner++) {
      const eye = atlas.layout.eyes[corner];
      const eyeX = pad.x + eye.dx;
      const eyeY = pad.y - lift + eye.dy;
      const hoverY = eyeY - atlas.layout.ropeLength - climb;
      // The line. Still tied while the skid is coming down; slack and gone
      // once it is released — a drone that flew off with the cable still
      // attached is the one frame that would undo the whole sequence.
      if (leaving < 0) {
        ctx.strokeStyle = tone.entity.shadow;
        ctx.globalAlpha = 0.85;
        ctx.lineWidth = Math.max(1, zoom);
        ctx.beginPath();
        ctx.moveTo(view.x(eyeX), view.y(eyeY));
        ctx.lineTo(view.x(eyeX), view.y(hoverY));
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
      // Frame 0 is pitched forward for a crossing; 1 is level on station.
      const cut = leaving < 0 ? Math.min(1, drone.states - 1) : 0;
      ctx.drawImage(
        drone.image,
        cut * drone.frameWidth, 0, drone.frameWidth, drone.frameHeight,
        view.x(eyeX) - Math.round((drone.frameWidth * zoom) / 2),
        view.y(hoverY) - drone.frameHeight * zoom,
        drone.frameWidth * zoom, drone.frameHeight * zoom,
      );
    }
    ctx.globalAlpha = 1;
  }
}

/**
 * Rotor discs, nav strobes and the wash under a rig on station.
 *
 * Additive, after the darkness pass, like every other light. The WASH is the
 * beat that matters: it only appears in the last stretch of the descent, when
 * the skid is close enough to the ground for the downdraft to hit it, and it
 * is what makes a landing feel like air moving rather than like a sprite
 * arriving at a Y coordinate.
 *
 * EVERY ALPHA HERE IS DELIBERATELY LOW, because three pads land at once in the
 * one lit room in the game. `lighter` SUMS and nothing clamps the total: the
 * wash sheet is seven tiles wide, the pads used to set down within five tiles
 * of each other, and at the old 0.85 two overlapping washes were already 1.7
 * of a full-bright sheet — before eight rotors and eight strobes went on top
 * of them, on the shop's ambient floor. That is how the apron saturated to
 * flat white for the length of a payout. The other half of the fix is on the
 * server (`store.PAYOUT_SPOTS` now land far enough apart that the washes do
 * not touch); it is one budget, documented at `zones.STORE_AMBIENT`.
 */
export function drawPayoutLight(
  ctx: CanvasRenderingContext2D,
  atlas: PlatformAtlas | null,
  payout: Payout | null,
  time: number,
): void {
  if (!atlas || !payout) return;
  const previous = ctx.globalCompositeOperation;
  ctx.globalCompositeOperation = 'lighter';

  for (const pad of payout.pads) {
    const progress = descentProgress(payout, pad);
    if (progress < 0) continue;
    const lift = (1 - progress) * DESCENT_HEIGHT;
    const leaving = departProgress(payout, pad);
    if (leaving >= 1) continue;
    const fade = leaving < 0 ? 1 : Math.max(0, 1 - leaving * leaving);

    const wash = atlas.downwash;
    if (wash && progress > 0.55) {
      const bite = (progress - 0.55) / 0.45;
      const step = Math.floor(time * wash.fps) % wash.frames;
      ctx.globalAlpha = bite * 0.5 * fade;
      ctx.drawImage(
        wash.image,
        step * wash.frameWidth, 0, wash.frameWidth, wash.frameHeight,
        Math.round(pad.x - wash.frameWidth / 2),
        Math.round(pad.y - wash.anchorY),
        wash.frameWidth, wash.frameHeight,
      );
    }

    const rotor = atlas.rotor;
    const strobe = atlas.strobe;
    for (let corner = 0; corner < atlas.layout.eyes.length; corner++) {
      const eye = atlas.layout.eyes[corner];
      const eyeX = pad.x + eye.dx;
      const hoverY =
        pad.y - lift + eye.dy - atlas.layout.ropeLength - (leaving < 0 ? 0 : leaving * CLIMB);
      if (rotor) {
        const step = Math.floor(time * rotor.fps + corner * 2) % rotor.frames;
        ctx.globalAlpha = 0.6 * fade;
        ctx.drawImage(
          rotor.image,
          step * rotor.frameWidth, 0, rotor.frameWidth, rotor.frameHeight,
          Math.round(eyeX - rotor.frameWidth / 2),
          Math.round(hoverY - atlas.layout.rotorY - rotor.anchorY),
          rotor.frameWidth, rotor.frameHeight,
        );
      }
      if (strobe) {
        const step = Math.floor(time * strobe.fps + corner * 3) % strobe.frames;
        ctx.globalAlpha = 0.6 * fade;
        ctx.drawImage(
          strobe.image,
          step * strobe.frameWidth, 0, strobe.frameWidth, strobe.frameHeight,
          Math.round(eyeX - strobe.frameWidth / 2),
          Math.round(hoverY - strobe.anchorY),
          strobe.frameWidth, strobe.frameHeight,
        );
      }
    }
  }

  ctx.globalAlpha = 1;
  ctx.globalCompositeOperation = previous;
}

/**
 * The gold, and the number it is going into. SCREEN space, last of everything.
 *
 * WHY SCREEN SPACE. The coins are travelling to the BALANCE, which is a HUD
 * element at top-centre — so their destination has no world position at all.
 * Drawing them in the world and hoping the camera happened to be pointing the
 * right way would make the payout land somewhere different on every arrival.
 * They leave the deck at its projected position (so they visibly come off the
 * platform) and fly to a fixed point on the glass, which is the one path that
 * reads the same on every screen.
 *
 * The count is DETERMINISTIC per pad — a fixed spray angle per index, not a
 * random one — because two players in the same room watching the same landing
 * must not see two different amounts of money.
 */
export function drawPayoutCoins(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  coin: HTMLImageElement | null,
  payout: Payout | null,
  width: number,
  height: number,
): void {
  if (!payout) return;
  const tone = palette();
  // Where the balance sits on the glass: top-centre, the row `Hud.tsx` puts it
  // on. A constant rather than a measured DOM anchor because that element does
  // not move, and reading its box every frame to learn a fixed number is the
  // wrong trade — but it is WARPED, because the HUD is painted onto a curved
  // display and coins that landed on the flat position would visibly miss the
  // number they are being added to.
  const target = warpHudPoint(width / 2, BALANCE_ROW, width, height);
  const targetX = target.x;
  const targetY = target.y;

  for (const pad of payout.pads) {
    const cash = cashProgress(payout, pad);
    if (cash < 0) continue;
    const count = Math.min(
      MAX_COINS,
      Math.max(3, Math.round((pad.value / 100) * COINS_PER_HUNDRED)),
    );
    const originX = view.x(pad.x);
    const originY = view.y(pad.y) - 18 * view.zoom;

    for (let index = 0; index < count; index++) {
      // Each coin leaves a fraction of a beat after the one before it, so the
      // spray is a stream rather than a starburst that all arrives at once.
      const offset = (index / count) * 0.55;
      const t = (cash - offset) / (1 - 0.55);
      if (t <= 0 || t >= 1) continue;

      // Out of the deck first, then in toward the number. The early arc is
      // what says the coins came OFF something.
      const fan = (index / Math.max(1, count - 1) - 0.5) * 2;
      const burstX = originX + fan * 46 * Math.min(1, t * 3);
      const burstY = originY - Math.sin(Math.min(1, t * 2.2) * Math.PI) * 40;
      const ease = t * t;
      const x = burstX + (targetX - burstX) * ease;
      const y = burstY + (targetY - burstY) * ease;

      const size = COIN_PX * (2.2 - t * 0.9);
      ctx.globalAlpha = t > 0.88 ? (1 - t) / 0.12 : 1;
      if (coin) {
        ctx.drawImage(
          coin, 0, 0, COIN_PX, COIN_PX,
          Math.round(x - size / 2), Math.round(y - size / 2), size, size,
        );
      } else {
        ctx.fillStyle = tone.rarity.legendary;
        ctx.beginPath();
        ctx.arc(x, y, size / 2, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }
  ctx.globalAlpha = 1;
}

/**
 * The big number, over the middle, while the gold is in the air.
 *
 * It is drawn on the CANVAS rather than as a HUD component on purpose: it has
 * to sit over the world and under nothing, it exists for two seconds, and a
 * React node for it would mean a mount, a keyframe and a piece of state for
 * something that is only ever a string and a scale. It shrinks toward the
 * balance as it leaves, which is what hands the number over to the HUD instead
 * of just deleting it.
 */
/*
 * THE `+N` OVER THE MIDDLE USED TO BE DRAWN HERE AND IT IS NOT ANY MORE.
 *
 * It was a large number rising out of the deck, holding, then shrinking toward
 * the balance on the HUD, with `EXTRAÇÃO PAGA` under it — and every part of
 * that was right except that the end-of-night CARD now says the same thing
 * eight percent of the screen higher up. Two `+N`s in the same moment at two
 * sizes, overlapping, is one event told twice.
 *
 * The card won because it carries the half the canvas could not: WHICH NIGHT
 * just closed. `Announce` states the day and the take together, once, and the
 * animation of the number actually moving is still here — it is the coins,
 * flying off the decks to the balance row, and the balance counting up under
 * them. See `Game.announceDayDone`.
 */

/** Whether this pad is close enough to the ground to shake the camera. */
export function padLanded(payout: Payout, pad: PayoutPad): boolean {
  return payout.elapsed >= padTiming(pad).touch;
}
