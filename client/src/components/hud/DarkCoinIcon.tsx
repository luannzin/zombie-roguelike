/**
 * DARK GOLD badge — the player's own purple coin, the face of the disc that
 * spins in the woods (`server/tools/make_coin.py`).
 *
 * Deliberately the same 8x8 silhouette as `CoinIcon`: at this size the METAL
 * is the whole message, and giving the two currencies different shapes would
 * make the panel look like it holds two unrelated icons instead of two kinds
 * of money. Gold is the GROUP's and rides on catalog value, platform quotas
 * and shop prices; this one is personal, and the only one anybody walks over.
 */

import { cn } from '@/lib/utils';

export interface DarkCoinIconProps {
  className?: string;
}

export function DarkCoinIcon({ className }: DarkCoinIconProps) {
  return (
    <img
      src="/hud/darkcoin.png"
      alt=""
      className={cn('pixelated size-2 shrink-0', className)}
    />
  );
}
