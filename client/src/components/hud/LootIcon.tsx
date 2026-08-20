/**
 * One collectable, as a CSS window onto the loot atlas.
 *
 * Frame index comes from the catalog. The sheet is a single row of 16x16
 * frames; we zoom by an integer so the pixels stay on the HUD grid.
 *
 * THE WINDOW IS SIZED OFF THE FRAME, NEVER OFF THE SHEET, and that is the
 * whole reason this file has a comment. It used to scale the background to
 * `frames * size`, where `frames` was a count the HUD derived by walking the
 * catalog for its largest index — which is a different number from "how many
 * frames the PNG actually has", and the two agreed only by luck.
 *
 * `loot.py` hands any key the generator has no art for a frame ONE PAST THE
 * END, deliberately, so it draws nothing instead of somebody else's picture.
 * That sentinel then became the catalog's largest index, the count came out
 * one too high, every window shifted by `frame / count` of a frame, and the
 * icon that suffered most was the one on the LAST frame of the sheet — the
 * knife, which rendered 97% of the AWP sitting next to it. Buying a gun was
 * enough to make a player notice, because a bar with one item in it does not
 * invite a comparison and a bar with two does.
 *
 * Scaling the background's HEIGHT to one cell makes the width follow at the
 * same ratio, so a frame is exactly `size` wide no matter how long the sheet
 * is, and `backgroundPosition` lands on frame boundaries by construction.
 * An out-of-range index now scrolls past the end and draws nothing, which is
 * what the sentinel was always asking for.
 */

import { cn } from '@/lib/utils';

const FRAME = 16;

export interface LootIconProps {
  frame: number;
  zoom?: number;
  className?: string;
}

export function LootIcon({ frame, zoom = 2, className }: LootIconProps) {
  const size = FRAME * zoom;

  return (
    <div
      aria-hidden="true"
      className={cn('pixelated shrink-0', className)}
      style={{
        width: size,
        height: size,
        backgroundImage: 'url(/loot/sheet.png)',
        backgroundRepeat: 'no-repeat',
        // `auto` width: the sheet scales by height, so one 16px frame becomes
        // exactly `size` across whatever the sheet's length happens to be.
        backgroundSize: `auto ${size}px`,
        backgroundPosition: `${-Math.max(0, Math.trunc(frame)) * size}px 0`,
      }}
    />
  );
}
