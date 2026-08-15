/**
 * The menu's button, in the HUD's language: square corners, a 1px border over
 * an inset ring, scanlines that light up on hover.
 *
 * Written here rather than restyling the coss `Button` because every one of
 * that component's visual decisions — radius, shadow, ring, sans face — is the
 * opposite of this one's, and overriding them all at the call site costs more
 * than the twenty lines below.
 */

import type { ButtonHTMLAttributes, MouseEvent, ReactNode } from 'react';
import { playSfx } from '@/audio';
import { cn } from '@/lib/utils';

export interface MenuButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'default' | 'quiet';
  children: ReactNode;
}

export function MenuButton({
  variant = 'default',
  className,
  children,
  onClick,
  ...props
}: MenuButtonProps) {
  // Sound belongs to the component, not to the twelve call sites: every menu
  // button in the game goes through here, so this is the one place that has to
  // agree about what a button sounds like. A `quiet` button is the way back
  // out of somewhere and takes the descending click.
  //
  // CLICK ONLY. Hover used to tick and it was wrong: the pointer crosses
  // buttons on the way to the one it wants, so the menu chattered at moves the
  // player had not decided on yet. A sound should mark a decision.
  const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
    playSfx(variant === 'quiet' ? 'ui-back' : 'ui-click');
    onClick?.(event);
  };

  return (
    <button
      type="button"
      onClick={handleClick}
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
