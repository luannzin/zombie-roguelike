/**
 * One bag cell: rarity border, the item sprite, value up-right, qty down-right.
 * A fly targeting this cell IS the sprite — the icon stays hidden until it lands.
 */

import { useLayoutEffect, useRef, useSyncExternalStore, type PointerEvent } from 'react';
import type { HudInventorySlot } from '../../game/hud-store';
import {
  dropInventoryAnchor,
  writeInventoryAnchor,
} from '../../game/inventory-anchors';
import { incomingHas, subscribeLootFlies } from '../../game/loot-flies';
import type { LootRarity } from '../../net/protocol';
import { cn } from '@/lib/utils';
import { LootIcon } from './LootIcon';
import { SlotValue } from './SlotValue';

export interface InventorySlotProps {
  index: number;
  item: HudInventorySlot | null;
  lootFrames: number;
  dragging?: boolean;
  onHover?: (item: HudInventorySlot, anchor: { x: number; top: number; bottom: number }) => void;
  onLeave?: () => void;
  onGrip?: (index: number, item: HudInventorySlot, event: PointerEvent<HTMLDivElement>) => void;
  onDrag?: (event: PointerEvent<HTMLDivElement>) => void;
  onRelease?: (event: PointerEvent<HTMLDivElement>) => void;
}

const RARITY_BORDER: Record<LootRarity, string> = {
  common: 'border-rarity-common',
  uncommon: 'border-rarity-uncommon',
  rare: 'border-rarity-rare',
  epic: 'border-rarity-epic',
  legendary: 'border-rarity-legendary',
};

export function InventorySlot({
  index,
  item,
  lootFrames,
  dragging = false,
  onHover,
  onLeave,
  onGrip,
  onDrag,
  onRelease,
}: InventorySlotProps) {
  const ref = useRef<HTMLDivElement>(null);
  const incoming = useSyncExternalStore(
    subscribeLootFlies,
    () => incomingHas(index),
    () => false,
  );
  const hide = dragging || (incoming && (!item || item.qty <= 1));

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
        'relative size-10 touch-none border bg-panel-inset shadow-[inset_0_0_0_1px_var(--surface)]',
        item ? RARITY_BORDER[item.rarity] : 'border-track-border',
        item && !incoming ? 'cursor-pointer' : null,
        dragging ? 'cursor-grabbing' : null,
      )}
      onPointerEnter={() => {
        if (!item || dragging) return;
        const el = ref.current;
        if (!el) return;
        const box = el.getBoundingClientRect();
        onHover?.(item, {
          x: box.left + box.width / 2,
          top: box.top,
          bottom: box.bottom,
        });
      }}
      onPointerLeave={() => onLeave?.()}
      onPointerDown={(event) => {
        if (!item || incoming) return;
        onGrip?.(index, item, event);
      }}
      onPointerMove={onDrag}
      onPointerUp={onRelease}
      onPointerCancel={onRelease}
    >
      {item && !hide ? (
        <>
          <LootIcon
            frame={item.frame}
            frames={lootFrames}
            className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2"
          />
          <SlotValue value={item.value} />
          <span className="text-ink absolute right-0.5 bottom-px text-[11px] leading-[11px] tabular-nums">
            {item.qty}
          </span>
        </>
      ) : null}
    </div>
  );
}
