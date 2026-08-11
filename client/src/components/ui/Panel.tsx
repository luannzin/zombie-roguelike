/**
 * The HUD's shared chrome: 1px border over an inset ring. Every floating panel
 * (minimap, vitals, and later the room list and menus) uses this so they read
 * as one system.
 */

import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

export interface PanelProps {
  className?: string;
  children: ReactNode;
}

export function Panel({ className, children }: PanelProps) {
  return (
    <div
      className={cn(
        'border-panel-border bg-panel border shadow-[0_0_0_1px_var(--panel-inset)]',
        className,
      )}
    >
      {children}
    </div>
  );
}
