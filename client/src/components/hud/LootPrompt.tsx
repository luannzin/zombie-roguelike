/**
 * Collect prompt on a world drop. One use of `Tooltip`. Mounted only while
 * E will collect, so the enter animation is the approach, not a 5 Hz flicker.
 */

import type { LootRarity } from '../../net/protocol';
import { Tooltip, TooltipKey } from './Tooltip';

export interface LootPromptInfo {
  id: string;
  name: string;
  rarity: LootRarity;
}

export interface LootPromptProps {
  prompt: LootPromptInfo | null;
}

const RARITY_CLASS: Record<LootRarity, string> = {
  common: 'text-rarity-common',
  uncommon: 'text-rarity-uncommon',
  rare: 'text-rarity-rare',
  epic: 'text-rarity-epic',
  legendary: 'text-rarity-legendary',
};

export function LootPrompt({ prompt }: LootPromptProps) {
  if (!prompt) return null;

  return (
    <Tooltip anchor="loot">
      Aperte <TooltipKey>E</TooltipKey> para coletar{' '}
      <span className={RARITY_CLASS[prompt.rarity]}>{prompt.name}</span>
    </Tooltip>
  );
}
