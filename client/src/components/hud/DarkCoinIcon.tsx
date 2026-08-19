/**
 * DARK GOLD badge — the player's own ANOMALY SHARD, frame 0 of the sphere
 * that turns in the woods (`server/tools/make_coin.py`, which paints both).
 *
 * It used to be a struck disc sharing `CoinIcon`'s silhouette, on the argument
 * that at 8px the METAL is the whole message. That stopped being true when the
 * pickup stopped being metal: one of these is money and the other is a piece
 * of the thing the night is spent feeding, and a ball against a disc says so
 * before the colour does. Gold is the GROUP's and rides on catalog value,
 * platform quotas and shop prices; this one is personal, and the only one
 * anybody walks over.
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
