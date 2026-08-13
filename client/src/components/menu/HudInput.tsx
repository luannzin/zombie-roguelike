/**
 * A labelled text field in HUD chrome.
 *
 * The caret and selection are the browser's; everything else is the panel
 * treatment the rest of the interface uses. Same reasoning as `MenuButton`:
 * the coss `Input` is a rounded, shadowed, sans-serif control and nothing of
 * it would survive being made to match.
 */

import type { InputHTMLAttributes, ReactNode, Ref } from 'react';
import { useId } from 'react';
import { cn } from '@/lib/utils';

export interface HudInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  /** Shown under the field, in muted ink — or in the danger tone when `invalid`. */
  hint?: ReactNode;
  invalid?: boolean;
  ref?: Ref<HTMLInputElement>;
}

export function HudInput({ label, hint, invalid, className, ref, ...props }: HudInputProps) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={id}
        className="pixel-text text-[11px] leading-[17px] tracking-[0.18em] text-ink-muted uppercase"
      >
        {label}
      </label>
      <input
        id={id}
        ref={ref}
        className={cn(
          'pixel-text border bg-track px-3 py-2.5 text-[11px] leading-[17px] tracking-[0.1em] text-ink',
          'placeholder:text-ink-muted/60 focus-visible:outline-none',
          'shadow-[0_0_0_1px_var(--panel-inset)]',
          invalid
            ? 'border-hp-low focus-visible:border-hp-low'
            : 'border-track-border focus-visible:border-ink-accent',
          className,
        )}
        {...props}
      />
      {hint ? (
        <p
          className={cn(
            'pixel-text text-[11px] leading-[17px]',
            invalid ? 'text-hp-low' : 'text-ink-muted',
          )}
        >
          {hint}
        </p>
      ) : null}
    </div>
  );
}
