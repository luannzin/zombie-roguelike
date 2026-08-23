/**
 * A card pinned to a HUD cell, in a portal, fitted to the viewport.
 *
 * Lifted out of `LootCard` when the belt and the armour panel grew cards of
 * their own. The POSITIONING is the whole of it — flip above/below when the
 * card would run off the top, clamp to the edges, and slide the arrow so it
 * still points at the cell after the clamp — and that arithmetic being in
 * three files would be three subtly different answers at the corners of the
 * screen, which is exactly where a HUD card is hardest to notice being wrong.
 *
 * IT LIVES IN A PORTAL because the HUD is drawn on curved glass (`HudScreen`)
 * and a card inside that wrapper warps off the cell it is pointing at. The
 * chrome (`.world-tooltip`) is `position: relative`, so this wrapper is the
 * `fixed` layer — without it the card would lay out at the end of
 * `document.body` and never appear over anything.
 */

import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { TooltipCard, type TooltipPlacement } from './TooltipCard';

/** The cell being pointed at, in screen pixels. */
export interface HoverAnchor {
  x: number;
  top: number;
  bottom: number;
}

export interface HoverCardProps {
  anchor: HoverAnchor;
  /** Changes to this re-fit the card. Pass whatever makes its size change. */
  fitKey?: string;
  children: ReactNode;
}

const GAP = 6;
const PAD = 8;
const ARROW_INSET = 8;

interface CardPose {
  left: number;
  top: number;
  placement: TooltipPlacement;
  arrowX: number;
}

export function HoverCard({ anchor, fitKey, children }: HoverCardProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [pose, setPose] = useState<CardPose | null>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;

    const place = () => {
      const box = el.getBoundingClientRect();
      if (box.width < 1 || box.height < 1) return;
      const next = fitCard(anchor, box.width, box.height, el);
      setPose((prev) => (samePose(prev, next) ? prev : next));
    };

    place();
    window.addEventListener('resize', place);
    return () => window.removeEventListener('resize', place);
  }, [fitKey, anchor.x, anchor.top, anchor.bottom]);

  return createPortal(
    <div
      ref={ref}
      className="pointer-events-none fixed top-0 left-0 z-50 w-max"
      style={{
        // Hidden rather than unmounted for the first frame: the card has to be
        // laid out to be measured, and measuring it visible at (0,0) is one
        // painted frame of a card in the corner of the screen.
        visibility: pose ? 'visible' : 'hidden',
        left: pose?.left ?? 0,
        top: pose?.top ?? 0,
      }}
    >
      <TooltipCard placement={pose?.placement ?? 'top'} arrowX={pose?.arrowX}>
        {children}
      </TooltipCard>
    </div>,
    document.body,
  );
}

function fitCard(
  anchor: HoverAnchor,
  width: number,
  height: number,
  el: HTMLElement,
): CardPose {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const maxLeft = Math.max(PAD, vw - PAD - width);

  let placement: TooltipPlacement = 'top';
  let top = anchor.top - GAP - height;
  if (top < PAD) {
    placement = 'bottom';
    top = anchor.bottom + GAP;
    if (top + height > vh - PAD) {
      top = Math.max(PAD, vh - PAD - height);
    }
  }

  let left = anchor.x - width / 2;
  left = Math.min(Math.max(left, PAD), maxLeft);

  const chrome = el.firstElementChild;
  const borderLeft = chrome
    ? parseFloat(getComputedStyle(chrome).borderLeftWidth) || 0
    : 2;
  const raw = anchor.x - left - borderLeft;
  const arrowX = Math.min(Math.max(raw, ARROW_INSET), width - borderLeft - ARROW_INSET);

  return { left, top, placement, arrowX };
}

function samePose(a: CardPose | null, b: CardPose): boolean {
  if (!a) return false;
  return (
    a.left === b.left &&
    a.top === b.top &&
    a.placement === b.placement &&
    a.arrowX === b.arrowX
  );
}
