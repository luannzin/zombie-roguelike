/**
 * Shared HUD meter (HP now, XP later).
 *
 * Colours are Tailwind utilities backed by the tokens in `styles/index.css` —
 * the same custom properties the canvas health bars read. Only the fill width
 * is an inline style, because it is data, not theme.
 */

import { clamp01 } from '../../lib/math';
import { cn } from '@/lib/utils';
import { hpLevel } from '../../theme/palette';

export type ProgressTone = 'hp' | 'xp' | 'neutral';

export interface ProgressBarProps {
  current: number;
  max: number;
  /** Left-side caption, e.g. "HP" / "XP". */
  label?: string;
  tone?: ProgressTone;
  className?: string;
}

/** Full class strings so Tailwind's scanner can see every variant. */
const HP_FILL = {
  high: 'bg-hp-high',
  mid: 'bg-hp-mid',
  low: 'bg-hp-low',
} as const;

function fillClass(tone: ProgressTone, ratio: number): string {
  if (tone === 'hp') return HP_FILL[hpLevel(ratio)];
  return tone === 'xp' ? 'bg-xp' : 'bg-neutral';
}

export function ProgressBar({ current, max, label, tone = 'neutral', className }: ProgressBarProps) {
  const safeMax = Math.max(0, max);
  const clamped = Math.min(safeMax, Math.max(0, current));
  const ratio = safeMax > 0 ? clamp01(clamped / safeMax) : 0;

  return (
    <div className={className} aria-label={label}>
      {label && (
        <div className="mb-1 flex items-baseline justify-between gap-2 text-[10px] leading-tight tracking-[0.05em]">
          <span className="text-ink-muted">{label}</span>
          <span className="text-ink tabular-nums">
            {Math.round(clamped)} / {Math.round(safeMax)}
          </span>
        </div>
      )}
      <div className="border-track-border bg-track relative h-2 overflow-hidden border shadow-[inset_0_0_0_1px_var(--surface)]">
        <div
          className={cn(
            'h-full shadow-[inset_0_-1px_0_var(--meter-shade)]',
            'transition-[width,background-color] duration-[120ms] ease-linear',
            'motion-reduce:transition-none',
            fillClass(tone, ratio),
          )}
          style={{ width: `${ratio * 100}%` }}
        />
      </div>
    </div>
  );
}
