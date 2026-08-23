/**
 * The card that describes a piece of gear. One component, three surfaces.
 *
 * The belt hovers it, the armour panel hovers it, and the shop shows it
 * unprompted when you walk up to a table — and it is the SAME card in all
 * three, because it is the same object. A player who learns to read it at a
 * stall can read it on their own hip.
 *
 * THE HEADLINE IS THE FIRST THING AND IT IS NOT A ROW. `gear-card.ts` marks
 * exactly one stat as the lead: a gun's shots-to-kill, a plate's absorption, a
 * shield's rule. Everything under it is detail somebody may or may not want. A
 * card of eight equal rows is a spreadsheet, and nobody reads a spreadsheet
 * with something walking toward them.
 *
 * `Rows` is exported separately from `GearCard` because the shop's version
 * lives inside a world tooltip that already has its own chrome and its own
 * anchor — it needs the CONTENT without a second card around it.
 */

import type { HudGearCard } from '../../game/gear-card';
import type { LootRarity } from '../../net/protocol';
import { cn } from '@/lib/utils';
import { LootIcon } from './LootIcon';

const RARITY_CLASS: Record<LootRarity, string> = {
  common: 'text-rarity-common',
  uncommon: 'text-rarity-uncommon',
  rare: 'text-rarity-rare',
  epic: 'text-rarity-epic',
  legendary: 'text-rarity-legendary',
};

const RARITY_LABEL: Record<LootRarity, string> = {
  common: 'Comum',
  uncommon: 'Incomum',
  rare: 'Raro',
  epic: 'Épico',
  legendary: 'Lendário',
};

export interface GearCardBodyProps {
  card: HudGearCard;
  /** The loot atlas frame, when the caller has one. Absent in the shop. */
  frame?: number;
  className?: string;
}

export function GearCardBody({ card, frame, className }: GearCardBodyProps) {
  const lead = card.stats.find((stat) => stat.lead);
  const rest = card.stats.filter((stat) => !stat.lead);

  return (
    <div className={cn('flex w-max flex-col gap-1', className)}>
      <div className="flex items-start gap-2">
        {frame === undefined ? null : (
          <LootIcon frame={frame} className="mt-px shrink-0" />
        )}
        <div className="flex flex-col">
          <span className={RARITY_CLASS[card.rarity]}>{card.name}</span>
          {/* The KIND and the RARITY on one line, muted: together they are
              "what is this and how good is its class", which is the question
              the name only half answers. `Elmo · Raro` fits where two rows
              would have pushed the numbers down. */}
          <span className="text-ink-muted">
            {card.kind} · <span className={RARITY_CLASS[card.rarity]}>{RARITY_LABEL[card.rarity]}</span>
          </span>
        </div>
      </div>

      {lead ? (
        <p className="border-track-border mt-0.5 flex justify-between gap-4 border-t pt-1">
          <span className="text-ink-muted">{lead.label}</span>
          <span className="text-ink-accent tabular-nums">{lead.value}</span>
        </p>
      ) : null}

      {rest.length ? (
        <div className={cn('flex flex-col', lead ? null : 'border-track-border mt-0.5 border-t pt-1')}>
          {rest.map((stat) => (
            <p key={stat.label} className="flex justify-between gap-4">
              <span className="text-ink-muted">{stat.label}</span>
              <span className="text-ink tabular-nums">{stat.value}</span>
            </p>
          ))}
        </div>
      ) : null}
    </div>
  );
}
