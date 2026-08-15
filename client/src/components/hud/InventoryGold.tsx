/**
 * Bag value total: every stowed item's catalog value × stack. Not the
 * vitals GOLD line (that is coin gold from kills).
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
