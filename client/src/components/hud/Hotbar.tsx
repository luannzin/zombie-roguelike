/**
 * Three gun slots above the lantern. 1 / 2 / 3 selects; the same key again
 * holsters. Always visible — this is a loadout, not a drawer.
 */

import type { HudHotbar } from '../../game/hud-store';
import { Panel } from './Panel';
import { HotbarSlot } from './HotbarSlot';

export interface HotbarProps {
  hotbar: HudHotbar | null;
}

export function Hotbar({ hotbar }: HotbarProps) {
  if (!hotbar) return null;

  return (
    <Panel className="w-40 px-2.5 py-2">
      <div className="mb-1.5 flex items-baseline justify-between gap-2 text-[11px] leading-[11px]">
        <span className="text-ink-muted tracking-[0.06em]">ARMAS</span>
        <span className="text-ink-muted tabular-nums">1 2 3</span>
      </div>
      <div className="flex justify-between gap-1.5">
        {hotbar.slots.map((item, index) => (
          <HotbarSlot
            key={`${index}-${hotbar.held === index ? hotbar.picks : 'off'}`}
            index={index}
            item={item}
            lootFrames={hotbar.lootFrames}
            selected={hotbar.held === index}
          />
        ))}
      </div>
    </Panel>
  );
}
