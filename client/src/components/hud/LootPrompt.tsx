/**
 * Collect prompt on a world drop. One use of `Tooltip`. Mounted only while
 * a drop is in reach, so the enter animation is the approach, not a 5 Hz
 * flicker. A full bag keeps the pin and changes the copy — hiding it would
 * look like the drop vanished.
 *
 * Three states, and the middle one is the whole reason this is not a
 * boolean. A full BELT with a gun in hand is not a refusal, it is a trade,
 * and the prompt has to name both halves of it: what you would pick up is
 * on the ground in front of you, but what you would put down is in your
 * hands where you cannot see it.
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

  if (prompt.swap) {
    return (
      <Tooltip anchor="loot">
        Aperte <TooltipKey>E</TooltipKey> para trocar{' '}
        {/* The gun being given up is muted and the one being gained takes
            its rarity colour, so the direction of the trade is legible
            before either name is read. */}
        <span className="text-ink-muted">{prompt.swap}</span> por{' '}
        <span className={RARITY_CLASS[prompt.rarity]}>{prompt.name}</span>
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
