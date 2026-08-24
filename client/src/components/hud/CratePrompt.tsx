/**
 * Use prompt on an interactive object. One use of `Tooltip`. Mounted only
 * while something is in reach, so the enter animation is the approach rather
 * than a 5 Hz flicker.
 *
 * The VERB comes from the object itself (`config.objects[kind].label`, via
 * `interaction.cratePromptInfo`) instead of being a constant here. That is the whole
 * point of the object vocabulary reaching the client as data: a barrel says
 * destruir, a chest says abrir, a car boot says vasculhar, and the HUD learns
 * a new one when `server/app/crates.py` grows a row.
 *
 * AND IT STATES THE PRICE BEFORE THE PRESS. One object in the game plants you
 * for real seconds (`open_time` — the vault), and the whole design of that is
 * that choosing WHEN to pay it is the interesting part. A player who only
 * finds out they are committed once they are standing still has been trapped
 * rather than asked, so the seconds are on the prompt, in the same line, and
 * nowhere else in the HUD needs to know.
 *
 * A COSTED OBJECT ASKS FOR A HOLD, AND THE PROMPT SAYS SO IN THE VERB. Every
 * other press in this game resolves on the frame it happens; this one runs
 * while the key is down and stops when it comes up (`Room.cancel_force`). The
 * sentence is the only place a player can learn that before trying it, so the
 * two prompts are different sentences rather than the same one with a number
 * on the end — `seconds` is what picks between them, so an object that grows
 * an `open_time` gets the right instruction without anybody editing this file.
 */

import { Tooltip, TooltipKey } from './Tooltip';
import type { HudCratePrompt } from '../../game/hud-store';

export interface CratePromptProps {
  /** The object under E, or null when nothing is in reach. */
  prompt: HudCratePrompt | null;
}

export function CratePrompt({ prompt }: CratePromptProps) {
  if (!prompt) return null;

  return (
    <Tooltip anchor="crate">
      {prompt.seconds > 0 ? (
        <>
          Mantenha <TooltipKey>E</TooltipKey> pressionado para {prompt.label}
          {/*
            Its own muted span rather than part of the sentence: the verb is
            what the player reads at a glance and the cost is what they read
            when they stop to think, and running the two together makes the
            fast read slower for every object that has no cost at all.
          */}
          <span className="text-ink-muted"> ({prompt.seconds.toFixed(1)}s parado)</span>
        </>
      ) : (
        <>
          Aperte <TooltipKey>E</TooltipKey> para {prompt.label}
        </>
      )}
    </Tooltip>
  );
}
