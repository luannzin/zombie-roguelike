/**
 * Slot gold badge: the small HUD coin plus the item's value.
 */

import { CoinIcon } from './CoinIcon';

export interface SlotValueProps {
  value: number;
}

export function SlotValue({ value }: SlotValueProps) {
  return (
    <span className="absolute top-px right-px flex items-center gap-px">
      <CoinIcon />
      <span className="text-ink-accent text-[11px] leading-[11px] tabular-nums">
        {value}
      </span>
    </span>
  );
}
