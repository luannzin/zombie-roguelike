/**
 * Prompt on the merchant. One use of `Tooltip`, pinned over his head.
 *
 * HIS OWN CARD, not a mode on the cabinet's. The machine sells SKILLS and he
 * sells OBJECTS, and a party pressing one lever for both would have no idea
 * which of the two they were bargaining with — which is also why the two
 * fixtures stand at opposite ends of the room.
 *
 * THE PRICE IS ALWAYS ON IT, in every state that has one, and only its COLOUR
 * says whether the party can cover it. That is the same rule the tables run
 * on: a number that vanished when it was out of reach would take the goal with
 * it, and saving up for something you can no longer see is not a plan.
 *
 * `empty` is a real state and not an oversight. A party who bought the whole
 * shelf has nothing to reroll, and the card says so rather than quoting a
 * price for a shuffle of nothing — charging for an outcome the game already
 * knows is empty is the one thing a doubling ladder must never do.
 */

import type { HudRerollPrompt } from '../../game/hud-store';
import { CoinIcon } from './CoinIcon';
import { Tooltip, TooltipKey } from './Tooltip';

export interface RerollPromptProps {
  prompt: HudRerollPrompt | null;
}

export function RerollPrompt({ prompt }: RerollPromptProps) {
  if (!prompt) return null;

  if (prompt.mode === 'empty') {
    return (
      <Tooltip anchor="merchant">
        <span className="text-ink-muted">Não sobrou nada nas mesas</span>
      </Tooltip>
    );
  }

  const price = (
    <span className={prompt.mode === 'broke' ? 'text-hp-low' : 'text-ink'}>
      <CoinIcon className="mr-1 inline-block align-[-1px]" />
      {prompt.price}
    </span>
  );

  return (
    <Tooltip anchor="merchant" end={price}>
      <TooltipKey>E</TooltipKey> trocar a mercadoria
    </Tooltip>
  );
}
