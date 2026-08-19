/**
 * THE PAYOUT — what the night was for, arriving in the clearing.
 *
 * The party walks up out of the south corridor and the platforms they loaded an
 * hour ago are being lowered onto the apron in front of them and to their left,
 * by the same four aircraft that took them. The skids touch down, the lines let
 * go, the drones climb out, and the cargo on the decks becomes GOLD: a spray of
 * coins off each platform, arcing toward the balance on the HUD, counting it up
 * as they land.
 *
 * WHY IT IS AN EVENT AND NOT A NUMBER.
 * The balance was credited server-side the moment the party crossed the
 * corridor (`Room.enter_store`) and nothing here can change it. What this file
 * owns is the two seconds between the number being true and the player
 * BELIEVING it — the difference between "you have 340 gold" and "we brought
 * this home". A currency that only ever appears as a HUD digit is a score; a
 * currency that visibly comes off a machine that visibly came back is money.
 *
 * SAME SPLIT AS EVERY OTHER SET PIECE HERE. The server ships one row per
 * platform on the map payload (`store.payout`: where it lands and what it
 * carried) and this side flies the whole thing on the render clock. There is
 * nothing about the descent on the wire.
 *
 * IT IS THE ARRIVAL'S OWN BEAT and it runs UNDER the zone intro rather than
 * after it: the title card names the end of the night while the skids are
 * already coming down behind it, so the first thing the player does with their
 * returned controls is walk toward a shop, not stand watching an animation.
 */

/** How long a skid takes to come down out of the treeline. */
const DESCENT = 2.6;
/** Stagger between platforms, so three do not land as one event. */
const STAGGER = 0.55;
/** How long the drones sit on the deck before the lines let go. */
const SETTLE = 0.4;
/** How long they take to climb out and fade. */
const DEPART = 1.9;
/** When the cargo starts becoming coins, measured from that skid's touchdown. */
const CASH_LAG = 0.35;
/** How long one platform spends paying out. */
const CASH_TIME = 1.25;

/** How high above its landing point a skid starts, in world pixels. */
export const DESCENT_HEIGHT = 340;

/** One platform coming home. */
export interface PayoutPad {
  x: number;
  y: number;
  /** What this skid carried, in group gold. Drives how many coins come off it. */
  value: number;
  /** When it starts descending, in seconds from the ceremony's start. */
  startAt: number;
  /** Beats already fired, so a long frame cannot replay or skip one. */
  fired: Set<PayoutBeat>;
}

export type PayoutBeat = 'touch' | 'release' | 'cash' | 'done';

export interface Payout {
  pads: PayoutPad[];
  elapsed: number;
  /** Total being paid out. The HUD counts up to it. */
  total: number;
  /** How much of `total` has actually landed on the balance so far. */
  paid: number;
}

export function beginPayout(rows: readonly [number, number, number][]): Payout | null {
  if (rows.length === 0) return null;
  const pads = rows.map(([x, y, value], index) => ({
    x,
    y,
    value,
    startAt: index * STAGGER,
    fired: new Set<PayoutBeat>(),
  }));
  return {
    pads,
    elapsed: 0,
    total: pads.reduce((sum, pad) => sum + pad.value, 0),
    paid: 0,
  };
}

/** When each beat of one pad lands, in seconds from the ceremony's start. */
export function padTiming(pad: PayoutPad): {
  touch: number;
  release: number;
  cash: number;
  done: number;
} {
  const touch = pad.startAt + DESCENT;
  const release = touch + SETTLE;
  const cash = touch + CASH_LAG;
  return { touch, release, cash, done: cash + CASH_TIME };
}

/**
 * How far into its descent a pad is, 0..1, or -1 before it starts.
 *
 * EASED OUT AT THE BOTTOM, hard. A skid under four aircraft does not float
 * down at a constant rate — it comes fast, and the last third is the pilots
 * fighting it into place. That deceleration is the entire reason the touchdown
 * reads as heavy: a linear descent lands with no more weight than a fade.
 */
export function descentProgress(payout: Payout, pad: PayoutPad): number {
  const t = (payout.elapsed - pad.startAt) / DESCENT;
  if (t < 0) return -1;
  if (t >= 1) return 1;
  return 1 - (1 - t) ** 2.6;
}

/** How far the drones are into climbing away, 0..1, or -1 while still tied. */
export function departProgress(payout: Payout, pad: PayoutPad): number {
  const { release } = padTiming(pad);
  const t = (payout.elapsed - release) / DEPART;
  if (t < 0) return -1;
  return Math.min(1, t);
}

/** How far this pad is into paying out, 0..1, or -1 outside the window. */
export function cashProgress(payout: Payout, pad: PayoutPad): number {
  const { cash, done } = padTiming(pad);
  if (payout.elapsed < cash) return -1;
  if (payout.elapsed > done) return -1;
  return (payout.elapsed - cash) / Math.max(0.001, done - cash);
}

/**
 * Advance the ceremony and return the beats crossed, per pad.
 *
 * `paid` is stepped here rather than by the coins that are drawn, and the two
 * are deliberately not the same clock: the HUD number has to be exactly right
 * at the end, and a counter driven by however many sprites happened to be
 * spawned would land a few gold short on a slow frame.
 */
export function stepPayout(
  payout: Payout,
  dt: number,
): Array<{ pad: PayoutPad; beat: PayoutBeat }> {
  payout.elapsed += dt;
  const crossed: Array<{ pad: PayoutPad; beat: PayoutBeat }> = [];
  let paid = 0;
  for (const pad of payout.pads) {
    const timing = padTiming(pad);
    for (const beat of ['touch', 'release', 'cash', 'done'] as PayoutBeat[]) {
      if (pad.fired.has(beat)) continue;
      if (payout.elapsed >= timing[beat]) {
        pad.fired.add(beat);
        crossed.push({ pad, beat });
      }
    }
    const cash = cashProgress(payout, pad);
    const share = cash < 0 ? (payout.elapsed > timing.done ? 1 : 0) : cash;
    paid += pad.value * share;
  }
  payout.paid = Math.round(paid);
  return crossed;
}

export function payoutFinished(payout: Payout): boolean {
  const last = payout.pads[payout.pads.length - 1];
  return !last || payout.elapsed >= padTiming(last).done + 1.4;
}
