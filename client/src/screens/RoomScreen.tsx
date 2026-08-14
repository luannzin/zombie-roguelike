/**
 * A room, at `/r/:code` — the link you send to a friend.
 *
 * One socket serves both halves of this screen (see `useRoomSession`), so the
 * lobby and the arena are two renders of one connection, not two connections.
 * They are also two renders of one PLACE: the lobby draws the camp the server
 * sent in `hello`, and the arena draws the same map with the simulation
 * running.
 *
 * Which one is shown is decided by three facts, and each one closes a gap the
 * player would otherwise see:
 *
 *   welcome    the run has begun. Not enough on its own — the lobby is midway
 *              through its camera move when this lands, and swapping here
 *              would cut the move in half.
 *   launched   the lobby says its move has finished. Now the arena may build.
 *   ready      the arena says it has actually DRAWN. Until then its canvas is
 *              blank — sheets resolving, terrain baking — so it is mounted
 *              hidden, over a lobby that is still holding the frame the camera
 *              landed on. Both are showing the same picture at that point, so
 *              revealing one and dropping the other changes nothing on screen.
 *
 * The arena is keyed on `playerId`. A reconnect makes you a new player
 * server-side, and a `Game` cannot be patched into a different identity.
 */

import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { MenuButton } from '@/components/menu/MenuButton';
import { useRoomSession } from '@/hooks/useRoomSession';
import { loadName } from '@/lib/identity';
import { ArenaScreen } from './ArenaScreen';
import { LobbyScreen } from './LobbyScreen';

const ERRORS: Record<string, string> = {
  room_not_found: 'Esta sala não existe mais.',
};

export function RoomScreen() {
  const { code = '' } = useParams();
  const navigate = useNavigate();
  // Read once: the name is fixed for the life of the room, and re-reading it
  // would tear down the socket.
  const [name] = useState(loadName);
  const session = useRoomSession(code.toUpperCase(), name);
  /** True once the lobby has finished handing the screen over. */
  const [launched, setLaunched] = useState(false);
  /** True once the arena has a world on its canvas. */
  const [ready, setReady] = useState(false);
  const onLaunched = useCallback(() => setLaunched(true), []);
  const onFirstFrame = useCallback(() => setReady(true), []);

  // Dropping back to the campfire — a reconnect, a fresh room — has to arm the
  // transition again, or the next run would skip straight into the arena.
  useEffect(() => {
    if (!session.welcome) {
      setLaunched(false);
      setReady(false);
    }
  }, [session.welcome]);

  const leave = () => void navigate('/');

  if (session.error) {
    return (
      <div className="flex h-screen w-screen flex-col items-center justify-center gap-5 bg-surface">
        <p className="pixel-text text-[22px] leading-[26px] tracking-[0.1em] text-hp-low uppercase">
          {ERRORS[session.error] ?? 'Não foi possível entrar.'}
        </p>
        <div className="w-64">
          <MenuButton onClick={leave}>← Voltar ao menu</MenuButton>
        </div>
      </div>
    );
  }

  const building = Boolean(session.connection && session.welcome && launched);

  // Both, briefly. The lobby is underneath holding the frame its camera landed
  // on; the arena is over it, hidden, warming up. DOM order is the stacking
  // order, so the moment it is revealed it covers the lobby exactly.
  return (
    <>
      {building && ready ? null : (
        <LobbyScreen
          code={session.lobby?.code ?? code.toUpperCase()}
          session={session}
          onLeave={leave}
          onLaunched={onLaunched}
        />
      )}
      {building && session.connection && session.welcome ? (
        <ArenaScreen
          key={session.welcome.playerId}
          connection={session.connection}
          welcome={session.welcome}
          visible={ready}
          onFirstFrame={onFirstFrame}
        />
      ) : null}
    </>
  );
}
