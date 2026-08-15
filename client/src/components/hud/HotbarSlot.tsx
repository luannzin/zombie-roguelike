/**
 * One hotbar cell: rarity border, the gun icon, the key number.
 * A fly targeting this cell IS the sprite — the cell stays empty until it lands.
 */

import { useEffect, useRef, useSyncExternalStore } from 'react';
import type { HudHotbarSlot } from '../../game/hud-store';
import { writeInventoryAnchor, dropInventoryAnchor } from '../../game/inventory-anchors';
import { incomingCount, subscribeLootFlies } from '../../game/loot-flies';
import type { LootRarity } from '../../net/protocol';
import { cn } from '@/lib/utils';
import { LootIcon } from './LootIcon';

export interface HotbarSlotProps {
  index: number;
  item: HudHotbarSlot | null;
  lootFrames: number;
  selected: boolean;
}

const RARITY_BORDER: Record<LootRarity, string> = {
  common: 'border-rarity-common',
  uncommon: 'border-rarity-uncommon',
  rare: 'border-rarity-rare',
  epic: 'border-rarity-epic',
  legendary: 'border-rarity-legendary',
};

export function HotbarSlot({ index, item, lootFrames, selected }: HotbarSlotProps) {
  const ref = useRef<HTMLDivElement>(null);
  const incoming = useSyncExternalStore(
    subscribeLootFlies,
    () => incomingCount(index, 'hotbar'),
    () => 0,
  );
  const shown = incoming > 0 ? null : item;

  useEffect(() => {
    const el = ref.current;
    const id = `hotbar-${index}`;
    if (!el) {
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
  }, [index]);

  return (
    <div
      ref={ref}
      data-hotbar-slot={index}
      className={cn(
        'relative size-10 border bg-panel-inset shadow-[inset_0_0_0_1px_var(--surface)]',
        shown ? RARITY_BORDER[shown.rarity] : 'border-track-border',
        selected && shown ? 'ring-1 ring-ink-accent' : null,
        selected ? 'animate-hotbar-pick' : null,
      )}
    >
      {shown ? (
        <LootIcon
          frame={shown.frame}
          frames={lootFrames}
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2"
        />
      ) : null}
      <span
        className={cn(
          'absolute top-px left-0.5 text-[11px] leading-[11px] tabular-nums',
          selected ? 'text-ink-accent' : 'text-ink-muted',
        )}
      >
        {index + 1}
      </span>
    </div>
  );
}
