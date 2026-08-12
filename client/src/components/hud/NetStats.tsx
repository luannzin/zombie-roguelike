/** Netcode telemetry line: entity counts, RTT, interpolation delay, FPS. */

import type { HudNetStats } from '../../game/hud-store';

export interface NetStatsProps {
  net: HudNetStats | null;
}

export function NetStats({ net }: NetStatsProps) {
  if (!net) return null;

  return (
    <div className="text-ink tabular-nums">
      {`players ${net.players} · zombies ${net.enemies} · rtt ${net.rttMs}ms · ` +
        `interp ${net.interpMs}ms · pending ${net.pending} · ${net.fps} fps`}
    </div>
  );
}
