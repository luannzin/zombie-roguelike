/**
 * The campfire lobby: the camp, full screen, with the roster panel over it.
 *
 * Nothing here is playable — the characters standing in the scene are the
 * party, on the exact tiles the server is holding for them, but the simulation
 * is not running and no input is read. The panel exists to answer three
 * questions at a glance: what is the code, who is here, and are we waiting on
 * anybody.
 *
 * The canvas is FULL SCREEN and the panel floats on top of it, rather than the
 * two sharing a row. That is not a styling preference: it is what makes the
 * launch possible. The arena's canvas is the whole window, so if this one were
 * a column beside a sidebar, the handover would shift the world sideways by
 * half the sidebar's width no matter how carefully the camera was matched. Same
 * box, same picture. The fire sits on the rest shot in `render/framing.ts` —
 * the same numbers the title screen uses — and taking that displacement back
 * is half of what the launch animates.
 *
 * LAUNCHING is the transition, and it happens here rather than in the arena.
 * The panel slides off to the left while the camera swooshes from the fire onto
 * your own character and pushes in to game scale; by the last frame this screen
 * draws, the picture is what the arena is about to open on. `onLaunched` fires
 * when the move lands, and `RoomScreen` swaps the screens then — not when the
 * `welcome` arrives, which is much earlier and would cut the move in half.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { setBeds } from '@/audio';
import { CampfireCanvas } from '@/components/lobby/CampfireCanvas';
import { PlayerRoster } from '@/components/lobby/PlayerRoster';
import { RoomCode } from '@/components/lobby/RoomCode';
import { MenuButton } from '@/components/menu/MenuButton';
import type { LobbyMember } from '@/game/lobby-scene';
import { cn } from '@/lib/utils';
import type { RoomSession } from '@/hooks/useRoomSession';

/**
 * Seconds the launch takes. The camera move, the panel's exit (`lobby-exit` in
 * styles/index.css, which is shorter so the chrome is gone well before the move
 * lands) and the screen swap are all cut to this one number.
 *
 * Long, deliberately. This is a drift onto your character, not a snap-zoom —
 * the party is what the player is looking at and the camera should take its
 * time leaving them.
 */
const LAUNCH_SECONDS = 2.1;

export interface LobbyScreenProps {
  code: string;
  session: RoomSession;
  onLeave: () => void;
  /** Called once the launch has landed and the arena may take the screen. */
  onLaunched: () => void;
}

export function LobbyScreen({ code, session, onLeave, onLaunched }: LobbyScreenProps) {
  const { lobby, selfId, camp, isHost, status, start } = session;
  const players = lobby?.players ?? [];
  const [launching, setLaunching] = useState(false);
  const landed = useRef(onLaunched);
  landed.current = onLaunched;

  // Everyone launches, not just whoever clicked: the host starts the move on
  // their own press so the button answers instantly, and every other client
  // starts it when the phase flips. `beginLaunch` is idempotent, so a host
  // hitting both paths still gets one move.
  const playing = lobby?.phase === 'playing';
  /**
   * The camp sounds like a bonfire, and being on this screen is what says so.
   *
   * Ambience is declared by the SCREEN rather than by `CampfireCanvas`, because
   * the scene is drawn on the title screen too and the menu must be silent —
   * and because the fire has to survive this screen unmounting into the arena.
   * There is deliberately no cleanup: whoever mounts next states its own mix
   * (`HomeScreen` states silence, `Game` states the zone's), so the hand-off
   * into a run has no gap while leaving for the menu still goes quiet.
   */
  useEffect(() => {
    setBeds({ fire: 1 });
  }, []);

  useEffect(() => {
    if (playing) setLaunching(true);
  }, [playing]);

  useEffect(() => {
    if (!launching) return;
    const timer = window.setTimeout(() => landed.current(), LAUNCH_SECONDS * 1000);
    return () => window.clearTimeout(timer);
  }, [launching]);

  const launch = () => {
    if (launching) return;
    setLaunching(true);
    start();
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
    <div className="relative h-screen w-screen overflow-hidden bg-surface">
      <CampfireCanvas
        members={members}
        camp={camp}
        seed={code}
        launching={launching}
        launchSeconds={LAUNCH_SECONDS}
        className="absolute inset-0"
      />

      <aside
        className={cn(
          'crt-scanlines absolute top-0 left-0 z-10 flex h-full w-full max-w-[336px] flex-col gap-5 border-panel-border bg-panel/95 p-5 md:border-r',
          'max-md:h-auto max-md:max-w-none max-md:border-b',
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

      {/*
        The letterbox closing over the push-in. It reaches full opacity on the
        exact frame the camera lands, and the arena opens holding it there (see
        components/hud/Hud) — so the cut between the two canvases happens
        underneath a bar that is not moving. Above the panel, because the panel
        is leaving and the frame closing down over it is the point.
      */}
      {launching ? (
        <div
          className="zone-bars animate-zone-bars-in z-20"
          style={{ animationDuration: `${LAUNCH_SECONDS}s` }}
          aria-hidden="true"
        />
      ) : null}

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
    </div>
  );
}
