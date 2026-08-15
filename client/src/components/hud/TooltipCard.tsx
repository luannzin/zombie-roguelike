/**
 * Card-shaped world tooltip. Same chrome as `Tooltip` — inset fill, hairline,
 * 2px leading bar, pixel staircase arrow — stacked as a column instead of
 * a single prompt line.
 */

import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface TooltipCardProps {
  children: ReactNode;
  className?: string;
}

export function TooltipCard({ children, className }: TooltipCardProps) {
  return (
    <div
      role="tooltip"
      className={cn(
        'world-tooltip world-tooltip-card pixel-text text-ink text-[11px] leading-[14px]',
        className,
      )}
    >
      {children}
    </div>
  );
}
