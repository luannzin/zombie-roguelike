/**
 * THE RUN IS OVER.
 *
 * The only screen in this game that takes the world away. Everything else the
 * HUD does is drawn AT the edges precisely so the forest keeps the middle —
 * this covers it, because at this moment there is nothing out there worth
 * looking at any more. What the player was standing in belongs to a run that
 * no longer exists.
 *
 * IT IS THE OPPOSITE OF `ZoneTitle` AND THAT IS THE DESIGN. The arrival card
 * plays into an empty frame, fades gently, and hands the screen back — it is
 * the calm before a night. This one arrives HARD: the word hits on the first
 * frame at a scale it then settles down from, the rules slam out to full width
 * instead of drawing, and nothing about it is soft until it is already there.
 * A run ending should not be paced like a run beginning.
 *
 * THREE LINES, IN THE ORDER THEY MATTER.
 *
 *   VOCÊ MORREU   the fact, in the danger red, and the only red on the screen
 *   Noite N       how far you got — the number the whole run was measured in,
 *                 and the one thing a player wants at that moment
 *   a quiet line  what happens next, so the camp arriving in a moment is not a
 *                 surprise
 *
 * The night number is the run's SCORE and it is treated as one: it is the
 * largest thing on screen after the word itself, because "day 9" is the only
 * sentence a player says out loud about a run that ended.
 *
 * NO BUTTON, AND NOTHING TO PRESS. The server holds this for `WIPE_HOLD` and
 * then sends the camp; the card leaves when the `welcome` clears the store's
 * `wipe`. A "continue" button here would ask the player to make a decision on
 * the one frame where they have nothing to decide, and a hold that ends on its
 * own is what makes it read as a consequence rather than as a dialog.
 *
 * Every animation is a CSS keyframe on mount. React is never in the frame loop
 * — see the HUD contract in components/AGENTS.md.
 */

import type { HudWipe } from '../../game/hud-store';

export interface DeathScreenProps {
  wipe: HudWipe | null;
}

export function DeathScreen({ wipe }: DeathScreenProps) {
  if (!wipe) return null;

  return (
    <div
      className="hud-layer animate-death-veil inset-0 flex flex-col items-center justify-center bg-black"
      role="alert"
      aria-live="assertive"
    >
      <div className="relative flex flex-col items-center gap-5">
        <div className="animate-death-rule bg-hp-low/70 h-px w-0" />

        <h2 className="animate-death-word pixel-text text-hp-low text-[52px] leading-[56px] tracking-[0.2em] uppercase opacity-0 drop-shadow-[0_3px_0_var(--hud-text-shadow)]">
          Você morreu
        </h2>

        <div className="animate-death-rule bg-hp-low/70 h-px w-0 [animation-delay:90ms]" />

        <p className="animate-death-score pixel-text text-ink text-[26px] leading-[30px] tracking-[0.3em] uppercase opacity-0">
          Noite {wipe.day}
        </p>

        <p className="animate-death-note pixel-text text-ink-muted text-[13px] leading-[18px] tracking-[0.26em] uppercase opacity-0">
          A expedição recomeça do acampamento
        </p>
      </div>
    </div>
  );
}
