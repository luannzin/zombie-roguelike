/**
 * The menu's button, in the HUD's language: square corners, a 1px border over
 * an inset ring, scanlines that light up on hover.
 *
 * Written here rather than restyling the coss `Button` because every one of
 * that component's visual decisions — radius, shadow, ring, sans face — is the
 * opposite of this one's, and overriding them all at the call site costs more
 * than the twenty lines below.
 */

import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface MenuButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'default' | 'quiet';
  children: ReactNode;
}

export function MenuButton({
  variant = 'default',
  className,
  children,
  ...props
}: MenuButtonProps) {
  return (
    <button
      type="button"
      className={cn(
        'pixel-text group relative inline-flex w-full cursor-pointer items-center justify-center',
        'border px-4 py-2.5 text-[11px] leading-[17px] tracking-[0.14em] uppercase',
        'transition-[background-color,color,border-color,translate] duration-100',
        'focus-visible:ring-1 focus-visible:ring-ink-accent focus-visible:outline-none',
        'active:translate-y-px disabled:cursor-not-allowed disabled:opacity-45 disabled:active:translate-y-0',
        variant === 'primary' &&
          'border-ink-accent bg-ink-accent text-surface not-disabled:hover:brightness-115',
        variant === 'default' &&
          'crt-scanlines border-panel-border bg-panel text-ink shadow-[0_0_0_1px_var(--panel-inset)] not-disabled:hover:border-ink-accent not-disabled:hover:text-ink-accent',
        variant === 'quiet' &&
          'border-transparent text-ink-muted not-disabled:hover:text-ink',
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}
