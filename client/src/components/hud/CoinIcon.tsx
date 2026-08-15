/**
 * Static coin from the world sheet. Idle down-frame, no spin — HUD chrome,
 * not a pickup.
 */

import { cn } from '@/lib/utils';

const FRAME = 16;
const COLS = 3;
const ROWS = 4;

export interface CoinIconProps {
  zoom?: number;
  className?: string;
}

export function CoinIcon({ zoom = 1, className }: CoinIconProps) {
  const size = FRAME * zoom;

  return (
    <div
      aria-hidden="true"
      className={cn('pixelated shrink-0', className)}
      style={{
        width: size,
        height: size,
        backgroundImage: 'url(/coin/sheet.png)',
        backgroundRepeat: 'no-repeat',
        backgroundSize: `${COLS * size}px ${ROWS * size}px`,
        backgroundPosition: '0 0',
      }}
    />
  );
}
