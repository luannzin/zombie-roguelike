/**
 * Quest progress readout. Catalog-gold rows wear the HUD coin so the
 * quota reads as the same currency the bag already uses.
 */

import { cn } from '@/lib/utils';
import { CoinIcon } from './CoinIcon';

export interface QuestCountProps {
  have: number;
  need: number;
  gold?: boolean;
  risk?: boolean;
  done?: boolean;
  className?: string;
}

export function QuestCount({ have, need, gold, risk, done, className }: QuestCountProps) {
  const tone = done
    ? 'text-ink-accent'
    : gold
      ? 'text-ink-accent'
      : risk
        ? 'text-hp-low'
        : 'text-ink';

  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-0.5 tabular-nums tracking-[0.08em]',
        tone,
        className,
      )}
    >
      {gold ? <CoinIcon /> : null}
      {have}/{need}
    </span>
  );
}
