/**
 * Ready prompt at the bonfire. One use of `Tooltip`. Mounted only while E
 * will answer, so the enter animation is the approach, not a 5 Hz flicker.
 */

import { Tooltip, TooltipKey } from './Tooltip';

export interface InteractPromptProps {
  prompt: 'ready' | null;
}

export function InteractPrompt({ prompt }: InteractPromptProps) {
  if (!prompt) return null;

  return (
    <Tooltip anchor="ready">
      Aperte <TooltipKey>E</TooltipKey> para ficar pronto
    </Tooltip>
  );
}
