/**
 * Collect prompt on a world drop. One use of `Tooltip`. Mounted only while
 * a drop is in reach, so the enter animation is the approach, not a 5 Hz
 * flicker. A full bag keeps the pin and changes the copy — hiding it would
 * look like the drop vanished.
 */

import type { HudLootPrompt } from '../../game/hud-store';
import type { LootRarity } from '../../net/protocol';
import { Tooltip, TooltipKey } from './Tooltip';

export interface LootPromptProps {
  prompt: HudLootPrompt | null;
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

  if (prompt.full) {
    return (
      <Tooltip anchor="loot">
        <span className="text-hp-low">Inventário Cheio</span>
      </Tooltip>
    );
  }

  return (
    <Tooltip anchor="loot">
      Aperte <TooltipKey>E</TooltipKey> para coletar{' '}
      <span className={RARITY_CLASS[prompt.rarity]}>{prompt.name}</span>
    </Tooltip>
  );
}
