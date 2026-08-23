/**
 * The belt: two gun cells and, after them, the LÂMINA. 1 / 2 / 3 selects; the
 * same key again holsters. Always visible — this is a loadout, not a drawer.
 *
 * The blade's cell is the last one and it is never empty, which is the only
 * thing the player has to learn from looking at this: the first two change
 * over a run and the third is never blank. A run also OPENS with the first two
 * empty, so the hairline before the last cell is doing real work on the
 * first screen — it is the difference between "you have nothing" and "you
 * have this". No label: a cell that is always full and always in the same
 * place explains itself the second time somebody presses 3.
 *
 * HOVERING A CELL DESCRIBES WHAT IS IN IT, the same card the shop shows and
 * the armour panel hovers. A belt that could only tell you a weapon's name was
 * asking the player to remember eleven stat blocks — and the one number that
 * actually decides a fight, how many of these puts a walker down, was written
 * nowhere in the game.
 */

import { Fragment, useState } from 'react';
import type { HudHotbar, HudHotbarSlot } from '../../game/hud-store';
import { GearCardBody } from './GearCard';
import { HoverCard, type HoverAnchor } from './HoverCard';
import { Panel } from './Panel';
import { HotbarSlot } from './HotbarSlot';

export interface HotbarProps {
  hotbar: HudHotbar | null;
}

interface HoverState {
  item: HudHotbarSlot;
  anchor: HoverAnchor;
}

export function Hotbar({ hotbar }: HotbarProps) {
  const [hover, setHover] = useState<HoverState | null>(null);

  if (!hotbar) return null;

  const last = hotbar.slots.length - 1;
  // The hovered cell can empty under the pointer — a shield breaking takes its
  // cell with it — so the card is re-read off the live snapshot every render
  // rather than kept in state.
  const shown = hover ? (hotbar.slots.find((slot) => slot?.key === hover.item.key) ?? null) : null;

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
              selected={hotbar.held === index}
              onHover={(next, anchor) => setHover({ item: next, anchor })}
              onLeave={() => setHover(null)}
            />
          </Fragment>
        ))}
      </div>

      {shown?.card ? (
        <HoverCard anchor={hover!.anchor} fitKey={shown.key}>
          <GearCardBody card={shown.card} frame={shown.frame} />
        </HoverCard>
      ) : null}
    </Panel>
  );
}
