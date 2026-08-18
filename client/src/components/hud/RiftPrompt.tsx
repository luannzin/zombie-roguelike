/**
 * Interact prompt on an extraction pad. One use of `Tooltip`.
 *
 * FIVE THINGS THE BUTTON CAN BE SAYING, and they are not interchangeable: wake
 * the platform, wait (another pad is already running), load it, keep loading
 * past the quota, or SEND it. The last one is the one that matters most and
 * the one a player will not guess — the quota is paid, the console has gone
 * gold, and pressing now flies the platform out rather than adding to it.
 * Everything loaded past the quota before that press comes back as one
 * condensed core once the skid is gone.
 *
 * Mounted only while in reach.
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
        Aperte <TooltipKey>E</TooltipKey> para ligar a plataforma
      </Tooltip>
    );
  }

  if (prompt.mode === 'busy') {
    return (
      <Tooltip anchor="rift">
        <span className="text-hp-low">Outra plataforma está ligada</span>
      </Tooltip>
    );
  }

  const count = <QuestCount have={prompt.have} need={prompt.need} gold />;

  if (prompt.mode === 'close') {
    return (
      <Tooltip anchor="rift" end={count}>
        Aperte <TooltipKey>E</TooltipKey> para lançar a plataforma
      </Tooltip>
    );
  }

  // Past the quota with a bag that still has something in it. The press is the
  // same key doing the same verb — the platform is just no longer counting —
  // so the line says what it BUYS rather than repeating the instruction. The
  // level is the number of drones that will be carrying it out.
  if (prompt.mode === 'over') {
    return (
      <Tooltip anchor="rift" end={count}>
        Aperte <TooltipKey>E</TooltipKey> para sobrecarregar a plataforma
        <span className="text-ink-muted"> · nível {prompt.level}</span>
      </Tooltip>
    );
  }

  if (prompt.empty) {
    return (
      <Tooltip anchor="rift" end={count}>
        <span className="text-hp-low">Inventário vazio</span>
      </Tooltip>
    );
  }

  return (
    <Tooltip anchor="rift" end={count}>
      Aperte <TooltipKey>E</TooltipKey> para carregar a plataforma
    </Tooltip>
  );
}
