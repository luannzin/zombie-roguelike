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
  // Always offered, because the knife always answers — `zone.hostile` gates
  // the gun, not the swing, so even the campfire has something on the
  // trigger. Listing it only in the forest would teach the player that the
  // button is dead here, which is the mistake this component exists to avoid.
  parts.push('clique para atacar');
  parts.push('1-2 arma', '3 faca');
  if (zone?.lantern !== false) parts.push('F lanterna');
  if (zone?.kind === 'camp') parts.push('E pronto');
  else if (zone?.hostile) parts.push('E coletar');
  parts.push('TAB mochila');
  // Always listed, unlike the rest: mute is the one control that works
  // everywhere, and a player who wants the sound off needs to find it without
  // reading a settings screen that does not exist yet.
  parts.push('M som');

  return <div className="text-ink-muted text-[11px] leading-[11px]">{parts.join(' · ')}</div>;
}
