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
 *
 * A REFUSAL SAYS WHY, and it used to say the wrong thing twice out of three
 * times. "Inventário Cheio" was printed over a box of rifle rounds by a
 * player with an empty bag — which is not true, does not explain anything,
 * and teaches them that the prompt lies. There are three refusals in this
 * game and only ONE of them is about space:
 *
 *   bag       no free cell and no stack. The original, and the only one the
 *             old copy fitted
 *   calibre   ammunition for a weapon nobody in your hands can fire. Not a
 *             refusal about YOU at all — the rounds belong to whoever brought
 *             the gun, so the copy names the calibre rather than scolding
 *   reserve   ammunition you can fire and are already carrying the most of.
 *             Muted rather than red: nothing is wrong, you are simply full,
 *             and the box will still be there on the walk back
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
    if (prompt.reason === 'calibre') {
      return (
        <Tooltip anchor="loot">
          {/* The NAME leads, because the name is the answer: "Munição de
              rifle" over a body holding a pistol explains itself without the
              sentence under it having to work hard. */}
          <span className="text-ink-muted">
            <span className={RARITY_CLASS[prompt.rarity]}>{prompt.name}</span> — você não
            tem uma arma desse calibre
          </span>
        </Tooltip>
      );
    }
    if (prompt.reason === 'reserve') {
      return (
        <Tooltip anchor="loot">
          <span className="text-ink-muted">
            <span className={RARITY_CLASS[prompt.rarity]}>{prompt.name}</span> — reserva
            cheia
          </span>
        </Tooltip>
      );
    }
    return (
      <Tooltip anchor="loot">
        <span className="text-hp-low">Mochila cheia</span>
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
