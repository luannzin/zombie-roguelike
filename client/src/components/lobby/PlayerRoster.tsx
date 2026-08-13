/**
 * Who is at the fire.
 *
 * Colour is the join: the swatch on a row is the exact tint the character
 * wears in the scene next to it, so the list and the canvas are one readout
 * rather than two. Rows animate in on mount — React remounts a row when its
 * id first appears, which is the same instant the scene starts summoning it.
 */

import type { LobbyPlayer } from '@/net/protocol';
import { cn } from '@/lib/utils';

export interface PlayerRosterProps {
  players: readonly LobbyPlayer[];
  hostId: string | null;
  selfId: string | null;
}

export function PlayerRoster({ players, hostId, selfId }: PlayerRosterProps) {
  return (
    <div className="flex min-h-0 flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <span className="pixel-text text-[11px] leading-[17px] tracking-[0.18em] text-ink-muted uppercase">
          Sobreviventes
        </span>
        <span className="pixel-text text-[11px] leading-[17px] text-ink">
          {players.length}
        </span>
      </div>

      <ul className="flex min-h-0 flex-col gap-px overflow-y-auto">
        {players.map((player) => {
          const isSelf = player.id === selfId;
          return (
            <li
              key={player.id}
              className={cn(
                'flex items-center gap-2.5 border-l-2 bg-panel-inset/70 px-2.5 py-2',
                'animate-in fade-in slide-in-from-left-2 duration-300',
                isSelf ? 'bg-panel-inset' : 'border-transparent',
              )}
              style={{ borderLeftColor: isSelf ? player.color : undefined }}
            >
              <span
                aria-hidden="true"
                className="size-2.5 shrink-0"
                style={{ backgroundColor: player.color }}
              />
              <span
                className={cn(
                  'pixel-text min-w-0 flex-1 truncate text-[11px] leading-[17px]',
                  isSelf ? 'text-ink' : 'text-ink/80',
                )}
              >
                {player.name}
              </span>
              {isSelf ? (
                <span className="pixel-text shrink-0 text-[11px] leading-[17px] text-ink-muted uppercase">
                  você
                </span>
              ) : null}
              {player.id === hostId ? (
                <span className="pixel-text shrink-0 border border-ink-accent/50 px-1 text-[11px] leading-[15px] text-ink-accent uppercase">
                  anfitrião
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
