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
 *
 * THE ARROWS ARE NOT DECIDED HERE EITHER. `gear-card.ts` marks a row up, down
 * or level against whatever the player already has in that place, and this
 * file only knows which glyph and which colour that is. The comparison is a
 * fact about a catalog and a loadout; putting it in a component would make
 * the shop's card and the drop's card two places to get it wrong, and the
 * shop's would be the one nobody checked.
 *
 * A ROW WITH NO ARROW IS THE COMMON CASE and it must not reserve space for
 * one. The belt's own cells and the armour panel's hover uncompared cards —
 * they ARE the current thing — so an empty gutter on every row of those would
 * be a column of nothing, three surfaces wide, paid for by every card in the
 * game to serve two.
 */

import type { GearStat, HudGearCard } from '../../game/gear-card';
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

/**
 * The mark beside a compared value.
 *
 * A TRIANGLE AND A DASH, in the two colours the health bar already uses for
 * good and bad — so the vocabulary is one a player learned in the first
 * minute of the game rather than a new legend to read. Level is a DASH rather
 * than a grey triangle: two triangles and a third thing that is also a
 * triangle would mean the shape stopped carrying the meaning and the colour
 * had to carry all of it, which fails for the eight percent of people it
 * always fails for.
 *
 * `aria-hidden`, because the arrow is a restatement: the two numbers are both
 * on the glass and the mark is only there to save the comparison being done
 * in the player's head while something walks toward them.
 */
const DELTA_MARK: Record<NonNullable<GearStat['delta']>, string> = {
  up: '▲',
  down: '▼',
  same: '–',
};

const DELTA_CLASS: Record<NonNullable<GearStat['delta']>, string> = {
  up: 'text-hp-high',
  down: 'text-hp-low',
  same: 'text-ink-muted',
};

function Delta({ delta }: { delta: GearStat['delta'] }) {
  if (!delta) return null;
  return (
    <span aria-hidden className={cn('shrink-0 text-[9px]', DELTA_CLASS[delta])}>
      {DELTA_MARK[delta]}
    </span>
  );
}

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
          <span className="flex items-center gap-1">
            <Delta delta={lead.delta} />
            <span className="text-ink-accent tabular-nums">{lead.value}</span>
          </span>
        </p>
      ) : null}

      {/*
        THE ULTIMATE, BY NAME. It is not a stat and it is not in the row list —
        it is a line of its own, in the accent, under the numbers.

        It earns the space at a SHOP TABLE more than anywhere else. Everything
        above this line is comparable — damage against damage, rate against
        rate — and this is the one thing on the card that is not a number at
        all: it is the sentence "this weapon can do something the others
        cannot, if you dress for it". A player choosing between a katana and an
        axe with four hundred gold has no other way to find that out before
        paying.
      */}
      {card.ultimate ? (
        <p className="border-track-border text-ink-accent mt-0.5 border-t pt-1">
          ⚡ {card.ultimate}
        </p>
      ) : null}

      {rest.length ? (
        <div className={cn('flex flex-col', lead ? null : 'border-track-border mt-0.5 border-t pt-1')}>
          {rest.map((stat) => (
            <p key={stat.label} className="flex justify-between gap-4">
              <span className="text-ink-muted">{stat.label}</span>
              <span className="flex items-center gap-1">
                <Delta delta={stat.delta} />
                <span className="text-ink tabular-nums">{stat.value}</span>
              </span>
            </p>
          ))}
        </div>
      ) : null}
    </div>
  );
}
