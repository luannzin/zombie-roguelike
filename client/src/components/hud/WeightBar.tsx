/**
 * How much of the bag is filled. White when light, red when heavy.
 * The fill caps at the track; the numbers may go past max — overweight
 * is allowed, and the colour is how you feel it.
 */

import { clamp01 } from '../../lib/math';
import type { HudInventory } from '../../game/hud-store';

export interface WeightBarProps {
  inventory: HudInventory;
}

export function WeightBar({ inventory }: WeightBarProps) {
  const max = Math.max(0, inventory.maxWeight);
  const ratio = max > 0 ? inventory.weight / max : 0;
  const fill = clamp01(ratio);
  const heat = clamp01(ratio);
  const ink = Math.round((1 - heat) * 100);
  const danger = Math.round(heat * 100);
  const color = `color-mix(in srgb, var(--ink) ${ink}%, var(--hp-low) ${danger}%)`;

  return (
    <div className="mt-1.5" aria-label="peso">
      <div className="mb-1 flex items-baseline justify-between gap-2 text-[11px] leading-[11px] tracking-[0.05em]">
        <span className="text-ink-muted">PESO</span>
        <span className="tabular-nums" style={{ color }}>
          {formatWeight(inventory.weight)} / {formatWeight(max)}
        </span>
      </div>
      <div className="border-track-border bg-track relative h-2 overflow-hidden border shadow-[inset_0_0_0_1px_var(--surface)]">
        <div
          className="h-full shadow-[inset_0_-1px_0_var(--meter-shade)] transition-[width] duration-[120ms] ease-linear motion-reduce:transition-none"
          style={{ width: `${fill * 100}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

function formatWeight(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}
