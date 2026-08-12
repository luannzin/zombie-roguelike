/**
 * The lantern's charge, as four cells of pixel art.
 *
 * The gauge is the sprite from `server/tools/make_hud_icons.py` drawn four
 * times, and a cell drains from the TOP DOWN by stacking two copies of it: a
 * dead grey one underneath, and a full-colour one on top clipped to whatever
 * charge is left. So a cell does not switch between "full" and "empty" art —
 * the colour recedes down the battery and the drained part of the same pixels
 * stays visible, greyed out, which is what makes four cells read as one
 * continuous meter instead of four lights.
 *
 * The clip is quantized to the sprite's own pixel rows. Cutting a 10x18 sprite
 * at an arbitrary fraction of its blown-up height would leave a half-lit row of
 * screen pixels, and one soft edge is all it takes to break a pixel HUD.
 *
 * Everything here is driven by `charge`, not by a per-frame signal: the lamp's
 * blinking lives in the light itself (see `game/lantern.ts`), and the HUD only
 * republishes at 5 Hz. The one exception is the failing state, which animates
 * in CSS.
 */

import { clamp01 } from '@/lib/math';
import { cn } from '@/lib/utils';
import { BATTERY_CELLS, type LanternReading } from '../../game/lantern';
import { Panel } from './Panel';

/** Frame size of `/hud/battery.png`. Must match make_hud_icons.py. */
const SPRITE_WIDTH = 10;
const SPRITE_HEIGHT = 18;
/** Integer zoom only — a pixel sprite at a fractional scale shimmers. */
const ZOOM = 2;

export interface BatteryGaugeProps {
  lantern: LanternReading | null;
}

export function BatteryGauge({ lantern }: BatteryGaugeProps) {
  if (!lantern) return null;

  const dead = lantern.cells === 0;
  const tone = dead
    ? 'text-hp-low'
    : lantern.failing
      ? 'text-hp-mid'
      : lantern.on
        ? 'text-ink-accent'
        : 'text-ink-muted';

  return (
    <Panel className={cn('w-40 px-2.5 py-2', lantern.failing && 'animate-lantern-fail')}>
      <div className="mb-1.5 flex items-baseline justify-between gap-2 text-[11px] leading-[11px]">
        <span className="text-ink-muted tracking-[0.06em]">LANTERN</span>
        <span className={cn('tabular-nums', tone)}>
          {dead ? 'DEAD' : lantern.on ? 'ON' : 'OFF'}
        </span>
      </div>

      <div className="flex gap-1.5">
        {Array.from({ length: BATTERY_CELLS }, (_, index) => (
          <Cell key={index} fill={clamp01(lantern.charge * BATTERY_CELLS - index)} />
        ))}
      </div>

      <div className="text-ink-muted mt-1.5 text-[11px] leading-[11px] tracking-[0.04em]">
        [F] {lantern.on ? 'off' : 'on'}
      </div>
    </Panel>
  );
}

/** One cell: a grey battery with a colour one clipped over the charge left. */
function Cell({ fill }: { fill: number }) {
  // Snap to whole sprite rows, then express the cut as a percentage of the
  // element so the clip survives any ZOOM.
  const rows = Math.round(fill * SPRITE_HEIGHT);
  const drained = ((SPRITE_HEIGHT - rows) / SPRITE_HEIGHT) * 100;

  return (
    <div
      className="relative shrink-0"
      style={{ width: SPRITE_WIDTH * ZOOM, height: SPRITE_HEIGHT * ZOOM }}
    >
      <img
        src="/hud/battery.png"
        alt=""
        className="pixelated absolute inset-0 h-full w-full grayscale brightness-50"
      />
      {rows > 0 && (
        <img
          src="/hud/battery.png"
          alt=""
          className="pixelated absolute inset-0 h-full w-full"
          style={{ clipPath: `inset(${drained}% 0 0 0)` }}
        />
      )}
    </div>
  );
}
