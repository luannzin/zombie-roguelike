/**
 * Hover card for a bag item. Lives in a portal so the glass does not warp
 * it off the slot it is pointing at.
 */

import { createPortal } from 'react-dom';
import type { HudInventorySlot } from '../../game/hud-store';
import type { LootRarity } from '../../net/protocol';
import { LootCardRow } from './LootCardRow';
import { TooltipCard } from './TooltipCard';

export interface LootCardProps {
  item: HudInventorySlot;
  x: number;
  y: number;
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

export function LootCard({ item, x, y }: LootCardProps) {
  return createPortal(
    <div
      className="pointer-events-none fixed top-0 left-0 z-40"
      style={{
        transform: `translate(${Math.round(x)}px, ${Math.round(y)}px) translate(-50%, -100%) translateY(-6px)`,
      }}
    >
      <TooltipCard>
        <p className={RARITY_CLASS[item.rarity]}>{item.name}</p>
        <p className="text-ink-muted">{RARITY_LABEL[item.rarity]}</p>
        <LootCardRow label="PESO" value={String(item.weight)} />
        <LootCardRow label="VALOR" value={String(item.value)} />
        {item.qty > 1 ? <LootCardRow label="QTD" value={String(item.qty)} /> : null}
      </TooltipCard>
    </div>,
    document.body,
  );
}
