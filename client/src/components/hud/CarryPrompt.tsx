/**
 * The prompt on a downed teammate, and on your own bag. One use of `Tooltip`.
 *
 * ONE COMPONENT FOR BOTH HALVES OF ONE TRADE, because the player has to see it
 * as one. Picking somebody up costs the bag; walking back for the bag costs
 * putting them down. Two components would have been two vocabularies for a
 * single decision, and the second one would be the one nobody read.
 *
 * THE COST IS NAMED FIRST AND THE RESCUE SECOND: "largar mochila e carregar
 * {nome}". That ordering is the whole card. Picking up a teammate is the
 * obvious half — it is what the player is already walking over to do — and the
 * bag going down is the half they will only find out about afterwards if the
 * copy does not lead with it. A prompt that said "carregar {nome}" and then
 * silently emptied their pockets onto the grass would read as a bug the first
 * time and as a betrayal the second.
 *
 * IT IS NOT IN THE DANGER TONE. The pad's pickup call is (`RiftPrompt`) because
 * that press turns the whole map hostile and cannot be taken back; this one
 * costs something real and is completely reversible — the bag is right there,
 * and setting the body down gets you back to it. Red here would put the two on
 * the same footing and spend the one tone this HUD keeps for the press that
 * actually earns it. The COST gets the accent instead, which is enough to be
 * read before the verb without claiming to be a warning.
 *
 * THE PLATFORM LINE IS THE ONE THAT TEACHES THE MECHANIC. Putting a body down
 * anywhere is legal and means nothing; putting one down on a deck is the whole
 * rescue, and nothing else in the game says so. So the `drop` copy changes on
 * the deck, and that changed line is where a player learns that the platform
 * takes people as well as loot.
 */

import type { HudCarryPrompt } from '../../game/hud-store';
import { Tooltip, TooltipKey } from './Tooltip';

export interface CarryPromptProps {
  prompt: HudCarryPrompt | null;
}

export function CarryPrompt({ prompt }: CarryPromptProps) {
  if (!prompt) return null;

  // Their own nameplate colour, so the body on the floor and the name in the
  // sentence are visibly the same person. Falls back to the plain ink rather
  // than to a default colour — a wrong colour is worse than none.
  const who = prompt.name ? (
    <span style={prompt.color ? { color: prompt.color } : undefined}>{prompt.name}</span>
  ) : (
    <span className="text-ink">o jogador</span>
  );

  if (prompt.mode === 'lift') {
    return (
      <Tooltip anchor="carry">
        Aperte <TooltipKey>E</TooltipKey> para{' '}
        {/* THE COST, IN THE ACCENT, BEFORE THE VERB. See the header. */}
        <span className="text-ink-accent">largar a mochila</span> e carregar {who}
      </Tooltip>
    );
  }

  if (prompt.mode === 'drop') {
    if (prompt.onPad) {
      return (
        <Tooltip anchor="carry">
          Aperte <TooltipKey>E</TooltipKey> para deixar {who} na plataforma{' '}
          {/* The consequence, muted and on the same line: this is the only
              place putting a body down does anything, and the thing it does
              happens LATER, on somebody else's press. */}
          <span className="text-ink-muted">· a extração o revive</span>
        </Tooltip>
      );
    }
    return (
      <Tooltip anchor="carry">
        Aperte <TooltipKey>E</TooltipKey> para largar {who}
      </Tooltip>
    );
  }

  if (prompt.mode === 'busy') {
    return (
      <Tooltip anchor="carry">
        <span className="text-ink-muted">
          Largue o jogador para pegar a mochila
        </span>
      </Tooltip>
    );
  }

  // THE BAG. The count rides in the sentence rather than in `end`, because it
  // is the reason to press: a bag with a night in it and a bag the platforms
  // already emptied are the same sprite in the same grass, and the number is
  // the only thing that tells them apart before the pickup.
  return (
    <Tooltip anchor="carry">
      Aperte <TooltipKey>E</TooltipKey> para pegar sua mochila
      {prompt.count ? (
        <span className="text-ink-muted"> · {prompt.count} item{prompt.count === 1 ? '' : 's'}</span>
      ) : (
        <span className="text-ink-muted"> · vazia</span>
      )}
    </Tooltip>
  );
}
