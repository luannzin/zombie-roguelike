/**
 * Left-side pocket. Collapsed it is the backpack and a TAB hint; TAB
 * expands the slots in place — not a dialog, not a new layer.
 */

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { HudInventory } from '../../game/hud-store';
import {
  dropInventoryAnchor,
  writeInventoryAnchor,
} from '../../game/inventory-anchors';
import { cn } from '@/lib/utils';
import { InventorySlot } from './InventorySlot';
import { Panel } from './Panel';
import { TooltipKey } from './Tooltip';
import { WeightBar } from './WeightBar';

export interface InventoryProps {
  inventory: HudInventory | null;
}

const PACK = 16;
const PACK_ZOOM = 2;

export function Inventory({ inventory }: InventoryProps) {
  const packRef = useRef<HTMLDivElement>(null);
  const caught = useCatchKick(inventory?.catches ?? 0);
  const refused = useCatchKick(inventory?.refusals ?? 0);

  useLayoutEffect(() => {
    const el = packRef.current;
    if (!el) return;
    const write = () => {
      const box = el.getBoundingClientRect();
      writeInventoryAnchor('pack', box.left + box.width / 2, box.top + box.height / 2);
    };
    write();
    const observer = new ResizeObserver(write);
    observer.observe(el);
    window.addEventListener('resize', write);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', write);
      dropInventoryAnchor('pack');
    };
  }, [inventory]);

  if (!inventory) return null;

  return (
    <div
      className={cn(
        'flex flex-col items-start gap-1.5',
        refused && 'animate-lantern-refused',
      )}
    >
      <div className="flex items-center gap-1.5">
        <div
          ref={packRef}
          className={cn('relative shrink-0', caught && 'animate-pack-catch')}
          style={{ width: PACK * PACK_ZOOM, height: PACK * PACK_ZOOM }}
        >
          <img
            src="/hud/backpack.png"
            alt=""
            className="pixelated h-full w-full"
          />
        </div>
        <span className="text-ink-muted text-[11px] leading-[11px]" aria-hidden="true">
          ▸
        </span>
        <TooltipKey>TAB</TooltipKey>
      </div>

      <div
        className="grid transition-[grid-template-rows] duration-300 ease-out motion-reduce:transition-none"
        style={{ gridTemplateRows: inventory.open ? '1fr' : '0fr' }}
      >
        <div className="overflow-hidden">
          <Panel className="px-2 pt-2 pb-2">
            <div className="flex gap-1">
              {inventory.slots.map((item, index) => (
                <InventorySlot
                  key={index}
                  index={index}
                  item={item}
                  lootFrames={inventory.lootFrames}
                />
              ))}
            </div>
            <WeightBar inventory={inventory} />
          </Panel>
        </div>
      </div>
    </div>
  );
}

function useCatchKick(count: number): boolean {
  const [kicking, setKicking] = useState(false);
  const [seen, setSeen] = useState(count);

  useEffect(() => {
    if (count === seen) return;
    setSeen(count);
    if (count <= 0) return;
    setKicking(true);
    const timer = window.setTimeout(() => setKicking(false), 280);
    return () => window.clearTimeout(timer);
  }, [count, seen]);

  return kicking;
}
