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
 */

import { Tooltip, TooltipKey } from './Tooltip';

export interface CratePromptProps {
  /** The verb, or null when nothing is in reach. */
  prompt: string | null;
}

export function CratePrompt({ prompt }: CratePromptProps) {
  if (!prompt) return null;

  return (
    <Tooltip anchor="crate">
      Aperte <TooltipKey>E</TooltipKey> para {prompt}
    </Tooltip>
  );
}
