/**
 * Interact prompt on an extraction pad. One use of `Tooltip`.
 *
 * FIVE THINGS THE BUTTON CAN BE SAYING, and they are not interchangeable: wake
 * the platform, wait (another pad is already running), load it, keep loading
 * past the quota, or CALL THE PICKUP.
 *
 * THAT LAST ONE IS THE MOST EXPENSIVE PRESS IN THE GAME and the line has to
 * say so before it happens, not after. Everything up to it is quiet and
 * reversible; that one turns four green lamps red, starts a siren in a black
 * forest, and puts every creature on the map on hunt for thirteen seconds
 * while the party stands next to the pad waiting for aircraft. So it is the
 * one prompt in the game drawn in the danger tone, and it names the
 * consequence rather than the verb.
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
        Aperte <TooltipKey>E</TooltipKey> para chamar a extração
        <span className="text-hp-low"> · o barulho atrai tudo</span>
      </Tooltip>
    );
  }

  // Past the quota with a bag that still has something in it. The press is the
  // same key doing the same verb — the platform is just no longer counting —
  // so the line says what it BUYS rather than repeating the instruction. The
  // overshoot itself is on the count beside it.
  if (prompt.mode === 'over') {
    return (
      <Tooltip anchor="rift" end={count}>
        Aperte <TooltipKey>E</TooltipKey> para sobrecarregar a plataforma
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
