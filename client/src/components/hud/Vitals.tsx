/**
 * Bottom-right player panel: name, level, K/D, dark gold, health, respawn.
 *
 * The GOLD row is the PLAYER's, and it is the only currency readout that is up
 * the whole run — it wears the purple badge because the number it counts is
 * coins this person walked over, one at a time, out there. The group's balance
 * is a different metal and lives in the shop (`Balance`), for the reason
 * written there: a party purse in the corner of every expedition would be
 * telling the player about money nothing on this map can spend.
 */

import type { HudVitals } from '../../game/hud-store';
import { DarkCoinIcon } from './DarkCoinIcon';
import { Panel } from './Panel';
import { ProgressBar } from './ProgressBar';

export interface VitalsProps {
  vitals: HudVitals | null;
}

export function Vitals({ vitals }: VitalsProps) {
  if (!vitals) return null;

  return (
    <Panel className="w-40 px-2.5 pt-2 pb-2.5">
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <span
          className="truncate text-[11px] leading-[11px] tracking-[0.02em]"
          style={{ color: vitals.color }}
        >
          {vitals.name}
        </span>
        <span className="text-ink-muted shrink-0 text-[11px] leading-[11px] tabular-nums">
          lv {vitals.level}
        </span>
      </div>

      <div className="mb-2 flex items-baseline justify-between gap-2 text-[11px] leading-[11px]">
        <span className="text-ink-muted tracking-[0.06em]">K/D</span>
        <span className="text-ink tabular-nums">
          {vitals.kills} / {vitals.deaths}
        </span>
      </div>

      <div className="mb-2 flex items-baseline justify-between gap-2 text-[11px] leading-[11px]">
        <span className="text-ink-muted tracking-[0.06em]">GOLD</span>
        <span className="text-ink-dark-gold flex items-center gap-1 tabular-nums">
          <DarkCoinIcon />
          {vitals.gold}
        </span>
      </div>

      <ProgressBar current={vitals.hp} max={vitals.maxHp} label="HP" tone="hp" />
      <ProgressBar
        className="mt-2"
        current={vitals.xpInLevel}
        max={vitals.xpToLevel}
        label="XP"
        tone="xp"
      />

      {!vitals.alive && (
        <div className="text-hp-low mt-1.5 text-[11px] leading-[11px] tracking-[0.04em]">
          respawning…
        </div>
      )}
    </Panel>
  );
}
