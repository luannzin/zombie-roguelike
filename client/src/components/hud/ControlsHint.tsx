/**
 * Bottom-left controls reminder.
 *
 * It lists what works HERE. A safe zone has no trigger and no lamp, and a hint
 * that offers both teaches the player two controls that will not answer — which
 * is worse than not mentioning them, because the first thing they will do is
 * try one.
 */

import type { ZoneInfo } from '../../net/protocol';

export interface ControlsHintProps {
  zone: ZoneInfo | null;
}

export function ControlsHint({ zone }: ControlsHintProps) {
  const parts = ['WASD mover', 'mouse mirar'];
  if (zone?.hostile !== false) parts.push('clique para atirar');
  if (zone?.lantern !== false) parts.push('F lanterna');
  if (zone?.kind === 'camp') parts.push('E pronto');
  else if (zone?.hostile) parts.push('E coletar');
  parts.push('TAB mochila');

  return <div className="text-ink-muted text-[11px] leading-[11px]">{parts.join(' · ')}</div>;
}
