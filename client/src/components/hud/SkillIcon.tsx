/**
 * One skill, as a CSS window onto the skill atlas.
 *
 * The twin of `LootIcon` and deliberately not a generalisation of it: the two
 * sheets have different frame counts, different roots and different reasons to
 * change, and folding them into one component with a `sheet` prop would mean
 * every future change to either had to be safe for both.
 */

import { cn } from '@/lib/utils';

const FRAME = 16;

export interface SkillIconProps {
  frame: number;
  frames: number;
  zoom?: number;
  className?: string;
}

export function SkillIcon({ frame, frames, zoom = 2, className }: SkillIconProps) {
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
        backgroundImage: 'url(/skills/sheet.png)',
        backgroundRepeat: 'no-repeat',
        backgroundSize: `${safeFrames * size}px ${size}px`,
        backgroundPosition: `${-safeFrame * size}px 0`,
      }}
    />
  );
}
