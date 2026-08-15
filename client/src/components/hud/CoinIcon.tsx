/**
 * HUD gold badge. Dedicated 8x8 asset — not a frame of the world coin sheet.
 */

import { cn } from '@/lib/utils';

export interface CoinIconProps {
  className?: string;
}

export function CoinIcon({ className }: CoinIconProps) {
  return (
    <img
      src="/hud/coin.png"
      alt=""
      className={cn('pixelated size-2 shrink-0', className)}
    />
  );
}
