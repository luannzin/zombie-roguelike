/**
 * WATCHING SOMEBODY ELSE PLAY, BECAUSE YOU CANNOT.
 *
 * Two things put a player here and they share one camera (`game/spectate.ts`):
 * you are on the floor, or you crossed the exit first and the zone will not
 * turn over until the rest of the party has. Both leave somebody holding a
 * controller with nothing to control while the most interesting part of the
 * run happens to their friends.
 *
 * IT IS THE OPPOSITE OF `DeathScreen` AND THAT IS THE POINT. That card covers
 * the world, because when a run has ended there is nothing out there worth
 * looking at. This one covers as little as possible: the whole reason it
 * exists is the forest behind it. So it is two thin bars — a line at the top
 * that says why, and a strip at the bottom that says whose eyes you are
 * borrowing — and the middle of the screen is left entirely alone.
 *
 * THE TWO REASONS READ DIFFERENTLY AND THEY HAVE TO. Being down is a state
 * somebody can still do something about, and the line says so: it names the
 * one thing that brings you back, because a player who does not know a
 * platform can revive them will not ask their party to carry them to one.
 * Being out is finished — there is nothing to want, only somebody to wait for
 * — so that line counts, and a count is a promise that this ends.
 *
 * THE STRIP IS A LIST OF PEOPLE, NOT A LIST OF CAMERAS. Name, their nameplate
 * colour, a health pip, and a mark on whoever is carrying somebody — which is
 * usually YOU, and is the first thing a downed player wants to know. It is the
 * one place in the HUD where another player's health is drawn, and it earns
 * that here for a reason it would not anywhere else: while you are watching
 * them, their health bar is the run's health bar.
 *
 * IT IS THE ONE HUD LAYER THAT TAKES THE MOUSE BACK WHOLESALE, and that is
 * safe here and nowhere else: there is no trigger to eat. The rest of the HUD
 * opts back in per cell precisely because the canvas underneath is still being
 * aimed at; underneath this one, nothing the player does reaches the world.
 */

import type { HudSpectate } from '../../game/hud-store';
import { cn } from '@/lib/utils';

export interface SpectateProps {
  spectate: HudSpectate | null;
  /** Point the camera at a body. `Game.watchPlayer`. */
  onWatch: (id: string) => void;
}

export function Spectate({ spectate, onWatch }: SpectateProps) {
  if (!spectate) return null;

  const down = spectate.reason === 'downed';

  return (
    <>
      {/*
        THE LINE, at the top, over nothing. It is deliberately not centred on
        the screen's middle — the middle is where the player is looking, and
        this is a caption on what they are looking at rather than a message
        that replaces it.
      */}
      <div className="hud-layer inset-x-0 top-0 flex justify-center pt-6">
        <div className="flex flex-col items-center gap-1 text-center">
          <p
            className={cn(
              'pixel-text text-[15px] leading-[18px] tracking-[0.24em] uppercase',
              down ? 'text-hp-low' : 'text-ink-accent',
            )}
          >
            {down ? 'Você caiu' : 'Você saiu'}
          </p>
          <p className="pixel-text text-ink-muted text-[11px] leading-[14px] tracking-[0.14em]">
            {down
              ? 'um companheiro pode te carregar até uma plataforma'
              : `esperando ${spectate.targets.length} ${
                  spectate.targets.length === 1 ? 'jogador' : 'jogadores'
                }`}
          </p>
        </div>
      </div>

      {/*
        THE STRIP, at the bottom middle — the one part of the glass no other
        panel uses, because the four corners are all spoken for and this is
        only ever on screen while every one of them is meaningless anyway.
      */}
      <div className="hud-layer pointer-events-auto inset-x-0 bottom-0 flex justify-center pb-6">
        <div className="flex items-center gap-1.5">
          {spectate.targets.map((row) => {
            const watched = row.id === spectate.watching;
            const share = row.maxHp > 0 ? Math.max(0, Math.min(1, row.hp / row.maxHp)) : 0;
            return (
              <button
                key={row.id}
                type="button"
                onClick={() => onWatch(row.id)}
                className={cn(
                  'bg-panel/85 border-panel-border relative flex flex-col gap-1 border px-2.5 py-1.5',
                  'pixel-text cursor-pointer text-[11px] leading-[11px]',
                  watched ? 'ring-ink-accent ring-1' : 'opacity-70',
                )}
              >
                <span className="flex items-center gap-1.5">
                  {/* Their own colour, as a pip rather than as the text
                      colour: a name in a dark player colour on a dark panel is
                      unreadable, and the pip carries the identity at any
                      brightness. */}
                  <span
                    aria-hidden
                    className="size-1.5 shrink-0"
                    style={{ backgroundColor: row.color }}
                  />
                  <span className={watched ? 'text-ink' : 'text-ink-muted'}>{row.name}</span>
                  {/* CARRYING SOMEBODY — and it is usually you. The first thing
                      a downed player looks for on this strip. */}
                  {row.carrying ? <span className="text-ink-accent">↑</span> : null}
                </span>
                <span className="bg-track relative block h-1 w-20 overflow-hidden">
                  <span
                    className={cn(
                      'absolute inset-y-0 left-0',
                      share > 0.5 ? 'bg-hp-high' : share > 0.25 ? 'bg-hp-mid' : 'bg-hp-low',
                    )}
                    style={{ width: `${Math.round(share * 100)}%` }}
                  />
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </>
  );
}
