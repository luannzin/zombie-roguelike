/**
 * Interact prompt on an extraction pad. One use of `Tooltip`.
 *
 * Dormant: open the console. Open: feed the anomaly from the bag, with the
 * same have/need the quest card is showing. Mounted only while in reach.
 */

import { Tooltip, TooltipKey } from './Tooltip';
import type { HudRiftPrompt } from '../../game/hud-store';
import { QuestCount } from './QuestCount';

export interface RiftPromptProps {
  prompt: HudRiftPrompt | null;
}

export function RiftPrompt({ prompt }: RiftPromptProps) {
  if (!prompt) return null;

  if (prompt.mode === 'open') {
    return (
      <Tooltip anchor="rift">
        Aperte <TooltipKey>E</TooltipKey> para abrir a fenda
      </Tooltip>
    );
  }

  if (prompt.empty) {
    return (
      <Tooltip
        anchor="rift"
        end={
          <QuestCount have={prompt.have} need={prompt.need} gold />
        }
      >
        <span className="text-hp-low">Inventário vazio</span>
      </Tooltip>
    );
  }

  return (
    <Tooltip
      anchor="rift"
      end={
        <QuestCount have={prompt.have} need={prompt.need} gold />
      }
    >
      Aperte <TooltipKey>E</TooltipKey> para alimentar a fenda
    </Tooltip>
  );
}
