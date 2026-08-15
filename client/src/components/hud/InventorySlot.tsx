/**
 * One bag cell: rarity border, the item sprite, value up-right, qty down-right.
 */

import { useLayoutEffect, useRef } from 'react';
import type { HudInventorySlot } from '../../game/hud-store';
import {
  dropInventoryAnchor,
  writeInventoryAnchor,
} from '../../game/inventory-anchors';
import type { LootRarity } from '../../net/protocol';
import { cn } from '@/lib/utils';
import { LootIcon } from './LootIcon';

export interface InventorySlotProps {
  index: number;
  item: HudInventorySlot | null;
  lootFrames: number;
}

const RARITY_BORDER: Record<LootRarity, string> = {
  common: 'border-rarity-common',
  uncommon: 'border-rarity-uncommon',
  rare: 'border-rarity-rare',
  epic: 'border-rarity-epic',
  legendary: 'border-rarity-legendary',
};

export function InventorySlot({ index, item, lootFrames }: InventorySlotProps) {
  const ref = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const id = `slot-${index}`;
    const write = () => {
      const box = el.getBoundingClientRect();
      writeInventoryAnchor(id, box.left + box.width / 2, box.top + box.height / 2);
    };
    write();
    const observer = new ResizeObserver(write);
    observer.observe(el);
    window.addEventListener('resize', write);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', write);
      dropInventoryAnchor(id);
    };
  }, [index]);

  return (
    <div
      ref={ref}
      data-inv-slot={index}
      className={cn(
        'relative size-10 border bg-panel-inset shadow-[inset_0_0_0_1px_var(--surface)]',
        item ? RARITY_BORDER[item.rarity] : 'border-track-border',
      )}
    >
      {item ? (
        <>
          <LootIcon
            frame={item.frame}
            frames={lootFrames}
            className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2"
          />
          <span className="text-ink-accent absolute top-px right-0.5 text-[11px] leading-[11px] tabular-nums">
            {item.value}
          </span>
          <span className="text-ink absolute right-0.5 bottom-px text-[11px] leading-[11px] tabular-nums">
            {item.qty}
          </span>
        </>
      ) : null}
    </div>
  );
}
