/**
 * The boss's name and his health, across the top of the screen.
 *
 * The only enemy in this game the HUD is ever told about by name. Everything
 * else is a body in a world you look at; a plate with a name on it is the
 * game saying THIS one is the subject, and the bar under it is the only
 * progress bar in the run that is about somebody else.
 *
 * IT IS ONE BAR AND IT HAS NO NUMBER ON IT. `ProgressBar` shows "62 / 100"
 * because the player's own health is a resource they budget with. His is not
 * a resource, it is a distance — the question the bar answers is "am I
 * getting anywhere", and 1840 / 2460 answers it worse than a line does.
 *
 * WHAT MAKES IT FEEL LIKE DAMAGE. Two fills, not one:
 *
 *   the LEAD    tracks his health instantly. This is the truth.
 *   the CHASE   a paler bar that lags a quarter of a second behind it, so
 *               every hit leaves a bright wound on the bar that closes up
 *               after it. It is the same trick a hit flash on the sprite
 *               plays, and it exists for the same reason: a body with 2460
 *               health moves the bar about a pixel a shot, and a pixel is not
 *               feedback. The gap between the two fills is what a player
 *               actually reads as "that landed".
 *
 * The whole thing is CSS: the chase is a transition with a longer duration on
 * the same width. No timers, no rAF, nothing this component has to own — and
 * it degrades to an honest bar under `prefers-reduced-motion`.
 *
 * IT SURVIVES HIS DEATH. `slain` holds the panel up while the collapse plays
 * — the payoff of a two-minute fight is watching the bar reach zero, and a
 * panel that unmounts when hp hits 0 takes that away on the exact frame it is
 * worth something. It leaves on its own, afterwards.
 */

import { useEffect, useState } from 'react';
import type { HudBoss } from '../../game/hud-store';
import { cn } from '@/lib/utils';

/** How long the empty bar stays up after he goes down, in ms. */
const SLAIN_HOLD = 2600;
/** The cinematic is over and the bar slides in. Seconds, off `engaged`. */
const ENTER_AFTER = 0;

export interface BossBarProps {
  boss: HudBoss | null;
  className?: string;
}

export function BossBar({ boss, className }: BossBarProps) {
  // Held so the panel outlives the row by the length of the collapse.
  const [held, setHeld] = useState<HudBoss | null>(null);

  useEffect(() => {
    if (boss) {
      setHeld(boss);
      return;
    }
    if (!held) return;
    const timer = window.setTimeout(() => setHeld(null), SLAIN_HOLD);
    return () => window.clearTimeout(timer);
  }, [boss, held]);

  const row = boss ?? held;
  if (!row) return null;

  // NOT SHOWN DURING THE ARRIVAL. `engaged` is negative until the cinematic
  // ends, and a health bar over a boss who is still in the air is the game
  // spoiling its own entrance — the shadow is supposed to be the reveal.
  const shown = row.engaged >= ENTER_AFTER;
  const fraction = Math.max(0, Math.min(1, row.fraction));

  return (
    <div
      className={cn(
        'pointer-events-none absolute inset-x-0 top-6 z-20 flex flex-col items-center gap-1.5',
        'transition-[opacity,transform] duration-500 ease-out motion-reduce:transition-none',
        shown ? 'translate-y-0 opacity-100' : '-translate-y-3 opacity-0',
        className,
      )}
      aria-hidden={!shown}
    >
      <div className="flex flex-col items-center gap-0.5">
        <div
          className={cn(
            'text-[15px] leading-[15px] tracking-[0.34em] uppercase',
            'text-ink drop-shadow-[0_1px_0_rgba(0,0,0,0.9)]',
            // The enrage is announced by the TYPE as well as by the bar,
            // because a colour change alone is a change somebody looking at
            // the boss instead of the HUD will miss entirely.
            row.enraged && 'text-hp-low',
          )}
        >
          {row.name}
        </div>
        <div className="text-ink-muted text-[10px] leading-[10px] tracking-[0.22em] uppercase">
          {row.enraged ? 'enfurecido' : row.title}
        </div>
      </div>

      <div
        className={cn(
          'border-track-border bg-track relative h-[9px] w-[min(56vw,560px)] overflow-hidden border',
          'shadow-[inset_0_0_0_1px_var(--surface),0_1px_0_rgba(0,0,0,0.8)]',
        )}
      >
        {/* THE CHASE. Behind, paler, and slower — the wound left by a hit. */}
        <div
          className={cn(
            'bg-hp-mid/45 absolute inset-y-0 left-0',
            'transition-[width] duration-[520ms] ease-out motion-reduce:transition-none',
          )}
          style={{ width: `${fraction * 100}%` }}
        />
        {/* THE LEAD. His actual health, and it moves the frame the hit lands. */}
        <div
          className={cn(
            'absolute inset-y-0 left-0 shadow-[inset_0_-1px_0_var(--meter-shade)]',
            'transition-[width,background-color] duration-[90ms] ease-linear',
            'motion-reduce:transition-none',
            row.enraged ? 'bg-hp-low' : 'bg-hp-high',
          )}
          style={{ width: `${fraction * 100}%` }}
        />
        {/* Half. The one landmark on a bar with no numbers on it, and it is
            where the fight changes — see `BOSS_ENRAGE_AT`. */}
        <div className="bg-track-border/80 absolute inset-y-0 left-1/2 w-px" />
      </div>
    </div>
  );
}
