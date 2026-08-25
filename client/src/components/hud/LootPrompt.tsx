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
 * THE OBJECT IS DESCRIBED ABOVE THE LINE, marked against what the player is
 * already carrying — the same card the shop shows over a table, in the same
 * slot of the same tooltip. That used to be the shop's alone on the argument
 * that a stall is where a night's extraction gets spent; the grass turned out
 * to be the harder case. A purchase can be reconsidered at the counter, but a
 * pickup is instant and takes the old thing off you on the frame it lands, so
 * the comparison has to happen BEFORE the press or it happens by reading the
 * belt afterwards with the axe already on the floor behind you.
 *
 * A REFUSAL SAYS WHY, and it used to say the wrong thing for most of them.
 * "Inventário Cheio" was printed over a box of rifle rounds by a player with
 * an empty bag, over a bandage by a player with four free slots, and over the
 * axe they were already carrying. There are SIX refusals in this game and only
 * ONE of them is about pocket space:
 *
 *   bag       no free cell and no stack. The original, and the only one the
 *             old copy fitted
 *   calibre   ammunition for a weapon nobody in your hands can fire. Not a
 *             refusal about YOU at all — the rounds belong to whoever brought
 *             the gun, so the copy names the calibre rather than scolding
 *   reserve   ammunition you can fire and are already carrying the most of.
 *             Muted rather than red: nothing is wrong, you are simply full,
 *             and the box will still be there on the walk back
 *   med       both medical cells are full. Medicine has never been in the
 *             pocket, so this one was lying about a container the player
 *             could have gone and emptied to no effect
 *   worn      the piece already on that part of the body, in the same or
 *             better condition
 *   blade     the lâmina already in the cell. This is the one that was worst:
 *             it did not print a refusal at all, it offered to trade the GUN
 *             in your hands for a knife you were already holding
 *   shield    one is the limit
 *
 * MOST OF THEM NAME THE OBJECT FIRST, because the name is usually most of the
 * answer: "Machado — você já carrega esta lâmina" needs no second sentence to
 * explain itself. The two that do NOT are the ones where the name adds
 * nothing — a full bag is not about the thing on the ground at all, and a
 * piece you are already wearing is one the card above has just drawn, named
 * and marked with a column of level arrows. Those two are whole sentences on
 * their own line.
 */

import type { HudLootPrompt } from '../../game/hud-store';
import type { LootRarity } from '../../net/protocol';
import { GearCardBody } from './GearCard';
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

/**
 * The tail of a named refusal. The subject is always the object's own name in
 * its rarity colour, so these are only ever the predicate — which is what
 * keeps them one line each and stops any of them growing into a sentence
 * about the player.
 */
const REFUSAL_COPY: Record<string, string> = {
  calibre: 'você não tem uma arma desse calibre',
  reserve: 'reserva cheia',
  med: 'cinto médico cheio',
  blade: 'você já carrega esta lâmina',
  shield: 'você já carrega um escudo',
};

/**
 * The refusals that stand alone, without the object's name in front of them.
 *
 * `worn` is here because the name would be said twice: the card directly above
 * this line is drawing the piece, naming it, and marking every one of its rows
 * level against the one on the body. Repeating "Elmo de Aço —" under a picture
 * of a steel helmet is ceremony.
 */
const REFUSAL_LINE: Record<string, string> = {
  worn: 'Você já tem este item equipado',
};

export function LootPrompt({ prompt }: LootPromptProps) {
  if (!prompt) return null;

  // The description rides above every state, refusals included. A player being
  // told they cannot take something is exactly the player who wants to know
  // what it was — and on a `worn` or `blade` refusal the card is the proof:
  // the arrows are all level or red, which is the reason.
  const about = prompt.card ? (
    <GearCardBody card={prompt.card} frame={prompt.frame} />
  ) : undefined;
  const name = <span className={RARITY_CLASS[prompt.rarity]}>{prompt.name}</span>;

  if (prompt.full) {
    const line = prompt.reason ? REFUSAL_LINE[prompt.reason] : undefined;
    if (line) {
      return (
        <Tooltip anchor="loot" above={about}>
          <span className="text-ink-muted">{line}</span>
        </Tooltip>
      );
    }
    const copy = prompt.reason ? REFUSAL_COPY[prompt.reason] : undefined;
    if (copy) {
      return (
        <Tooltip anchor="loot" above={about}>
          {/* The NAME leads, because the name is the answer: "Munição de
              rifle" over a body holding a pistol explains itself without the
              sentence under it having to work hard. */}
          <span className="text-ink-muted">
            {name} — {copy}
          </span>
        </Tooltip>
      );
    }
    return (
      <Tooltip anchor="loot" above={about}>
        <span className="text-hp-low">Mochila cheia</span>
      </Tooltip>
    );
  }

  if (prompt.swap) {
    return (
      <Tooltip anchor="loot" above={about}>
        Aperte <TooltipKey>E</TooltipKey> para trocar{' '}
        {/* The gun being given up is muted and the one being gained takes
            its rarity colour, so the direction of the trade is legible
            before either name is read. */}
        <span className="text-ink-muted">{prompt.swap}</span> por {name}
      </Tooltip>
    );
  }

  return (
    <Tooltip anchor="loot" above={about}>
      Aperte <TooltipKey>E</TooltipKey> para coletar {name}
    </Tooltip>
  );
}
