/**
 * Card-shaped world tooltip. Same chrome as `Tooltip` — inset fill, hairline,
 * 2px leading bar, pixel staircase arrow — stacked as a column instead of
 * a single prompt line. `placement` flips the arrow; `--tooltip-arrow-x`
 * slides it so it still points at the thing when the card has to shift.
 */

import { forwardRef, type CSSProperties, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

export type TooltipPlacement = 'top' | 'bottom';

export interface TooltipCardProps {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  placement?: TooltipPlacement;
  arrowX?: number;
}

export const TooltipCard = forwardRef<HTMLDivElement, TooltipCardProps>(
  function TooltipCard(
    { children, className, style, placement = 'top', arrowX },
    ref,
  ) {
    return (
      <div
        ref={ref}
        role="tooltip"
        data-placement={placement}
        className={cn(
          'world-tooltip world-tooltip-card pixel-text text-ink text-[11px] leading-[14px]',
          className,
        )}
        style={{
          ...style,
          ['--tooltip-arrow-x' as string]: arrowX === undefined ? undefined : `${arrowX}px`,
        }}
      >
        {children}
      </div>
    );
  },
);
