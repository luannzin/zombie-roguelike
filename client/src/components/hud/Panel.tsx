/**
 * The HUD's shared chrome: 1px border over an inset ring, scanlined. Every
 * floating panel (minimap, vitals, and later the room list and menus) uses this
 * so they read as one system.
 *
 * The scanlines are the panel's half of the CRT the whole HUD is warped onto
 * (see `HudScreen`). They are painted here rather than over the full screen on
 * purpose: the arena underneath is a forest at night, not a monitor, and lines
 * across it would flatten the one thing the lighting works hardest to give
 * depth to.
 */

import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface PanelProps {
  className?: string;
  children: ReactNode;
}

export function Panel({ className, children }: PanelProps) {
  return (
    <div
      className={cn(
        'border-panel-border bg-panel crt-scanlines border shadow-[0_0_0_1px_var(--panel-inset)]',
        className,
      )}
    >
      {children}
    </div>
  );
}
