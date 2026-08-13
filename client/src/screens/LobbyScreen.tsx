/**
 * The campfire lobby: roster on the left, the fire on the right.
 *
 * Nothing here is playable — the character standing in the scene is you, but
 * the arena has not started and no input is read. The screen exists to answer
 * three questions at a glance: what is the code, who is here, and are we
 * waiting on anybody.
 */

import { useMemo } from 'react';
import { CampfireCanvas } from '@/components/lobby/CampfireCanvas';
import { PlayerRoster } from '@/components/lobby/PlayerRoster';
import { RoomCode } from '@/components/lobby/RoomCode';
import { MenuButton } from '@/components/menu/MenuButton';
import type { LobbyMember } from '@/game/lobby-scene';
import { cn } from '@/lib/utils';
import type { RoomSession } from '@/hooks/useRoomSession';

export interface LobbyScreenProps {
  code: string;
  session: RoomSession;
  onLeave: () => void;
}

export function LobbyScreen({ code, session, onLeave }: LobbyScreenProps) {
  const { lobby, selfId, isHost, status, start } = session;
  const players = lobby?.players ?? [];

  // The scene diffs by id, but a fresh array every render would still make it
  // re-sort and re-allocate on every unrelated re-render.
  const members = useMemo<LobbyMember[]>(
    () =>
      players.map((player) => ({
        id: player.id,
        name: player.name,
        color: player.color,
        isLocal: player.id === selfId,
        isHost: player.id === lobby?.hostId,
      })),
    [players, selfId, lobby?.hostId],
  );

  const connected = status === 'open';

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-surface md:flex-row">
      <aside className="crt-scanlines flex shrink-0 flex-col gap-5 border-panel-border bg-panel p-5 max-md:border-b md:h-full md:w-[336px] md:border-r">
        <header className="flex items-center justify-between">
          <h1 className="pixel-text text-[22px] leading-[26px] tracking-[0.16em] text-ink uppercase">
            Lobby
          </h1>
          <span
            className={cn(
              'pixel-text text-[11px] leading-[17px] uppercase',
              connected ? 'text-hp-high' : 'text-hp-low',
            )}
          >
            {connected ? '● online' : '● reconectando…'}
          </span>
        </header>

        <RoomCode code={code} />

        <div className="h-px bg-panel-border" />

        <div className="min-h-0 flex-1">
          <PlayerRoster
            players={players}
            hostId={lobby?.hostId ?? null}
            selfId={selfId}
          />
        </div>

        <div className="flex flex-col gap-2">
          <MenuButton
            variant="primary"
            disabled={!isHost || !connected}
            onClick={start}
            className={cn(isHost && connected && 'animate-ready-glow')}
          >
            {isHost ? 'Iniciar partida' : 'Aguardando o anfitrião'}
          </MenuButton>
          <MenuButton variant="quiet" onClick={onLeave}>
            Sair da sala
          </MenuButton>
        </div>
      </aside>

      <main className="relative min-h-0 flex-1">
        <CampfireCanvas members={members} className="absolute inset-0" />
        <p className="pixel-text pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 text-center text-[11px] leading-[17px] text-ink-muted">
          {players.length < 2
            ? 'compartilhe o código — a floresta é grande'
            : 'a fogueira não vai durar a noite toda'}
        </p>
      </main>
    </div>
  );
}
