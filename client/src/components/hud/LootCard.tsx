/**
 * Hover card for a bag item. Lives in a portal so the glass does not warp
 * it off the slot it is pointing at. The chrome (`.world-tooltip`) is
 * `position: relative` — this wrapper is the `fixed` layer, or the card
 * would lay out at the end of `document.body` and never show on the slot.
 */

import { useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { HudInventorySlot } from '../../game/hud-store';
import type { LootRarity } from '../../net/protocol';
import { LootCardRow } from './LootCardRow';
import { formatWeight } from './WeightBar';
import { TooltipCard, type TooltipPlacement } from './TooltipCard';

export interface LootCardAnchor {
  x: number;
  top: number;
  bottom: number;
}

export interface LootCardProps {
  item: HudInventorySlot;
  anchor: LootCardAnchor;
}

const RARITY_LABEL: Record<LootRarity, string> = {
  common: 'Comum',
  uncommon: 'Incomum',
  rare: 'Raro',
  epic: 'Épico',
  legendary: 'Lendário',
};

const RARITY_CLASS: Record<LootRarity, string> = {
  common: 'text-rarity-common',
  uncommon: 'text-rarity-uncommon',
  rare: 'text-rarity-rare',
  epic: 'text-rarity-epic',
  legendary: 'text-rarity-legendary',
};

const GAP = 6;
const PAD = 8;
const ARROW_INSET = 8;

interface CardPose {
  left: number;
  top: number;
  placement: TooltipPlacement;
  arrowX: number;
}

export function LootCard({ item, anchor }: LootCardProps) {
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
  }, [item.key, item.qty, item.rarity, anchor.x, anchor.top, anchor.bottom]);

  return createPortal(
    <div
      ref={ref}
      className="pointer-events-none fixed top-0 left-0 z-50 w-max"
      style={{
        visibility: pose ? 'visible' : 'hidden',
        left: pose?.left ?? 0,
        top: pose?.top ?? 0,
      }}
    >
      <TooltipCard placement={pose?.placement ?? 'top'} arrowX={pose?.arrowX}>
        <p className={RARITY_CLASS[item.rarity]}>{item.name}</p>
        <p className={RARITY_CLASS[item.rarity]}>{RARITY_LABEL[item.rarity]}</p>
        <LootCardRow label="PESO" value={`${formatWeight(item.weight)}kg`} />
        <LootCardRow label="VALOR" value={String(item.value)} />
        {item.qty > 1 ? <LootCardRow label="QTD" value={String(item.qty)} /> : null}
      </TooltipCard>
    </div>,
    document.body,
  );
}

function fitCard(
  anchor: LootCardAnchor,
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
