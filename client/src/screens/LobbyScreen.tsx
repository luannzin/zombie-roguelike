/**
 * The campfire lobby: roster on the left, the camp on the right.
 *
 * Nothing here is playable — the characters standing in the scene are the
 * party, on the exact tiles the server is holding for them, but the simulation
 * is not running and no input is read. The screen exists to answer three
 * questions at a glance: what is the code, who is here, and are we waiting on
 * anybody.
 *
 * Starting is ACKNOWLEDGED before it is obeyed. The host's click flicks the
 * button, the chrome slides off the glass, and only then does `start` go up the
 * socket — the same arcade cadence the title screen uses. It also buys the one
 * thing the transition needs: a beat where the camp is on screen with nothing
 * on top of it, so the arena's push-in continues a shot the player is already
 * looking at rather than replacing one.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { CampfireCanvas } from '@/components/lobby/CampfireCanvas';
import { PlayerRoster } from '@/components/lobby/PlayerRoster';
import { RoomCode } from '@/components/lobby/RoomCode';
import { MenuButton } from '@/components/menu/MenuButton';
import type { LobbyMember } from '@/game/lobby-scene';
import { cn } from '@/lib/utils';
import type { RoomSession } from '@/hooks/useRoomSession';

/**
 * How long the chrome takes to leave, in ms. Matches the `lobby-exit`
 * keyframes in styles/index.css; changing one without the other either cuts the
 * exit short or leaves a dead pause before the run starts.
 */
const LAUNCH_MS = 420;

export interface LobbyScreenProps {
  code: string;
  session: RoomSession;
  onLeave: () => void;
}

export function LobbyScreen({ code, session, onLeave }: LobbyScreenProps) {
  const { lobby, selfId, camp, isHost, status, start } = session;
  const players = lobby?.players ?? [];
  const [launching, setLaunching] = useState(false);
  const launchTimer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (launchTimer.current !== null) window.clearTimeout(launchTimer.current);
    },
    [],
  );

  const launch = () => {
    if (launching) return;
    setLaunching(true);
    launchTimer.current = window.setTimeout(() => {
      launchTimer.current = null;
      start();
    }, LAUNCH_MS);
  };

  // The scene diffs by id, but a fresh array every render would still make it
  // re-place and re-allocate on every unrelated re-render.
  const members = useMemo<LobbyMember[]>(
    () =>
      players.map((player) => ({
        id: player.id,
        name: player.name,
        color: player.color,
        // The server's own coordinates. This screen never invents a seat.
        x: player.x,
        y: player.y,
        isLocal: player.id === selfId,
        isHost: player.id === lobby?.hostId,
      })),
    [players, selfId, lobby?.hostId],
  );

  const connected = status === 'open';
  const zone = lobby?.zone;

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-surface md:flex-row">
      <aside
        className={cn(
          'crt-scanlines flex shrink-0 flex-col gap-5 border-panel-border bg-panel p-5 max-md:border-b md:h-full md:w-[336px] md:border-r',
          launching && 'animate-lobby-exit pointer-events-none',
        )}
      >
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
          {/* What the button starts, named. "Iniciar partida" was true when the
              lobby opened into a forest; it opens into `Preparação` now, and a
              host has to know which. */}
          {zone ? (
            <p className="pixel-text text-ink-muted text-[11px] leading-[17px] uppercase">
              a seguir · {zone.title} — {zone.subtitle}
            </p>
          ) : null}
          <MenuButton
            variant="primary"
            disabled={!isHost || !connected || launching}
            onClick={launch}
            className={cn(isHost && connected && !launching && 'animate-ready-glow')}
          >
            {isHost ? 'Iniciar partida' : 'Aguardando o anfitrião'}
          </MenuButton>
          <MenuButton variant="quiet" onClick={onLeave}>
            Sair da sala
          </MenuButton>
        </div>
      </aside>

      <main className="relative min-h-0 flex-1">
        <CampfireCanvas
          members={members}
          camp={camp}
          seed={code}
          className="absolute inset-0"
        />
        <p
          className={cn(
            'pixel-text pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 text-center text-[11px] leading-[17px] text-ink-muted transition-opacity duration-300',
            launching && 'opacity-0',
          )}
        >
          {players.length < 2
            ? 'compartilhe o código — a floresta é grande'
            : 'a fogueira não vai durar a noite toda'}
        </p>
      </main>
    </div>
  );
}
