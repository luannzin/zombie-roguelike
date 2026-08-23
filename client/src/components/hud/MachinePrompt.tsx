/**
 * Prompt on the upgrade machine. One use of `Tooltip`, pinned to the cabinet.
 *
 * IT ALWAYS HAS AN OFFER, and that is the whole reason it has four states
 * instead of one. A machine that only spoke to somebody already holding a
 * level would be a piece of scenery for the entire first shop — the player has
 * to be told, standing in front of it, what this thing eats. It eats a LEVEL
 * first and GOLD after, so the card leads with whichever one the next press
 * would actually spend.
 *
 * The number rides the `end` slot for the same reason a price does on a table:
 * it is a number, not part of the sentence, and it keeps the card to one line
 * whatever the copy says. Which number depends on what the press costs —
 * banked pulls while they last, the ladder's price once they run out — because
 * two figures on one line is a card nobody reads at a glance.
 */

import type { HudMachinePrompt } from '../../game/hud-store';
import { CoinIcon } from './CoinIcon';
import { Tooltip, TooltipKey } from './Tooltip';

export interface MachinePromptProps {
  prompt: HudMachinePrompt | null;
}

export function MachinePrompt({ prompt }: MachinePromptProps) {
  if (!prompt) return null;

  const banked = (
    <span className={prompt.spins > 0 ? 'text-rarity-legendary' : 'text-ink-muted'}>
      {prompt.spins} {prompt.spins === 1 ? 'giro' : 'giros'}
    </span>
  );
  // AFFORDABILITY IS ONLY A COLOUR, the same rule the shop's tables run on:
  // the price is always legible, and red is what says the party cannot cover
  // it. A number that vanished when it was out of reach would take the goal
  // with it.
  const price = (
    <span className={prompt.mode === 'broke' ? 'text-hp-low' : 'text-ink'}>
      <CoinIcon className="mr-1 inline-block align-[-1px]" />
      {prompt.price}
    </span>
  );

  if (prompt.mode === 'busy') {
    return (
      <Tooltip anchor="machine">
        <span className="text-ink-muted">A máquina está rodando</span>
      </Tooltip>
    );
  }

  // A LEVEL IS SPENT BEFORE GOLD IS, so while one is banked the card says so
  // and the price stays off it — nobody standing on a free pull is shopping.
  if (prompt.mode === 'ready') {
    return (
      <Tooltip anchor="machine" end={banked}>
        <TooltipKey>E</TooltipKey> puxar a alavanca
      </Tooltip>
    );
  }

  if (prompt.mode === 'broke') {
    return (
      <Tooltip anchor="machine" end={price}>
        <span className="text-hp-low">Ouro insuficiente</span>
      </Tooltip>
    );
  }

  // The verb is "pagar", not "comprar": what leaves the tray is the same
  // canister a level pays for, so this is the same act at a different price
  // rather than a second thing the cabinet sells.
  return (
    <Tooltip anchor="machine" end={price}>
      <TooltipKey>E</TooltipKey> pagar por um giro
    </Tooltip>
  );
}
