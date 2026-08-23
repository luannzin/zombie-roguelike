/**
 * Hover card for a bag item: name, rarity, weight, value.
 *
 * CARGO HAS NO STATS, which is why this is not `GearCard`. A crown and a
 * radio do exactly one thing — weigh something and be worth something — and a
 * card that tried to describe them the way it describes a rifle would be four
 * empty rows. The two cards share their chrome (`HoverCard`) and nothing else,
 * because they are answering two different questions: "what will this fetch"
 * and "what does this do".
 */

import type { HudInventorySlot } from '../../game/hud-store';
import type { LootRarity } from '../../net/protocol';
import { HoverCard, type HoverAnchor } from './HoverCard';
import { LootCardRow } from './LootCardRow';
import { formatWeight } from './WeightBar';

export type LootCardAnchor = HoverAnchor;

export interface LootCardProps {
  item: HudInventorySlot;
  anchor: LootCardAnchor;
}

const RARITY_LABEL: Record<LootRarity, string> = {
  common: 'Comum',
  uncommon: 'Incomum',
  rare: 'Raro',
  epic: 'Épico',
  legendary: 'Lendário',
};

const RARITY_CLASS: Record<LootRarity, string> = {
  common: 'text-rarity-common',
  uncommon: 'text-rarity-uncommon',
  rare: 'text-rarity-rare',
  epic: 'text-rarity-epic',
  legendary: 'text-rarity-legendary',
};

export function LootCard({ item, anchor }: LootCardProps) {
  return (
    <HoverCard anchor={anchor} fitKey={`${item.key}:${item.qty}:${item.rarity}`}>
      <p className={RARITY_CLASS[item.rarity]}>{item.name}</p>
      <p className={RARITY_CLASS[item.rarity]}>{RARITY_LABEL[item.rarity]}</p>
      <LootCardRow label="PESO" value={`${formatWeight(item.weight)}kg`} />
      <LootCardRow label="VALOR" value={String(item.value)} />
      {item.qty > 1 ? <LootCardRow label="QTD" value={String(item.qty)} /> : null}
    </HoverCard>
  );
}
