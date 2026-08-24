/**
 * One ultimate's mark, as a CSS window onto `/ultimates/sheet.png`.
 *
 * The third of these — `LootIcon` and `SkillIcon` are the others — and it is
 * deliberately a third rather than a generalisation of either. The three
 * sheets have different cell sizes, different roots and completely different
 * reasons to change; folding them into one component with a `sheet` prop would
 * mean every future change to any of them had to be safe for all three, which
 * is the tax that turns three small correct files into one careful one.
 *
 * THE STATE IS A FILTER, NOT A FRAME. A locked ultimate is this same image
 * with the colour taken out of it and a ready one is this same image burning;
 * neither is a different picture. That is what lets a player learn one mark
 * per weapon instead of three per weapon — and it is why the generator draws
 * every icon at full strength and knows nothing about locks.
 */

import { cn } from '@/lib/utils';

/** The generator's cell. Must match `CELL` in `server/tools/make_ultimates.py`. */
const CELL = 20;
/** How many marks the sheet holds. Must match `ULTIMATES` in `ultimates.py`. */
const FRAMES = 4;

export type UltimateIconState = 'locked' | 'charging' | 'ready';

export interface UltimateIconProps {
  frame: number;
  state: UltimateIconState;
  zoom?: number;
  className?: string;
}

export function UltimateIcon({ frame, state, zoom = 2, className }: UltimateIconProps) {
  const size = CELL * zoom;
  const safe = ((frame % FRAMES) + FRAMES) % FRAMES;

  return (
    <div
      aria-hidden="true"
      className={cn(
        'pixelated shrink-0 transition-[filter,opacity] duration-200 motion-reduce:transition-none',
        className,
        // LOCKED IS GREY AND DIM, and both halves matter. Grey alone still
        // reads as "a thing"; dim alone still reads as coloured. Together they
        // read as an object behind glass, which is exactly the sentence — the
        // ultimate exists, it is yours, and you cannot have it yet.
        state === 'locked' && 'opacity-45 grayscale',
        // CHARGING is the mark as drawn. No treatment at all, because this is
        // the state it will be in for most of a night and anything applied
        // here would become the baseline the other two are read against.
        // READY BURNS. A drop shadow in the mark's own light rather than a
        // brightness lift: brightness flattens a five-step ramp toward white
        // and what comes back is a paler icon, where a glow leaves the pixels
        // alone and puts the light AROUND them.
        state === 'ready' && 'drop-shadow-[0_0_6px_var(--ult-flash)]',
      )}
      style={{
        width: size,
        height: size,
        backgroundImage: 'url(/ultimates/sheet.png)',
        backgroundRepeat: 'no-repeat',
        backgroundSize: `${FRAMES * size}px ${size}px`,
        backgroundPosition: `${-safe * size}px 0`,
      }}
    />
  );
}
