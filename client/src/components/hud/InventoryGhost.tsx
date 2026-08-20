/**
 * The bag item under the cursor while it is being dragged. Portaled so the
 * HUD glass does not warp it off the pointer.
 */

import { createPortal } from 'react-dom';
import type { HudInventorySlot } from '../../game/hud-store';
import { LootIcon } from './LootIcon';

export interface InventoryGhostProps {
  item: HudInventorySlot;
  x: number;
  y: number;
}

export function InventoryGhost({ item, x, y }: InventoryGhostProps) {
  return createPortal(
    <div
      className="pointer-events-none fixed top-0 left-0 z-50"
      style={{
        transform: `translate(${Math.round(x)}px, ${Math.round(y)}px) translate(-50%, -50%)`,
      }}
      aria-hidden="true"
    >
      <LootIcon frame={item.frame} zoom={2} />
    </div>,
    document.body,
  );
}
