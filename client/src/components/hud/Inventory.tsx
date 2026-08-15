/**
 * Left-side pocket. Collapsed it is the backpack and a TAB hint; TAB
 * expands the slots in place — not a dialog, not a new layer.
 * Hover opens a loot card. Drag a filled cell off the panel to toss it.
 */

import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent } from 'react';
import type { HudInventory, HudInventorySlot } from '../../game/hud-store';
import { requestInventoryDrop } from '../../game/inventory-actions';
import {
  dropInventoryAnchor,
  writeInventoryAnchor,
} from '../../game/inventory-anchors';
import { cn } from '@/lib/utils';
import { InventoryGhost } from './InventoryGhost';
import { InventorySlot } from './InventorySlot';
import { LootCard } from './LootCard';
import { Panel } from './Panel';
import { TooltipKey } from './Tooltip';
import { WeightBar } from './WeightBar';

export interface InventoryProps {
  inventory: HudInventory | null;
}

const PACK = 16;
const PACK_ZOOM = 2;
const DRAG_SLOP = 5;

interface HoverState {
  item: HudInventorySlot;
  x: number;
  y: number;
}

interface DragState {
  index: number;
  item: HudInventorySlot;
  x: number;
  y: number;
}

export function Inventory({ inventory }: InventoryProps) {
  const packRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const gripRef = useRef<{
    index: number;
    item: HudInventorySlot;
    x: number;
    y: number;
    pointerId: number;
  } | null>(null);
  const pullingRef = useRef(false);
  const caught = useCatchKick(inventory?.catches ?? 0);
  const refused = useCatchKick(inventory?.refusals ?? 0);
  const [hover, setHover] = useState<HoverState | null>(null);
  const [drag, setDrag] = useState<DragState | null>(null);

  useEffect(() => {
    if (!drag) return;
    const previous = document.body.style.cursor;
    document.body.style.cursor = 'grabbing';
    return () => {
      document.body.style.cursor = previous;
    };
  }, [drag]);

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

  const onGrip = (
    index: number,
    item: HudInventorySlot,
    event: PointerEvent<HTMLDivElement>,
  ) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    gripRef.current = {
      index,
      item,
      x: event.clientX,
      y: event.clientY,
      pointerId: event.pointerId,
    };
  };

  const onDrag = (event: PointerEvent<HTMLDivElement>) => {
    const grip = gripRef.current;
    if (!grip || event.pointerId !== grip.pointerId) return;
    const dx = event.clientX - grip.x;
    const dy = event.clientY - grip.y;
    if (!pullingRef.current && dx * dx + dy * dy < DRAG_SLOP * DRAG_SLOP) return;
    pullingRef.current = true;
    setHover(null);
    setDrag({
      index: grip.index,
      item: grip.item,
      x: event.clientX,
      y: event.clientY,
    });
  };

  const onRelease = (event: PointerEvent<HTMLDivElement>) => {
    const grip = gripRef.current;
    if (!grip || event.pointerId !== grip.pointerId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    const pulled = pullingRef.current;
    const index = grip.index;
    gripRef.current = null;
    pullingRef.current = false;
    setDrag(null);
    if (!pulled) return;
    const box = panelRef.current?.getBoundingClientRect();
    if (!box) return;
    const { clientX: x, clientY: y } = event;
    const inside = x >= box.left && x <= box.right && y >= box.top && y <= box.bottom;
    if (!inside) requestInventoryDrop(index);
  };

  return (
    <div
      className={cn(
        'pointer-events-auto flex flex-col items-start gap-1.5',
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
          <div ref={panelRef}>
            <Panel className="px-2 pt-2 pb-2">
              <div className="flex gap-1">
                {inventory.slots.map((item, index) => (
                  <InventorySlot
                    key={index}
                    index={index}
                    item={item}
                    lootFrames={inventory.lootFrames}
                    dragging={drag?.index === index}
                    onHover={(next, x, y) => {
                      if (drag) return;
                      setHover({ item: next, x, y });
                    }}
                    onLeave={() => setHover(null)}
                    onGrip={onGrip}
                    onDrag={onDrag}
                    onRelease={onRelease}
                  />
                ))}
              </div>
              <WeightBar inventory={inventory} />
            </Panel>
          </div>
        </div>
      </div>

      {hover && !drag ? <LootCard item={hover.item} x={hover.x} y={hover.y} /> : null}
      {drag ? (
        <InventoryGhost
          item={drag.item}
          x={drag.x}
          y={drag.y}
          lootFrames={inventory.lootFrames}
        />
      ) : null}
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
