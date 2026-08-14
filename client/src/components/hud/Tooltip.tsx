/**
 * World (or HUD) tooltip. Reusable: a chest, a door, the fire — each caller
 * supplies the copy and, if the thing lives in the world, an `anchor` id the
 * game loop writes a screen position into.
 *
 * Positioning is a transform on this wrapper, updated from
 * `tooltip-anchors` in rAF. That is not a React render. The enter animation
 * lives on the inner row so it does not fight the world transform.
 */

import { useEffect, useRef, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { readTooltipAnchor } from '../../game/tooltip-anchors';

export interface TooltipProps {
  /** Id the game loop writes a screen-space point into. Omit for a static tooltip. */
  anchor?: string;
  children: ReactNode;
  className?: string;
}

export function Tooltip({ anchor, children, className }: TooltipProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!anchor) return;
    const el = ref.current;
    if (!el) return;
    let raf = 0;
    const tick = () => {
      const pos = readTooltipAnchor(anchor);
      if (pos) {
        el.style.transform = `translate(${Math.round(pos.x)}px, ${Math.round(pos.y)}px) translate(-50%, -100%)`;
        el.style.visibility = 'visible';
      } else {
        el.style.visibility = 'hidden';
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [anchor]);

  return (
    <div
      ref={ref}
      role="tooltip"
      className={cn(
        'pointer-events-none',
        anchor && 'fixed top-0 left-0',
        className,
      )}
      style={anchor ? { visibility: 'hidden' } : undefined}
    >
      <p
        className={cn(
          'world-tooltip pixel-text text-ink flex items-center gap-1.5 text-[11px] leading-[17px]',
        )}
      >
        {children}
      </p>
    </div>
  );
}

export interface TooltipKeyProps {
  children: ReactNode;
}

export function TooltipKey({ children }: TooltipKeyProps) {
  return (
    <kbd className="border-panel-border text-ink inline-flex h-[17px] min-w-[17px] items-center justify-center border px-0.5 text-[11px] leading-[11px]">
      {children}
    </kbd>
  );
}
