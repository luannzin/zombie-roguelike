/**
 * Smash prompt on a crate. One use of `Tooltip`. Mounted only while a crate
 * is in reach, so the enter animation is the approach, not a 5 Hz flicker.
 */

import { Tooltip, TooltipKey } from './Tooltip';

export interface CratePromptProps {
  prompt: boolean;
}

export function CratePrompt({ prompt }: CratePromptProps) {
  if (!prompt) return null;

  return (
    <Tooltip anchor="crate">
      Aperte <TooltipKey>E</TooltipKey> para destruir
    </Tooltip>
  );
}
