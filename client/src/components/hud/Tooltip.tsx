/**
 * World (or HUD) tooltip. Reusable: a chest, a door, the fire — each caller
 * supplies the copy and, if the thing lives in the world, an `anchor` id the
 * game loop writes a screen position into.
 *
 * Positioning is a transform on this wrapper, updated from
 * `tooltip-anchors` in rAF. That is not a React render. The enter animation
 * lives on the inner row so it does not fight the world transform.
 *
 * The card itself — fill, hairline, leading bar and pointer — is
 * `.world-tooltip` in styles/index.css, which is the lobby nameplate in DOM
 * form. See that rule before changing any measurement here.
 */

import { useEffect, useRef, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { readTooltipAnchor } from '../../game/tooltip-anchors';

export interface TooltipProps {
  /** Id the game loop writes a screen-space point into. Omit for a static tooltip. */
  anchor?: string;
  /**
   * Sits before the copy, inside the card — a key cap, a tick, a cost. It is a
   * slot rather than a prop per shape because the row is a flex line: whatever
   * goes here is spaced and centred by the same rule the copy is, so a caller
   * cannot end up nudging one with a margin.
   */
  start?: ReactNode;
  /** The same, after the copy. */
  end?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Tooltip({ anchor, start, end, children, className }: TooltipProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!anchor) return;
    const el = ref.current;
    if (!el) return;
    let raf = 0;
    const tick = () => {
      const pos = readTooltipAnchor(anchor);
      if (pos) {
        // The extra 3px is the pointer, which hangs below the card's box: the
        // anchor is the point being pointed AT, so the tip has to land on it
        // and not the card's bottom edge.
        el.style.transform = `translate(${Math.round(pos.x)}px, ${Math.round(pos.y)}px) translate(-50%, -100%) translateY(-3px)`;
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
      {/* 14px leading is Departure Mono's own content box at 11px (11 up, 3
          down) — the same span the lobby measures its card off, so the copy
          sits on the card exactly the way a name does.

          `whitespace-nowrap` because these are ONE-LINE prompts and the card
          is `position: fixed` with no width — so its containing block is the
          viewport, and a tooltip pinned to something near the screen edge was
          wrapping mid-sentence into a two-line card that jumped as the player
          walked. Overflowing the edge is the better failure: the copy stays
          one readable line and the card is still pointing at the thing. */}
      <p
        className={cn(
          'world-tooltip pixel-text text-ink flex items-center gap-1.5 whitespace-nowrap text-[11px] leading-[14px]',
        )}
      >
        {/* `shrink-0`: the copy may be clipped, an adornment may not —
            half a key cap says nothing at all. */}
        {start === undefined ? null : (
          <span className="flex shrink-0 items-center">{start}</span>
        )}
        {children}
        {end === undefined ? null : <span className="flex shrink-0 items-center">{end}</span>}
      </p>
    </div>
  );
}

export interface TooltipKeyProps {
  children: ReactNode;
}

export function TooltipKey({ children }: TooltipKeyProps) {
  return (
    <kbd className="border-panel-border text-ink inline-flex h-[14px] min-w-[14px] items-center justify-center border px-0.5 text-[11px] leading-[11px]">
      {children}
    </kbd>
  );
}
