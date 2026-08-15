/**
 * Slot gold badge: the static coin plus the item's value.
 */

import { CoinIcon } from './CoinIcon';

export interface SlotValueProps {
  value: number;
}

export function SlotValue({ value }: SlotValueProps) {
  return (
    <span className="absolute top-px right-px flex items-center">
      <CoinIcon zoom={1} />
      <span className="text-ink-accent text-[11px] leading-[11px] tabular-nums">
        {value}
      </span>
    </span>
  );
}
