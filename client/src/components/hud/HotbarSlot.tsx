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
  selected: boolean;
  onHover?: (item: HudHotbarSlot, anchor: { x: number; top: number; bottom: number }) => void;
  onLeave?: () => void;
}

const RARITY_BORDER: Record<LootRarity, string> = {
  common: 'border-rarity-common',
  uncommon: 'border-rarity-uncommon',
  rare: 'border-rarity-rare',
  epic: 'border-rarity-epic',
  legendary: 'border-rarity-legendary',
};

export function HotbarSlot({ index, item, selected, onHover, onLeave }: HotbarSlotProps) {
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
        // POINTER ON A FULL CELL, exactly as a bag cell does. The cursor is
        // the only affordance a hover card gets — there is no room on a 40px
        // cell for a hint, and the bag already taught this gesture.
        //
        // THE MOUSE IS TAKEN BACK PER CELL, NOT PER PANEL. `hud-layer` hands
        // every click to the canvas so the trigger works wherever the cursor
        // is; a panel that opted back in wholesale would put a dead rectangle
        // in the corner of the screen. An EMPTY cell stays transparent to the
        // mouse for the same reason — there is nothing to hover, so there is
        // no reason to eat a click.
        shown ? 'pointer-events-auto cursor-pointer' : null,
      )}
      onPointerEnter={() => {
        if (!shown) return;
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
    >
      {shown ? (
        <LootIcon
          frame={shown.frame}

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
      {/*
        ROUNDS, ON THE CELL. Per weapon rather than one counter beside the
        belt, because two guns can be on two calibres and "how much ammo do I
        have" has no single answer. The knife's cell carries no number at all
        — `ammo` is null there — and that absence is the clearest thing the
        HUD can say about the one weapon that never runs out.

        Empty goes red rather than hidden: a zero the player can read is what
        turns a dry trigger into a decision they made instead of a bug.
      */}
      {shown && shown.ammo !== null ? (
        <span
          className={cn(
            'absolute right-0.5 bottom-px text-[11px] leading-[11px] tabular-nums',
            shown.ammo > 0 ? 'text-ink-muted' : 'text-hp-low',
          )}
        >
          {shown.ammo}
        </span>
      ) : null}
    </div>
  );
}
