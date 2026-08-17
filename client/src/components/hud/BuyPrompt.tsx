/**
 * Buy prompt on a merchant's table. One use of `Tooltip`, pinned to the stall.
 *
 * The PRICE rides in the tooltip's `end` slot rather than in the copy, which
 * is what keeps this to one line: `end` is `shrink-0` and sits outside the
 * sentence, so the card reads "Aperte E para comprar AK-47 · 🪙 276" whatever
 * the weapon is called.
 *
 * AFFORDABILITY IS ONLY A COLOUR. A price the party cannot cover turns red and
 * says nothing else — the number and the empty purse next to it are already
 * the whole message, and spelling it out made the card long enough to wrap.
 * The stall is deliberately still offered rather than hidden: a shop that only
 * shows what you can already afford has no aspirational shelf, and the AWP
 * standing there priced out of reach on day three is doing more work than a
 * tutorial line about saving up would.
 *
 * Three states in the copy, and the middle one is why `full` is not enough on
 * its own: a full belt with a gun in hand is a TRADE, and naming both halves
 * matters more here than on a world drop, because the gun being given up is
 * being exchanged for one that costs money.
 */

import type { HudBuyPrompt } from '../../game/hud-store';
import type { LootRarity } from '../../net/protocol';
import { CoinIcon } from './CoinIcon';
import { Tooltip, TooltipKey } from './Tooltip';

export interface BuyPromptProps {
  prompt: HudBuyPrompt | null;
}

const RARITY_CLASS: Record<LootRarity, string> = {
  common: 'text-rarity-common',
  uncommon: 'text-rarity-uncommon',
  rare: 'text-rarity-rare',
  epic: 'text-rarity-epic',
  legendary: 'text-rarity-legendary',
};

export function BuyPrompt({ prompt }: BuyPromptProps) {
  if (!prompt) return null;

  const name = <span className={RARITY_CLASS[prompt.rarity]}>{prompt.name}</span>;
  const price = (
    <span className={prompt.afford ? 'text-ink' : 'text-hp-low'}>
      <CoinIcon className="mr-1 inline-block align-[-1px]" />
      {prompt.price}
    </span>
  );

  if (prompt.full) {
    return (
      <Tooltip anchor="buy" end={price}>
        <span className="text-hp-low">Cinto cheio</span>
      </Tooltip>
    );
  }

  if (prompt.swap) {
    return (
      <Tooltip anchor="buy" end={price}>
        <TooltipKey>E</TooltipKey>{' '}
        {/* Same read as the loot trade: what you give up is muted, what you
            get takes its rarity colour, so the direction is legible before
            either name is. */}
        trocar <span className="text-ink-muted">{prompt.swap}</span> por {name}
      </Tooltip>
    );
  }

  return (
    <Tooltip anchor="buy" end={price}>
      <TooltipKey>E</TooltipKey> comprar {name}
    </Tooltip>
  );
}
