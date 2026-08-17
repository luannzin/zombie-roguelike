/**
 * The party's purse. Top-centre, no panel — a number, not a widget, the same
 * shape `ReadyCount` takes in the camp.
 *
 * ONLY IN THE SHOP, and that is the whole design of it. The balance exists
 * from the moment the party leaves the forest, but it is not a resource you
 * manage during a run: nothing in a night out spends it and nothing outside
 * this corridor can. A permanent gold counter would sit in the corner of every
 * expedition telling the player about money they cannot use, competing for
 * attention with the bag — which is the number that DOES change while they
 * play, and the one extraction is about.
 *
 * `vitals.gold` is the other one and stays where it is: coins this player
 * personally walked over, which nobody pooled.
 */

import { CoinIcon } from './CoinIcon';

export interface BalanceProps {
  balance: number;
  /** Only the store shows it — see the note above. */
  visible: boolean;
}

export function Balance({ balance, visible }: BalanceProps) {
  if (!visible) return null;

  return (
    <p className="pixel-text flex items-center justify-center gap-1.5 text-center text-[11px] leading-[17px] tracking-[0.14em] uppercase">
      <span className="text-ink-muted">saldo do grupo</span>
      <CoinIcon />
      <span className="text-ink">{balance}</span>
    </p>
  );
}
