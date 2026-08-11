/**
 * Minimap host. The canvas element stays mounted for the whole session so the
 * `Game` reference stays valid; only its visibility follows arena state.
 *
 * Sizing is done imperatively by `render/minimap.ts` (it fits the canvas to the
 * map's aspect ratio), so no width/height is set here.
 */

import type { RefObject } from 'react';
import { cn } from '../../lib/cn';

export interface MinimapCanvasProps {
  ref: RefObject<HTMLCanvasElement | null>;
  visible: boolean;
}

export function MinimapCanvas({ ref, visible }: MinimapCanvasProps) {
  return (
    <canvas
      ref={ref}
      aria-label="minimap"
      width={160}
      height={160}
      className={cn(
        'pixelated border-panel-border bg-panel block border shadow-[0_0_0_1px_var(--panel-inset)]',
        !visible && 'invisible',
      )}
    />
  );
}
