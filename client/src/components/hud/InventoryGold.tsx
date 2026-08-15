/**
 * Pocket gold total. Same number as the vitals GOLD line — here so the
 * open bag can answer "how much am I carrying" without leaving the panel.
 */

import { CoinIcon } from './CoinIcon';

export interface InventoryGoldProps {
  gold: number;
}

export function InventoryGold({ gold }: InventoryGoldProps) {
  return (
    <div className="mt-1.5 flex items-baseline justify-between gap-2 text-[11px] leading-[11px] tracking-[0.05em]">
      <span className="text-ink-muted">OURO</span>
      <span className="text-ink-accent flex items-center gap-0.5 tabular-nums">
        <CoinIcon />
        {gold}
      </span>
    </div>
  );
}
