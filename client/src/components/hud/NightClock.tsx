/**
 * The night's countdown. One figure, one meter, at the top of the glass.
 *
 * IT IS THE ONLY DEADLINE IN THE GAME. Before it, a night ended when the party
 * decided it had, so waiting cost nothing and clearing the whole forest slowly
 * was strictly the best play — a survival game in which patience dominates has
 * no tension in it however dangerous the monsters are. This is the element that
 * turns "one more crate" from free value into a question.
 *
 * TOP CENTRE, WHICH IS THE ONE PLACE NOTHING ELSE LIVES. The corners are all
 * spoken for — status and net left, minimap and quests right, belt and bag
 * along the bottom — and the clock cannot be in a corner anyway: it is the
 * thing every other decision on screen is measured against, so it sits where
 * the eye returns to rather than where it goes looking.
 *
 * THE FIGURE COUNTS SECONDS, NOT MINUTES, and it does that because the length
 * is ROLLED (`NIGHT_LENGTH_JITTER`). A clock that always started at 4:00 would
 * be memorised after two runs and stop being read; "3:47" has to be looked at,
 * and a number the player looks at is a number applying pressure.
 */

import { cn } from '@/lib/utils';
import type { HudNight } from '../../game/hud-store';

export interface NightClockProps {
  night: HudNight | null;
}

/** `m:ss`. Never `mm:ss` — a leading zero on the minute buys nothing and the
 *  figure is narrower without it, which matters at 24px in the middle of the
 *  screen. */
function clock(seconds: number): string {
  const whole = Math.max(0, Math.ceil(seconds));
  const m = Math.floor(whole / 60);
  const s = whole % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function NightClock({ night }: NightClockProps) {
  if (!night) return null;

  const { phase } = night;
  const ratio = night.total > 0 ? Math.max(0, Math.min(1, night.left / night.total)) : 0;

  return (
    <div
      className="hud-layer pixel-text inset-x-0 top-2.5 flex flex-col items-center gap-1"
      // The label is what a screen reader gets; the figure below is drawn for
      // the eye and reads as a bare number without it.
      role="timer"
      aria-label="Tempo até o amanhecer"
    >
      <span
        className={cn(
          'text-[10px] leading-[12px] tracking-[0.22em] uppercase',
          phase === 'calm' ? 'text-ink-muted' : 'text-ink-accent',
        )}
      >
        {/* THE LABEL NAMES THE CONSEQUENCE ONLY WHEN THERE IS ONE. For most of
            a night this is a neutral heading and the number under it is just
            information; inside the last minute it becomes the sentence the
            player needs, without the layout moving. */}
        {phase === 'calm' ? 'Amanhecer' : 'As fendas fecham em'}
      </span>

      <span
        className={cn(
          'text-[24px] leading-[26px] tabular-nums tracking-[0.06em] drop-shadow-[0_2px_0_var(--hud-text-shadow)]',
          phase === 'panic'
            ? 'animate-night-panic text-hp-low'
            : phase === 'warn'
              ? 'text-ink-accent'
              : 'text-ink',
        )}
      >
        {clock(night.left)}
      </span>

      {/* THE METER IS THE PART YOU READ WITHOUT LOOKING. A figure has to be
          focused on and parsed; a bar that is a third full is understood from
          the corner of an eye while you are aiming at something else — which
          is the only state the player is ever in when this matters. */}
      <span className="bg-panel-border/50 relative block h-px w-[92px] overflow-hidden">
        <span
          className={cn(
            'absolute inset-y-0 left-0 block transition-[width] duration-500 ease-linear',
            phase === 'panic'
              ? 'bg-hp-low'
              : phase === 'warn'
                ? 'bg-ink-accent'
                : 'bg-ink-muted',
          )}
          style={{ width: `${ratio * 100}%` }}
        />
      </span>
    </div>
  );
}
