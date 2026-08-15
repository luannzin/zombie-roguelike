/**
 * One collectable, as a CSS window onto the loot atlas.
 *
 * Frame index comes from the catalog. The sheet is a single row of 16x16
 * frames; we zoom by an integer so the pixels stay on the HUD grid.
 */

import { cn } from '@/lib/utils';

const FRAME = 16;

export interface LootIconProps {
  frame: number;
  frames: number;
  zoom?: number;
  className?: string;
}

export function LootIcon({ frame, frames, zoom = 2, className }: LootIconProps) {
  const size = FRAME * zoom;
  const safeFrames = Math.max(1, frames);
  const safeFrame = ((frame % safeFrames) + safeFrames) % safeFrames;

  return (
    <div
      aria-hidden="true"
      className={cn('pixelated shrink-0', className)}
      style={{
        width: size,
        height: size,
        backgroundImage: 'url(/loot/sheet.png)',
        backgroundRepeat: 'no-repeat',
        backgroundSize: `${safeFrames * size}px ${size}px`,
        backgroundPosition: `${-safeFrame * size}px 0`,
      }}
    />
  );
}
