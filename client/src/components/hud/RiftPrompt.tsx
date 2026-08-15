/**
 * Activation prompt on the extraction console. One use of `Tooltip`.
 *
 * Mounted only while the rift is DORMANT and in reach, so it disappears on the
 * frame the console is pressed — the structure answering is the confirmation,
 * and a prompt still hanging over a button that has already been thrown reads
 * as the press not having registered.
 */

import { Tooltip, TooltipKey } from './Tooltip';

export interface RiftPromptProps {
  prompt: boolean;
}

export function RiftPrompt({ prompt }: RiftPromptProps) {
  if (!prompt) return null;

  return (
    <Tooltip anchor="rift">
      Aperte <TooltipKey>E</TooltipKey> para abrir a fenda
    </Tooltip>
  );
}
