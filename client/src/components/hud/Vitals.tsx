/** Bottom-right player panel: name, K/D, health, respawn state. */

import type { HudVitals } from '../../game/hud-store';
import { Panel } from '../ui/Panel';
import { ProgressBar } from './ProgressBar';

export interface VitalsProps {
  vitals: HudVitals | null;
}

export function Vitals({ vitals }: VitalsProps) {
  if (!vitals) return null;

  return (
    <Panel className="w-40 px-2.5 pt-2 pb-2.5">
      <div
        className="mb-1.5 truncate text-xs leading-tight font-semibold tracking-[0.02em]"
        style={{ color: vitals.color }}
      >
        {vitals.name}
      </div>

      <div className="mb-2 flex items-baseline justify-between gap-2 text-[11px] leading-tight">
        <span className="text-ink-muted tracking-[0.06em]">K/D</span>
        <span className="text-ink tabular-nums">
          {vitals.kills} / {vitals.deaths}
        </span>
      </div>

      <ProgressBar current={vitals.hp} max={vitals.maxHp} label="HP" tone="hp" />

      {!vitals.alive && (
        <div className="text-hp-low mt-1.5 text-[10px] tracking-[0.04em]">respawning…</div>
      )}
    </Panel>
  );
}
