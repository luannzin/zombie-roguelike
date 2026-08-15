/**
 * A 0-100 fader in the HUD's language: square track, hard fill, a block for a
 * thumb, and the number in the pixel face.
 *
 * Built on a native `<input type="range">` rather than on the coss `Slider`,
 * for the same reason `MenuButton` and `HudInput` are reimplemented — every
 * visual decision in that primitive (`rounded-full`, `bg-white`, a drop shadow,
 * a 20px circle) is the opposite of this one's, and overriding all of them at
 * the call site costs more than the component.
 *
 * A range input is also the one case where the platform IS the structural
 * primitive: drag, keyboard stepping, touch, and the full ARIA contract come
 * for free and correct, which is exactly the trade the components doc asks for
 * when it says real behaviour should be reused. The appearance is entirely
 * ours, through `.hud-range` in styles/index.css.
 *
 * The fill is painted with a CSS custom property rather than a second element,
 * so the track stays one box and there is nothing to keep in sync.
 */

import type { CSSProperties } from 'react';
import { cn } from '@/lib/utils';

export interface HudSliderProps {
  label: string;
  /** 0..100. */
  value: number;
  onChange: (value: number) => void;
  /** Optional second line under the label, for what the row actually covers. */
  hint?: string;
  className?: string;
}

export function HudSlider({ label, value, onChange, hint, className }: HudSliderProps) {
  const rounded = Math.round(value);

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <div className="flex items-baseline justify-between gap-4">
        <span className="pixel-text text-[13px] leading-[17px] tracking-[0.12em] text-ink uppercase">
          {label}
        </span>
        <span
          className={cn(
            'pixel-text text-[13px] leading-[17px] tabular-nums',
            // Zero is a state worth seeing at a glance, not just a number:
            // somebody who muted a group months ago should be able to find it.
            rounded === 0 ? 'text-ink-muted' : 'text-ink-accent',
          )}
        >
          {rounded}
        </span>
      </div>

      <input
        type="range"
        min={0}
        max={100}
        step={1}
        value={rounded}
        aria-label={label}
        onChange={(event) => onChange(Number(event.target.value))}
        className="hud-range"
        style={{ '--fill': `${rounded}%` } as CSSProperties}
      />

      {hint ? (
        <span className="pixel-text text-[11px] leading-[15px] text-ink-muted">{hint}</span>
      ) : null}
    </div>
  );
}
