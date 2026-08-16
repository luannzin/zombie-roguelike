/**
 * The belt: two gun cells and, after them, the knife. 1 / 2 / 3 selects; the
 * same key again holsters. Always visible — this is a loadout, not a drawer.
 *
 * The knife's cell is the last one and it is never empty, which is the only
 * thing the player has to learn from looking at this: the first two change
 * over a run and the third never does. A run also OPENS with the first two
 * empty, so the hairline before the last cell is doing real work on the
 * first screen — it is the difference between "you have nothing" and "you
 * have this". No label: a cell that is always full and always in the same
 * place explains itself the second time somebody presses 3.
 */

import { Fragment } from 'react';
import type { HudHotbar } from '../../game/hud-store';
import { Panel } from './Panel';
import { HotbarSlot } from './HotbarSlot';

export interface HotbarProps {
  hotbar: HudHotbar | null;
}

export function Hotbar({ hotbar }: HotbarProps) {
  if (!hotbar) return null;

  const last = hotbar.slots.length - 1;

  return (
    <Panel className="w-44 px-2.5 py-2">
      <div className="mb-1.5 flex items-baseline justify-between gap-2 text-[11px] leading-[11px]">
        <span className="text-ink-muted tracking-[0.06em]">ARMAS</span>
        <span className="text-ink-muted tabular-nums">1 2 3</span>
      </div>
      <div className="flex items-center gap-1.5">
        {hotbar.slots.map((item, index) => (
          <Fragment key={index}>
            {index === last && last > 0 ? (
              <span aria-hidden className="bg-track-border h-8 w-px shrink-0" />
            ) : null}
            <HotbarSlot
              // Remounting on every pick is what replays the select animation.
              key={hotbar.held === index ? hotbar.picks : 'off'}
              index={index}
              item={item}
              lootFrames={hotbar.lootFrames}
              selected={hotbar.held === index}
            />
          </Fragment>
        ))}
      </div>
    </Panel>
  );
}
