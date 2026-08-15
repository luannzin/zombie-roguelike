/**
 * One bag cell: rarity border, the item sprite, value up-right, qty down-right.
 * A fly targeting this cell IS the sprite — the cell stays empty until it lands.
 */

import { useEffect, useRef, useSyncExternalStore, type PointerEvent } from 'react';
import type { HudInventorySlot } from '../../game/hud-store';
import {
  dropInventoryAnchor,
  writeInventoryAnchor,
} from '../../game/inventory-anchors';
import { incomingCount, subscribeLootFlies } from '../../game/loot-flies';
import type { LootRarity } from '../../net/protocol';
import { cn } from '@/lib/utils';
import { LootIcon } from './LootIcon';
import { SlotValue } from './SlotValue';

export interface InventorySlotProps {
  index: number;
  item: HudInventorySlot | null;
  lootFrames: number;
  /** Drawer is open. Anchors are only written then, so a fly cannot aim at a collapsed cell. */
  active?: boolean;
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
  active = false,
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
    () => incomingCount(index),
    () => 0,
  );
  const shown = shownItem(item, incoming, dragging);

  useEffect(() => {
    const el = ref.current;
    const id = `slot-${index}`;
    if (!el || !active) {
      dropInventoryAnchor(id);
      return;
    }
    let raf = 0;
    const tick = () => {
      const box = el.getBoundingClientRect();
      if (box.width >= 8 && box.height >= 8) {
        writeInventoryAnchor(id, box.left + box.width / 2, box.top + box.height / 2);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      dropInventoryAnchor(id);
    };
  }, [index, active]);

  return (
    <div
      ref={ref}
      data-inv-slot={index}
      className={cn(
        'relative size-10 touch-none border bg-panel-inset shadow-[inset_0_0_0_1px_var(--surface)]',
        shown ? RARITY_BORDER[shown.rarity] : 'border-track-border',
        shown ? 'cursor-pointer' : null,
        dragging ? 'cursor-grabbing' : null,
      )}
      onPointerEnter={() => {
        if (!shown || dragging) return;
        const el = ref.current;
        if (!el) return;
        const box = el.getBoundingClientRect();
        onHover?.(shown, {
          x: box.left + box.width / 2,
          top: box.top,
          bottom: box.bottom,
        });
      }}
      onPointerLeave={() => onLeave?.()}
      onPointerDown={(event) => {
        if (!shown) return;
        onGrip?.(index, shown, event);
      }}
      onPointerMove={onDrag}
      onPointerUp={onRelease}
      onPointerCancel={onRelease}
    >
      {shown ? (
        <>
          <LootIcon
            frame={shown.frame}
            frames={lootFrames}
            className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2"
          />
          <SlotValue value={shown.value} />
          <span className="text-ink absolute right-0.5 bottom-px text-[11px] leading-[11px] tabular-nums">
            {shown.qty}
          </span>
        </>
      ) : null}
    </div>
  );
}

function shownItem(
  item: HudInventorySlot | null,
  incoming: number,
  dragging: boolean,
): HudInventorySlot | null {
  if (!item || dragging) return null;
  const qty = item.qty - incoming;
  if (qty <= 0) return null;
  if (qty === item.qty) return item;
  return { ...item, qty };
}
