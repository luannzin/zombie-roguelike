/**
 * Prompt on the upgrade machine. One use of `Tooltip`, pinned to the cabinet.
 *
 * IT ANSWERS WHEN THE PLAYER HAS NOTHING, and that is the whole reason it has
 * three states instead of one. A machine that only spoke to somebody already
 * holding a level would be a piece of scenery for the entire first shop — the
 * player has to be told, standing in front of it, that a LEVEL is what this
 * thing eats, or the connection between killing zombies in the woods and the
 * lever in the glade is never made.
 *
 * The count rides the `end` slot for the same reason a price does on a table:
 * it is a number, not part of the sentence, and it keeps the card to one line
 * whatever the copy says.
 */

import type { HudMachinePrompt } from '../../game/hud-store';
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

  if (prompt.mode === 'busy') {
    return (
      <Tooltip anchor="machine">
        <span className="text-ink-muted">A máquina está rodando</span>
      </Tooltip>
    );
  }

  if (prompt.mode === 'empty') {
    return (
      <Tooltip anchor="machine" end={banked}>
        {/* States the CURRENCY rather than the refusal. "Sem giros" would say
            what is missing; this says where it comes from, which is the one
            thing a player standing here does not know yet. */}
        <span className="text-ink-muted">Suba de nível para girar</span>
      </Tooltip>
    );
  }

  return (
    <Tooltip anchor="machine" end={banked}>
      <TooltipKey>E</TooltipKey> puxar a alavanca
    </Tooltip>
  );
}
